# AutoDesk — ML-Based IT Ticket Classification and Routing

A full-stack internal IT helpdesk. Employees describe a problem in their own
words, a fine-tuned **DistilBERT** model classifies it into one of six
categories, and deterministic rule engines assign the **priority**, the **support
team** and an **SLA deadline**. Agents work a filtered queue, admins get
analytics and can re-run the model on any ticket.

```
React (Vite)  ──JWT──▶  Flask REST API  ──▶  PostgreSQL
                                 │
                                 └──▶  DistilBERT (category)
                                      Priority engine (rules)
                                      Routing engine (rules)
                                      SLA engine (deadlines)
```

| Layer     | Stack                                                  |
| --------- | ----------------------------------------------------- |
| Frontend  | React 18, Vite, React Router, Tailwind, Axios, Recharts |
| Backend   | Flask 3, Flask-SQLAlchemy, Flask-JWT-Extended, bcrypt   |
| Database  | PostgreSQL (schema, view, trigger, CHECK constraints)  |
| ML        | PyTorch, HuggingFace Transformers, scikit-learn         |
| Tests     | pytest (135 tests), contract check, smoke test          |

---

## 1. Quick start

Three terminals. Prerequisite: **Python 3.11+**, **Node 18+**, a running
**PostgreSQL 14+**.

### 1.1 Database

```bash
createdb autodesk_db
psql -d autodesk_db -f database/schema.sql   # optional: or let the app create it
```

### 1.2 Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows:  .venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env            # then edit DATABASE_URL / SECRET_KEY / JWT_SECRET_KEY
flask --app run.py reset-db --yes # creates the schema and demo data
python run.py                     # http://127.0.0.1:5000
```

The first start loads the DistilBERT checkpoint into memory once (~1s) and warms
it up, so the first ticket does not pay the latency. Confirm with:

```bash
curl http://127.0.0.1:5000/api/health/ready
# {"readiness":"ready","checks":{"database":"ok","ml_engine":"distilbert","ml_ready":"ok"}}
```

### 1.3 Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

Vite proxies `/api` to `http://127.0.0.1:5000`, so the browser only ever talks
to one origin and no CORS preflight happens in development.

### Demo accounts

`flask reset-db` / `flask seed-db` creates these (passwords in `.env` as
`SEED_ADMIN_PASSWORD` / `SEED_DEFAULT_PASSWORD`):

| Role     | Email                             | Password     |
| -------- | --------------------------------- | ------------ |
| Admin    | `admin@autodesk.local`            | `Admin@123`  |
| Employee | `employee1@autodesk.local` … `employee5@autodesk.local` | `Employee@123` |
| Agent    | `agent.network@autodesk.local`, `agent.software@…`, `agent.hardware@…`, `agent.security@…`, `agent.network2@…` | `Agent@123` |

The login page lists them so the app can be reviewed without reading this file.

---

## 2. How a ticket is processed

1. **Classification — DistilBERT.** The title and description go through the
   fine-tuned checkpoint (`distilbert/distilbert-base-uncased-finetuned-autodesk`)
   which returns a category plus a softmax **confidence**. The API never invents
   a category: it is either the model's output or an error.
2. **Priority — deterministic rules** (`app/services/priority_engine.py`).
   Keywords, urgency phrases, scope words and impacted-user counts add up to a
   score that maps to `Critical / High / Medium / Low`. The matched rules are
   returned as `priority_reason`, so any priority can be explained and audited.
3. **Routing — deterministic rules** (`app/services/routing_engine.py`).
   Category → team: Software→Software Team, Hardware→Hardware Team,
   Network/VPN→Network Team, Login/Access→Security Team. An agent cannot claim a
   ticket outside their own team.
4. **SLA** (`app/services/sla_service.py`). `Critical 2h · High 4h · Medium 8h ·
   Low 24h`, configurable in `.env`. Deadlines are computed at creation time;
   a scanner raises notifications at 80% elapsed and on breach.

Priority and routing stay rule-based on purpose: an auditor must be able to
reproduce them, and a model must never decide who gets access to a ticket.

---

## 3. Roles and what each can do

| Capability                                | Employee | Agent | Admin |
| ----------------------------------------- | :------: | :---: | :---: |
| Raise a ticket, track own tickets         | ✅       | —      | —      |
| Live classification preview while typing  | ✅       | —      | —      |
| See assigned team, priority, SLA countdown | ✅      | —      | —      |
| Team queue, claim, add notes, resolve     | —        | ✅     | —      |
| Notifications, read/unread                | ✅       | ✅     | ✅     |
| All tickets, all filters, analytics       | —        | —      | ✅     |
| User management (role, team, active flag)  | —        | —      | ✅     |
| Re-run the model on any ticket            | —        | —      | ✅     |
| SLA report, system status, ML diagnostics  | —        | —      | ✅     |

Enforcement is server-side: `@role_required(...)` on every blueprint, plus a
per-ticket ownership check. Hiding a button in React is a convenience, not the
control.

---

## 4. API reference

All responses use one envelope, so the frontend unwraps in a single place:

```json
{ "success": true, "message": "Ticket created.", "data": { } }
{ "success": false, "error": "validation_error",
  "message": "Validation failed.", "fields": { "title": "Required." } }
```

Authenticated calls send `Authorization: Bearer <access_token>`.
List endpoints return `data.items` plus `data.pagination`.

### Public

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET  | `/api/health` | Liveness |
| GET  | `/api/health/ready` | Database + model readiness |
| GET  | `/api/meta` | Categories, priorities, statuses, teams, routing table, SLA hours |
| POST | `/api/auth/register` | Create an account (no token; sign in after) |
| POST | `/api/auth/login` | Returns `access_token` + user |
| GET  | `/api/auth/registration-policy` | Public registration rules + password rules |
| GET  | `/api/auth/stats` | Public counters for the login page |

### Authenticated

| Method | Path | Role | Purpose |
| ------ | ---- | ---- | ------- |
| GET   | `/api/auth/me` | any | Current user |
| PATCH | `/api/auth/password` | any | Change own password |
| POST  | `/api/auth/password-strength` | any | Live password rules feedback |
| POST  | `/api/auth/logout` | any | Invalidate the current token |
| GET   | `/api/notifications` / `unread-count` | any | Notification centre |
| PATCH | `/api/notifications/<id>/read`, `/read-all` | any | Mark read |

### Tickets

| Method | Path | Role | Purpose |
| ------ | ---- | ---- | ------- |
| POST | `/api/tickets` | any | Create; runs the full ML pipeline |
| GET  | `/api/tickets/my` | employee | Own tickets |
| GET  | `/api/tickets` | any | Scoped by role server-side |
| GET  | `/api/tickets/<id>` | owner/team/admin | One ticket with SLA and audit trail |
| PATCH | `/api/tickets/<id>` | employee | Edit own **Open** ticket |
| POST | `/api/tickets/<id>/notes` | any | Append a note |
| POST | `/api/tickets/<id>/claim` | employee/agent | Claim |
| POST | `/api/tickets/lookup` | any | Preview classification without creating |
| GET  | `/api/tickets/metadata` | any | Controlled vocabularies |

### Agent

`GET /api/agent/dashboard` · `GET /api/agent/tickets` (own team, any filter) ·
`GET /api/agent/tickets/<id>` · `POST /api/agent/tickets/<id>/claim` ·
`PATCH /api/agent/tickets/<id>/status` · `GET /api/agent/my-tickets` ·
`GET /api/agent/teams` · `GET /api/agent/notifications/unread-count`

Status transitions are validated server-side (`Open → In Progress → Resolved`,
reopen allowed); resolving without notes is a 422 because the UI requires them.

### Admin

`GET /api/admin/dashboard` · `GET /api/admin/analytics` · `GET /api/admin/reports` ·
`GET /api/admin/tickets` · `GET /api/admin/tickets/<id>` · `POST /api/admin/reclassify/<id>` ·
`GET /api/admin/users` · `GET|PATCH /api/admin/users/<id>` · `GET /api/admin/sla` ·
`POST /api/admin/sla/scan` · `GET /api/admin/ml-status` · `GET /api/admin/system`

`PATCH /api/admin/users/<id>` accepts `role`, `team`, `is_active`. Two rules the
database enforces and the API surfaces as 422 rather than a 500:

- promoting someone to `agent` requires a `team` in the same request;
- a non-agent can never hold a `team`, and demoting an agent clears it.

Print the full list yourself with `flask --app run.py routes-list` (48 routes).

---

## 5. Frontend structure

```
frontend/src
├── App.jsx                 role-guarded routes, /notifications per role
├── components/             AppShell (nav + unread badge), ui.jsx, StrengthMeter
├── context/                AuthContext (JWT), MetaContext (vocabularies)
├── hooks/useAsync.js       loading/error/data + debounce
├── pages/
│   ├── Login Register Forbidden NotFound Notifications
│   ├── employee/           Dashboard NewTicket MyTickets TicketDetail
│   ├── agent/              Dashboard Queue MyTickets TicketDetail
│   └── admin/              Dashboard Tickets TicketDetail Analytics Users MlStatus
├── services/api.js         typed client, unwraps the envelope, 401 handling
└── utils/format.jsx        CategoryBadge PriorityBadge StatusBadge SlaBadge
```

Vocabularies are never hardcoded in React — they come from `/api/meta` through
`MetaContext`, so a dropdown cannot offer a value the database would reject.

---

## 6. Machine learning

| Script | Purpose |
| ------ | ------- |
| `ml/generate_data.py` | Builds the labelled ticket corpus (6 categories, seeded RNG) |
| `ml/preprocess.py` | Cleans, folds bad labels, deduplicates, stratified 70/15/15 split |
| `ml/train.py` | Fine-tunes DistilBERT, reports metrics, copies artifacts to the backend |
| `ml/evaluate.py` | Confusion matrix + per-class P/R/F1 on the held-out test split |
| `ml/predictor.py` | CLI around the same predictor the API uses |

Retrain from scratch:

```bash
cd ml
python generate_data.py
python preprocess.py
python train.py --epochs 3
python evaluate.py
python predictor.py "The VPN drops every few minutes"
```

**On the reported 100% accuracy:** the corpus is synthetic and cleanly
separable by topic words, so the headline metrics are high by construction. The
value of this component is the *pipeline* — a real fine-tuned checkpoint, a
reproducible training path, and an admin screen that shows exactly which model
is loaded with which metrics — not the score itself. `GET /api/admin/ml-status`
reports the live checkpoint, label mappings and the held-out report.

If the checkpoint is missing the API can fall back to a keyword classifier
(`ML_ALLOW_FALLBACK=True`) so the rest of the system stays usable; set it to
`False` to make a missing model a hard error.

---

## 7. Testing

```bash
cd backend
python -m pytest ../tests -q          # 135 tests
python smoke_test.py                  # end-to-end against live Postgres + real model
python frontend_contract_check.py     # 89 checks that the React API layer matches the backend
python replay_postman_collection.py   # 40 checks that the shipped Postman collection still works
```

| Suite | Covers |
| ----- | ------ |
| `tests/test_auth.py` | Registration, login, password rules, JWT, RBAC |
| `tests/test_tickets.py` | Creation, filtering, editing, claiming, notes, SLA deadlines |
| `tests/test_admin.py` | Analytics, users/role rules, reclassify, ML status |
| `tests/test_notifications.py` | Creation, read state, unread counts |
| `tests/test_api_smoke.py` | Health, meta, envelopes, route guards |
| `tests/test_engines.py` | Priority and routing rule engines |
| `tests/test_ml_model.py` | **Real** checkpoint inference — no mocks |

`frontend_contract_check.py` is the one that catches drift between the two
halves of the app: it logs in as all three roles and asserts every field the
React pages read is present in the live response, so a renamed key fails here
instead of rendering an empty card in the browser. `replay_postman_collection.py`
does the same job for the documentation.

> The pytest fixtures truncate the live tables, and the contract/replay scripts
> mutate data (they change a demo password, promote a user, resolve a ticket).
> Run `flask --app run.py reset-db --yes` afterwards to restore the demo state.

---

## 8. API collection

`docs/autodesk.postman_collection.json` covers all five areas in order —
Service, Authentication, Employee tickets, Agent queue, Administration — with 42
requests. Import it and run the folders top to bottom: the login scripts capture
JWTs into collection variables and the ticket script captures the created ticket
id, so nothing has to be copied by hand.

Requests that deliberately demonstrate a rule carry an `expected` list
(`Promote without a team` → 422, `Resolve without notes` → 422). Regenerate the
collection after changing the API:

```bash
python build_postman_collection.py     # rebuilds from the Flask URL map
```

---

## 9. CLI reference

```bash
flask --app run.py init-db            # create tables
flask --app run.py reset-db --yes     # DROP, recreate, reseed  ← use before a demo
flask --app run.py seed-db             # additive: missing users/sample tickets only
flask --app run.py seed-db --no-tickets
flask --app run.py drop-db --yes
flask --app run.py ml-status           # classifier diagnostics
flask --app run.py sla-scan            # raise SLA notifications now
flask --app run.py routes-list
```

---

## 10. Security notes

- Passwords are bcrypt hashes; plain text is never stored or logged.
- JWT access tokens carry the role, but every role check is re-verified against
  the database on each request, so a demotion takes effect immediately.
- SQL is only ever built with SQLAlchemy expressions and bound parameters.
- Error responses never leak stack traces.
- A `CHECK` constraint keeps an agent's team consistent with their role.
- `.env`, `.venv/`, `node_modules/`, `dist/` and model checkpoints are
  git-ignored. Never commit `backend/.env`.
- Mail is best-effort: a ticket is never lost because SMTP is down.

---

## 11. Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `could not translate host name` / connection refused | PostgreSQL is not running or `DATABASE_URL` is wrong |
| `password authentication failed` | Special characters in the DB password must be URL-encoded (`@`→`%40`) |
| `/api/health/ready` shows `ml_ready: degraded` | Checkpoint not found — confirm `ML_MODEL_PATH=app/ml/saved_model` |
| Frontend shows network errors | Backend not running on port 5000, or the Vite proxy target is wrong |
| 401 immediately after login | Token expired (`JWT_ACCESS_TOKEN_EXPIRES_MINUTES`, default 480) or a stale `.env` secret |
| Login works but the page is empty | Reseed: `flask --app run.py reset-db --yes` |
| `Object of type timedelta is not JSON serializable` | Fixed in `admin_routes.py`; update your checkout |

---

## 12. Project layout

```
Autodesk/
├── backend/            Flask API, ML integration, services, models, CLI
│   ├── app/
│   │   ├── ml/         DistilBERT wrapper + the trained checkpoint
│   │   ├── models/     SQLAlchemy models (CHECK constraints mirror the SRS)
│   │   ├── routes/     auth, ticket, agent, admin, notification, system blueprints
│   │   ├── services/   priority_engine, routing_engine, sla_service, analytics…
│   │   └── utils/      responses, validators, decorators
│   ├── config.py  run.py  seed.py
│   ├── smoke_test.py                 end-to-end HTTP check
│   ├── frontend_contract_check.py    frontend ↔ backend contract
│   ├── build_postman_collection.py   regenerates docs/autodesk.postman_collection.json
│   └── replay_postman_collection.py  replays it against the live API
├── frontend/           React + Vite SPA
├── database/           schema.sql, seed.sql
├── docs/               ARCHITECTURE.md, autodesk.postman_collection.json
├── ml/                 generate_data, preprocess, train, evaluate, predictor
└── tests/              pytest suite
```