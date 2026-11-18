# Architecture

How AutoDesk is put together and, more importantly, *why* the boundaries sit
where they do.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser                                                              │
│  React 18 + Vite + React Router + Tailwind + Axios + Recharts        │
│  Pages per role, vocabularies from /api/meta, JWT in localStorage    │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  Authorization: Bearer <JWT>
                                │  Vite dev server proxies /api → :5000
┌───────────────────────────────▼──────────────────────────────────────┐
│  Flask API                                                            │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────────┐  │
│  │ auth       │  │ ticket     │  │ agent      │  │ admin          │  │
│  │ blueprint  │  │ blueprint  │  │ blueprint  │  │ blueprint      │  │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └───────┬────────┘  │
│        │  @jwt_required  │  @role_required / @owns_ticket_or_staff     │
│  ┌─────▼────────────────▼──────────────▼────────────────▼────────┐   │
│  │ services                                                      │   │
│  │   ticket_service  priority_engine  routing_engine  sla_service │   │
│  │   auth_service    analytics_service  notification_service      │   │
│  └─────┬──────────────────────────────┬──────────────────────────┘   │
│        │                              │                              │
│  ┌─────▼──────────┐            ┌──────▼───────────────────────┐   │
│  │ DistilBERT     │            │ SQLAlchemy → PostgreSQL        │   │
│  │ (category)     │            │ models mirror the SRS CHECKs   │   │
│  └────────────────┘            └───────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

## Layers

| Layer | Files | Responsibility |
| ----- | ----- | -------------- |
| Routes | `app/routes/*.py` | HTTP concerns only: parse, authorise, delegate, shape the response. No business rules. |
| Services | `app/services/*.py` | All the logic: ticket lifecycle, priority, routing, SLA, analytics, notifications. |
| Models | `app/models/*.py` | Schema and `to_dict()`. The CHECK constraints mirror the SRS so the database is the last line of defence. |
| ML | `app/ml/predictor.py` | Wraps the DistilBERT checkpoint; loaded once per process. |
| Utils | `app/utils/*.py` | Response envelope, validators, decorators, error handling. |

Routes never contain business logic and services never touch `flask.request`.
That split is what makes the engines directly unit-testable — see
`tests/test_engines.py`, which never builds an app context.

## Request flow: creating a ticket

1. `POST /api/tickets` → `create_ticket` validates the payload (`require_object`,
   `get_string`) and rejects anything malformed with a 422 that names the field.
2. `auth_service` resolves the employee from the JWT.
3. `app.ml.predictor` returns `{category, confidence}` from the checkpoint.
4. `priority_engine.predict_priority` scores the text against keyword, urgency,
   scope and impact rules → `{priority, score, reasons}`.
5. `routing_engine` maps the category to a team and exposes the SLA hours.
6. `sla_service.compute_due_at` stamps the deadline.
7. The `Ticket` row is written, an audit entry is recorded, notifications are
   queued for the team, and the best-effort email is attempted.
8. The response returns the ticket **and** the analysis, so the UI can explain
   itself: "classified as Network (98% confidence), High because it says
   'repeatedly', routed to the Network Team, 4h SLA".

Step 8 matters for evaluation: nothing in the system makes a decision a user
cannot see the reason for.

## Why the engines are rule-based

DistilBERT does classification, which is fuzzy language understanding — a good
fit for a model. Priority, routing and SLA decide **who is allowed to see a
ticket** and **when it must be closed**. Those must be reproducible and
auditable, so they are deterministic rule engines that return their reasoning:

```json
{
  "priority": "High",
  "score": 62,
  "reasons": ["urgency keyword: 'urgent'", "impact: 'affects 20 users'"]
}
```

An admin can always reproduce and contest the result, and
`POST /api/admin/reclassify/<id>` re-runs the model on demand and reports the
before/after.

## Authorisation model

Three roles, enforced on the server for every request:

| Mechanism | Where | What it guarantees |
| --------- | ----- | ------------------ |
| `@jwt_required()` | every authenticated blueprint | No anonymous access at all. |
| `@role_required(...)` | admin/agent blueprints | An employee calling an admin endpoint gets 403 before the handler runs. |
| `@owns_ticket_or_staff` | ticket detail/update | An employee cannot read or edit another employee's ticket. |
| Query scoping in `list_tickets` | `GET /api/tickets` | The list is filtered by `created_by` or `team` in SQL, not in React. |
| `CHECK (role <> 'agent' OR team IS NOT NULL)` | database | An agent always belongs to a team, so queue scoping is always well defined. |

The JWT carries the role as a claim for convenience, but authorisation
re-reads the user from the database, so deactivating or demoting someone takes
effect on their very next request.

## Frontend structure

- **One API client** (`services/api.js`) unwraps the response envelope once and
  centralises the JWT header, the 30s timeout and 401 handling (clearing the
  stale session and notifying the router).
- **Vocabularies come from the server.** `MetaContext` loads `/api/meta` once and
  shares categories, priorities, statuses and teams, so a dropdown cannot offer a
  value the database CHECK constraint would reject.
- **`AppShell`** renders the navigation, the unread-notification badge and the
  role-scoped menu; each role's routes are nested under it in `App.jsx`.
- **The admin ML page reads live diagnostics** (`/api/admin/ml-status`), not a
  hardcoded accuracy number, so what the UI claims is what the API loaded.

## Notification and SLA pipeline

`sla_service.find_tickets_needing_alert()` splits open tickets into
`warning` (≥80% of the window elapsed) and `breach`, and
`notification_service` raises one notification per event. It runs three ways:
inline after a status change, on demand via `flask sla-scan` or
`POST /api/admin/sla/scan`, and it is idempotent, so a scan never duplicates a
notification for the same ticket and threshold.

## Environment

| Variable | Purpose |
| -------- | ------- |
| `DATABASE_URL` | PostgreSQL DSN (URL-encode special characters in the password) |
| `SECRET_KEY`, `JWT_SECRET_KEY` | Signing keys — generate real ones, never commit |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | Session length (default 480) |
| `CORS_ORIGINS` | Allowed browser origins |
| `ML_MODEL_PATH`, `ML_MAX_LENGTH`, `ML_ALLOW_FALLBACK` | Classifier location, sequence length, fallback policy |
| `SLA_*_HOURS`, `SLA_NEAR_THRESHOLD` | Response windows and the warning threshold |
| `MAIL_*` | Best-effort SMTP; a ticket never fails because mail is down |

## Testing strategy

| Layer | Test file | What it proves |
| ----- | --------- | -------------- |
| Rule engines | `test_engines.py` | Deterministic behaviour, no app or DB needed. |
| API | `test_auth.py`, `test_tickets.py`, `test_admin.py`, `test_notifications.py`, `test_api_smoke.py` | Routes, RBAC and validation against live PostgreSQL. |
| ML | `test_ml_model.py` | Real checkpoint inference — the classifier is genuinely loaded and returns the right labels. |
| Contract | `frontend_contract_check.py` | Every field the React pages read is present in the live response. |
| End-to-end | `smoke_test.py` | A ticket created through the HTTP API, resolved, and its SLA/notification trail verified. |
| Docs | `replay_postman_collection.py` | The shipped Postman collection still matches the API. |

The contract and documentation replays exist because the two halves of this
project were written separately; they are the cheapest way to catch a renamed
response key before a reviewer sees an empty card.