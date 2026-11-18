-- ===========================================================================
--  AutoDesk - A Machine Learning Based IT Ticket Classification and Routing
--  System
--
--  File    : database/schema.sql
--  Target  : PostgreSQL 16+
--  Purpose : Creates the autodesk_db database, the schema owner and all tables
--            with their constraints and indexes.
--
--  Usage
--  -----
--    psql -U postgres -f database/schema.sql
--
--  Then seed the demo data:
--    psql -U postgres -d autodesk_db -f database/seed.sql
--
--  Alternatively the identical schema is created by SQLAlchemy with:
--    cd backend && flask --app run.py init-db
--
--  Notes
--  -----
--  * All timestamps are TIMESTAMP WITH TIME ZONE and hold UTC values.
--  * CHECK constraints mirror the SRS vocabulary exactly; the Flask models
--    (app/models/*.py) use the same constants, so the two never drift apart.
--  * Passwords are bcrypt hashes. No plain-text password is ever stored.
-- ===========================================================================

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------------
-- 0. Database
-- ---------------------------------------------------------------------------
-- Uncomment if psql is not being run while already connected to autodesk_db.
-- SELECT 'CREATE DATABASE autodesk_db'
--   WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'autodesk_db')\gexec

-- ---------------------------------------------------------------------------
-- 1. Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 2. Tables
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 2.1  users
--
--  Three roles: employee, agent, admin.
--  `team` is only populated for agents and is what the routing engine uses to
--  decide which support queue a ticket appears in.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS tickets CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(120)  NOT NULL,
    email       VARCHAR(255)  NOT NULL,
    -- bcrypt hash (60 chars). Never a plain-text password.
    password    VARCHAR(255)  NOT NULL,
    role        VARCHAR(20)   NOT NULL DEFAULT 'employee',
    team        VARCHAR(50),
    is_active   BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT users_role_check
        CHECK (role IN ('employee', 'agent', 'admin')),

    CONSTRAINT users_email_lowercase
        CHECK (email = lower(email)),

    CONSTRAINT users_agent_has_team
        CHECK (role <> 'agent' OR team IS NOT NULL)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE INDEX ix_users_role_created_at ON users (role, created_at);
CREATE INDEX ix_users_team ON users (team) WHERE team IS NOT NULL;

COMMENT ON TABLE  users                IS 'AutoDesk accounts: employees, support agents and administrators.';
COMMENT ON COLUMN users.password       IS 'bcrypt hash. Plain-text passwords are never stored.';
COMMENT ON COLUMN users.team           IS 'Support team for agents: Software / Hardware / Network / Security.';
COMMENT ON COLUMN users.created_at     IS 'UTC account creation timestamp.';

-- ---------------------------------------------------------------------------
-- 2.2  tickets
--
--  category      -> predicted by DistilBERT (6 classes)
--  priority      -> decided by the deterministic priority engine (4 levels)
--  assigned_team -> decided by the routing engine from category
--  sla_due_at    -> created_at + the SLA window for the priority
-- ---------------------------------------------------------------------------
CREATE TABLE tickets (
    id                        SERIAL PRIMARY KEY,
    title                     VARCHAR(200)  NOT NULL,
    description               TEXT           NOT NULL,

    -- AI classification output
    category                  VARCHAR(20)   NOT NULL,
    classification_confidence FLOAT,
    classification_source     VARCHAR(30),
    ml_model                  VARCHAR(120),

    -- Priority engine output
    priority                  VARCHAR(10)   NOT NULL,
    priority_reason           TEXT,

    -- Lifecycle
    status                    VARCHAR(20)   NOT NULL DEFAULT 'Open',
    resolution_notes          TEXT,
    created_at                TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ   NOT NULL DEFAULT now(),
    resolved_at               TIMESTAMPTZ,

    -- Ownership
    created_by                INTEGER       NOT NULL,
    assigned_to               INTEGER,
    assigned_team             VARCHAR(50)   NOT NULL,

    -- SLA
    sla_due_at                TIMESTAMPTZ,

    CONSTRAINT tickets_category_check
        CHECK (category IN ('Software', 'Hardware', 'Network', 'Login', 'VPN', 'Access')),

    CONSTRAINT tickets_priority_check
        CHECK (priority IN ('Low', 'Medium', 'High', 'Critical')),

    CONSTRAINT tickets_status_check
        CHECK (status IN ('Open', 'In Progress', 'Resolved')),

    CONSTRAINT tickets_title_not_blank
        CHECK (length(btrim(title)) > 0),

    CONSTRAINT tickets_description_not_blank
        CHECK (length(btrim(description)) > 0),

    -- A resolved ticket must carry a resolution timestamp, and an unresolved
    -- ticket must not. This is the database-level guarantee behind the
    -- SRS requirement to "record the resolved timestamp".
    CONSTRAINT tickets_resolution_consistency
        CHECK (
            (status = 'Resolved' AND resolved_at IS NOT NULL)
            OR (status <> 'Resolved' AND resolved_at IS NULL)
        ),

    CONSTRAINT tickets_sla_after_creation
        CHECK (sla_due_at IS NULL OR sla_due_at >= created_at),

    CONSTRAINT tickets_confidence_range
        CHECK (
            classification_confidence IS NULL
            OR (classification_confidence >= 0.0 AND classification_confidence <= 1.0)
        ),

    CONSTRAINT tickets_created_by_fk
        FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE RESTRICT,

    CONSTRAINT tickets_assigned_to_fk
        FOREIGN KEY (assigned_to) REFERENCES users (id) ON DELETE SET NULL
);

-- Analytics hot paths.
CREATE INDEX ix_tickets_created_by            ON tickets (created_by);
CREATE INDEX ix_tickets_assigned_to           ON tickets (assigned_to);
CREATE INDEX ix_tickets_status_created_at     ON tickets (status, created_at);
CREATE INDEX ix_tickets_team_status           ON tickets (assigned_team, status);
CREATE INDEX ix_tickets_category_priority     ON tickets (category, priority);
CREATE INDEX ix_tickets_created_by_created_at ON tickets (created_by, created_at);
CREATE INDEX ix_tickets_sla_due_at            ON tickets (sla_due_at);

-- Partial index: the agent queue filters on "still open".
CREATE INDEX ix_tickets_open_team ON tickets (assigned_team, priority)
    WHERE status <> 'Resolved';

COMMENT ON TABLE  tickets                    IS 'IT support tickets with AI category, rule-based priority and routed team.';
COMMENT ON COLUMN tickets.category           IS 'DistilBERT prediction: one of the six SRS categories.';
COMMENT ON COLUMN tickets.priority           IS 'Priority engine output - NOT produced by DistilBERT.';
COMMENT ON COLUMN tickets.assigned_team      IS 'Routing engine output (category -> support team).';
COMMENT ON COLUMN tickets.classification_source IS 'distilbert when the trained model answered, keyword-fallback otherwise.';
COMMENT ON COLUMN tickets.sla_due_at         IS 'created_at + the SLA window configured for this priority.';
COMMENT ON COLUMN tickets.resolved_at        IS 'UTC timestamp stamped when the ticket is resolved.';

-- ---------------------------------------------------------------------------
-- 2.3  notifications
--
--  The in-app notification centre. Rows are persisted so notifications survive
--  a page reload and can be reported on by the admin analytics endpoints.
-- ---------------------------------------------------------------------------
CREATE TABLE notifications (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER       NOT NULL,
    ticket_id   INTEGER,
    type        VARCHAR(30)   NOT NULL,
    title       VARCHAR(200)  NOT NULL,
    message     TEXT          NOT NULL,
    is_read     BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT notifications_type_check
        CHECK (type IN (
            'ticket_created',
            'ticket_assigned',
            'ticket_status',
            'ticket_resolved',
            'sla_warning',
            'sla_breach'
        )),

    CONSTRAINT notifications_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,

    CONSTRAINT notifications_ticket_fk
        FOREIGN KEY (ticket_id) REFERENCES tickets (id) ON DELETE CASCADE
);

CREATE INDEX ix_notifications_user_id            ON notifications (user_id);
CREATE INDEX ix_notifications_ticket_id          ON notifications (ticket_id);
CREATE INDEX ix_notifications_created_at         ON notifications (created_at);
CREATE INDEX ix_notifications_user_read_created  ON notifications (user_id, is_read, created_at);

COMMENT ON TABLE notifications IS 'In-app notification centre rows (PostgreSQL backed).';

-- ---------------------------------------------------------------------------
-- 3. Keep updated_at honest
--
-- The application sets updated_at explicitly, but this trigger guarantees the
-- column is never stale even if a future change forgets to.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION autodesk_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tickets_updated_at ON tickets;
CREATE TRIGGER trg_tickets_updated_at
    BEFORE UPDATE ON tickets
    FOR EACH ROW
    EXECUTE FUNCTION autodesk_set_updated_at();

-- ---------------------------------------------------------------------------
-- 4. Convenience views for reporting
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_ticket_summary;
CREATE VIEW v_ticket_summary AS
SELECT
    t.id,
    t.title,
    t.category,
    t.priority,
    t.status,
    t.assigned_team,
    t.assigned_to,
    t.created_by,
    t.created_at,
    t.resolved_at,
    t.sla_due_at,
    t.classification_confidence,
    CASE
        WHEN t.status = 'Resolved' AND t.sla_due_at IS NOT NULL
            THEN (t.resolved_at <= t.sla_due_at)
        ELSE NULL
    END AS resolved_within_sla,
    CASE
        WHEN t.status = 'Resolved' AND t.sla_due_at IS NOT NULL
            THEN round(EXTRACT(EPOCH FROM (t.resolved_at - t.created_at)) / 3600.0, 2)
        WHEN t.status <> 'Resolved' AND t.sla_due_at IS NOT NULL
            THEN round(EXTRACT(EPOCH FROM (now() - t.created_at)) / 3600.0, 2)
        ELSE NULL
    END AS age_hours,
    CASE
        WHEN t.status <> 'Resolved' AND t.sla_due_at IS NOT NULL AND now() > t.sla_due_at
            THEN 'SLA Breached'
        WHEN t.status = 'Resolved' AND t.sla_due_at IS NOT NULL AND t.resolved_at > t.sla_due_at
            THEN 'Resolved After SLA'
        WHEN t.status = 'Resolved' AND t.sla_due_at IS NOT NULL
            THEN 'Resolved Within SLA'
        ELSE 'Within SLA'
    END AS sla_state
FROM tickets t;

COMMENT ON VIEW v_ticket_summary IS 'Flat ticket view with SLA verdict and age, for ad-hoc SQL reporting.';

-- ---------------------------------------------------------------------------
-- 5. Verification
-- ---------------------------------------------------------------------------
SELECT 'users'        AS table_name, count(*) AS row_count FROM users
UNION ALL
SELECT 'tickets',            count(*) FROM tickets
UNION ALL
SELECT 'notifications',      count(*) FROM notifications;

\echo 'AutoDesk schema created successfully.'
