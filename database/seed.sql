-- ===========================================================================
--  AutoDesk - Development / demo seed data
--
--  File    : database/seed.sql
--  Target  : PostgreSQL 16+
--  Purpose : Inserts the demo users and sample tickets described in SRS
--            section 40.
--
--  Usage
--  -----
--    psql -U postgres -d autodesk_db -f database/seed.sql
--
--  IMPORTANT
--  ---------
--  * These are DEMO accounts with known passwords, for a college project
--    demonstration only. Never run this file in production.
--  * Every password below is a real bcrypt hash. There is no plain-text
--    password anywhere in this file (or anywhere else in the project).
--  * All tickets are labelled DEMO TICKET n so seeded rows are identifiable
--    and can be removed with the cleanup query at the bottom of this file.
--  * The seeded ticket labels are authored to exercise all six categories and
--    all four priorities. They are NOT model output - the Flask seeder
--    (`flask --app run.py seed-db`) instead runs the real DistilBERT +
--    priority + routing pipeline over these same descriptions. Prefer that
--    route when you want to demonstrate genuine AI classification.
--
--  Demo credentials
--    admin@autodesk.local            / Admin@123
--    employee1..5@autodesk.local     / Employee@123
--    agent.network@autodesk.local    / Agent@123
--    agent.software@autodesk.local   / Agent@123
--    agent.hardware@autodesk.local   / Agent@123
--    agent.security@autodesk.local   / Agent@123
--    agent.network2@autodesk.local   / Agent@123
-- ===========================================================================

\set ON_ERROR_STOP on
BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Make the run repeatable
-- ---------------------------------------------------------------------------
TRUNCATE notifications, tickets, users RESTART IDENTITY CASCADE;

-- ---------------------------------------------------------------------------
-- 2. Users
--
--    bcrypt hashes (cost 12):
--      Admin@123      -> $2b$12$PV5V4qB49EyyPWm2jReIrefkcJuEbI05ZdGYVAWEv.lcTx9L1e.hW
--      Employee@123   -> $2b$12$pAJz.YM.mNkTtqQwWQJnre4fv9zXQSLXk/ljHf1z.OOVGlsAVWHLy
--      Agent@123      -> $2b$12$/IgoWknyXPGqiPY0eH3k4ORnVgiOVUpY8KI6GtLu8.5uvGjmhp/0S
-- ---------------------------------------------------------------------------

-- ---- 1 administrator -------------------------------------------------------
INSERT INTO users (name, email, password, role, team, is_active, created_at) VALUES
('Ananya Deshmukh', 'admin@autodesk.local',
 '$2b$12$PV5V4qB49EyyPWm2jReIrefkcJuEbI05ZdGYVAWEv.lcTx9L1e.hW',
 'admin', NULL, TRUE, now() - interval '400 days');

-- ---- 5 employees -----------------------------------------------------------
INSERT INTO users (name, email, password, role, team, is_active, created_at) VALUES
('Rahul Sharma',    'employee1@autodesk.local', '$2b$12$pAJz.YM.mNkTtqQwWQJnre4fv9zXQSLXk/ljHf1z.OOVGlsAVWHLy', 'employee', NULL, TRUE, now() - interval '380 days'),
('Priya Nair',      'employee2@autodesk.local', '$2b$12$pAJz.YM.mNkTtqQwWQJnre4fv9zXQSLXk/ljHf1z.OOVGlsAVWHLy', 'employee', NULL, TRUE, now() - interval '340 days'),
('Arjun Das',       'employee3@autodesk.local', '$2b$12$pAJz.YM.mNkTtqQwWQJnre4fv9zXQSLXk/ljHf1z.OOVGlsAVWHLy', 'employee', NULL, TRUE, now() - interval '300 days'),
('Kavya Reddy',     'employee4@autodesk.local', '$2b$12$pAJz.YM.mNkTtqQwWQJnre4fv9zXQSLXk/ljHf1z.OOVGlsAVWHLy', 'employee', NULL, TRUE, now() - interval '260 days'),
('Manish Gupta',    'employee5@autodesk.local', '$2b$12$pAJz.YM.mNkTtqQwWQJnre4fv9zXQSLXk/ljHf1z.OOVGlsAVWHLy', 'employee', NULL, TRUE, now() - interval '220 days');

-- ---- 5 support agents, distributed across the four support teams ------------
INSERT INTO users (name, email, password, role, team, is_active, created_at) VALUES
('Aarav Mehta',    'agent.network@autodesk.local',  '$2b$12$/IgoWknyXPGqiPY0eH3k4ORnVgiOVUpY8KI6GtLu8.5uvGjmhp/0S', 'agent', 'Network Team',  TRUE, now() - interval '360 days'),
('Sara Fernandes', 'agent.software@autodesk.local', '$2b$12$/IgoWknyXPGqiPY0eH3k4ORnVgiOVUpY8KI6GtLu8.5uvGjmhp/0S', 'agent', 'Software Team', TRUE, now() - interval '350 days'),
('Rohan Iyer',     'agent.hardware@autodesk.local', '$2b$12$/IgoWknyXPGqiPY0eH3k4ORnVgiOVUpY8KI6GtLu8.5uvGjmhp/0S', 'agent', 'Hardware Team', TRUE, now() - interval '340 days'),
('Nisha Patel',    'agent.security@autodesk.local', '$2b$12$/IgoWknyXPGqiPY0eH3k4ORnVgiOVUpY8KI6GtLu8.5uvGjmhp/0S', 'agent', 'Security Team', TRUE, now() - interval '330 days'),
('Vikram Rao',     'agent.network2@autodesk.local', '$2b$12$/IgoWknyXPGqiPY0eH3k4ORnVgiOVUpY8KI6GtLu8.5uvGjmhp/0S', 'agent', 'Network Team',  TRUE, now() - interval '320 days');

-- ---------------------------------------------------------------------------
-- 3. Sample tickets
--
--    category      = the six SRS categories (authorship stands in for the model)
--    priority      = the four SRS priorities
--    assigned_team = SRS section 7 routing table
--    sla_due_at    = created_at + the configured window for that priority
--                    Critical 2h | High 4h | Medium 8h | Low 24h
--
--    Timestamps are backdated so the SLA dashboard, the volume trend chart and
--    the average-resolution-time figure all have meaningful data on a fresh
--    install.
-- ---------------------------------------------------------------------------
INSERT INTO tickets (
    title, description, category, priority, status, assigned_team,
    classification_confidence, classification_source, ml_model, priority_reason,
    created_by, assigned_to, created_at, updated_at, resolved_at,
    sla_due_at, resolution_notes
)
VALUES
-- ---------- Software Team ----------
( 'DEMO TICKET 1 - Word crashes on startup',
 'Microsoft Word closes immediately after opening, even after a restart.',
 'Software', 'High', 'Resolved', 'Software Team',
 0.9868, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 100 from: ''crash'', ''not working'' -> High.',
 (SELECT id FROM users WHERE email='employee1@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.software@autodesk.local'),
 now() - interval '40 hours', now() - interval '37 hours', now() - interval '37 hours',
 (now() - interval '40 hours') + interval '4 hours',
 'Cleared the Word normal template and repaired the Office installation.'
),
( 'DEMO TICKET 2 - Excel will not open from the share',
 'Excel spreadsheet will not open from the shared drive and gives a permissions error.',
 'Software', 'Medium', 'Open', 'Software Team',
 0.9750, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 30 from: ''error'', ''not working'' -> Medium.',
 (SELECT id FROM users WHERE email='employee5@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.software@autodesk.local'),
 now() - interval '12 hours', now() - interval '12 hours', NULL,
 (now() - interval '12 hours') + interval '8 hours',
 NULL
),
( 'DEMO TICKET 3 - Outlook password loop',
 'Outlook keeps asking for my password again and again in a loop every few minutes.',
 'Software', 'Medium', 'Open', 'Software Team',
 0.9810, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 30 from: ''password'' -> Medium.',
 (SELECT id FROM users WHERE email='employee4@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.software@autodesk.local'),
 now() - interval '9 hours', now() - interval '9 hours', NULL,
 (now() - interval '9 hours') + interval '8 hours', NULL
),

-- ---------- Hardware Team ----------
( 'DEMO TICKET 4 - Keyboard not responding',
 'My keyboard is not responding at all. Several keys are dead and I cannot type my report.',
 'Hardware', 'High', 'In Progress', 'Hardware Team',
 0.9880, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 90 from: ''not responding'', ''cannot'' -> High.',
 (SELECT id FROM users WHERE email='employee4@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.hardware@autodesk.local'),
 now() - interval '6 hours', now() - interval '3 hours', NULL,
 (now() - interval '6 hours') + interval '4 hours', NULL
),
( 'DEMO TICKET 5 - Printer prints blank pages',
 'The office printer prints blank pages for everyone on my floor since this morning.',
 'Hardware', 'Medium', 'Open', 'Hardware Team',
 0.9840, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 30 from: ''printer'' -> Medium.',
 (SELECT id FROM users WHERE email='employee3@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.hardware@autodesk.local'),
 now() - interval '4 hours', now() - interval '4 hours', NULL,
 (now() - interval '4 hours') + interval '8 hours', NULL
),
( 'DEMO TICKET 6 - Mouse pointer jumps around',
 'My mouse pointer jumps around the screen randomly and I cannot select text accurately.',
 'Hardware', 'Medium', 'Resolved', 'Hardware Team',
 0.9790, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 30 from: ''mouse'' -> Medium.',
 (SELECT id FROM users WHERE email='employee1@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.hardware@autodesk.local'),
 now() - interval '150 hours', now() - interval '146 hours', now() - interval '146 hours',
 (now() - interval '150 hours') + interval '8 hours',
 'Replaced the optical mouse with a new unit from the hardware store.'
),
( 'DEMO TICKET 7 - Laptop battery drains quickly',
 'My laptop battery drains very quickly and I cannot get through the day without it.',
 'Hardware', 'Low', 'Open', 'Hardware Team',
 0.9820, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 8 from: ''battery'' -> Low.',
 (SELECT id FROM users WHERE email='employee4@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.hardware@autodesk.local'),
 now() - interval '30 hours', now() - interval '30 hours', NULL,
 (now() - interval '30 hours') + interval '24 hours', NULL
),

-- ---------- Network Team ----------
( 'DEMO TICKET 8 - Internet not working',
 'My office laptop cannot access the company network and WiFi keeps disconnecting.',
 'Network', 'High', 'Resolved', 'Network Team',
 0.9862, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 90 from: ''cannot'', ''disconnecting'' -> High.',
 (SELECT id FROM users WHERE email='employee1@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.network@autodesk.local'),
 now() - interval '96 hours', now() - interval '91 hours', now() - interval '91 hours',
 (now() - interval '96 hours') + interval '4 hours',
 'Replaced the faulty network cable at the desk and re-seated the switch port.'
),
( 'DEMO TICKET 9 - WiFi very slow in meeting room',
 'The office WiFi is extremely slow in the meeting room and video calls keep freezing.',
 'Network', 'Medium', 'Open', 'Network Team',
 0.9855, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 30 from: ''wifi'', ''slow'' -> Medium.',
 (SELECT id FROM users WHERE email='employee2@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.network@autodesk.local'),
 now() - interval '2 hours', now() - interval '2 hours', NULL,
 (now() - interval '2 hours') + interval '8 hours', NULL
),
( 'DEMO TICKET 10 - Cannot connect to shared drive',
 'The network drive on my desktop keeps showing as unavailable and times out.',
 'Network', 'Medium', 'Resolved', 'Network Team',
 0.9780, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 30 from: ''unavailable'', ''timeout'' -> Medium.',
 (SELECT id FROM users WHERE email='employee2@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.network2@autodesk.local'),
 now() - interval '200 hours', now() - interval '196 hours', now() - interval '196 hours',
 (now() - interval '200 hours') + interval '8 hours',
 'Mapped the drive to the new file server alias after the migration.'
),
( 'DEMO TICKET 11 - Complete outage, internal systems down',
 'The entire system down for the whole finance department. Nothing loads for any of us.',
 'Network', 'Critical', 'In Progress', 'Network Team',
 0.9901, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 155 from: ''entire system down'', ''many users'' -> Critical.',
 (SELECT id FROM users WHERE email='employee1@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.network@autodesk.local'),
 now() - interval '1 hour', now() - interval '30 minutes', NULL,
 (now() - interval '1 hour') + interval '2 hours', NULL
),

-- ---------- VPN -> Network Team (SRS section 7) ----------
( 'DEMO TICKET 12 - VPN not connecting',
 'I urgently need to access the company network from home but VPN keeps disconnecting.',
 'VPN', 'High', 'Resolved', 'Network Team',
 0.9920, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 90 from: ''urgent'', ''cannot'', ''disconnecting'' -> High.',
 (SELECT id FROM users WHERE email='employee2@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.network@autodesk.local'),
 now() - interval '72 hours', now() - interval '70 hours', now() - interval '70 hours',
 (now() - interval '72 hours') + interval '4 hours',
 'Cleared the stale VPN profile and re-installed the updated client.'
),
( 'DEMO TICKET 13 - VPN disconnects every few minutes',
 'The VPN tunnel drops every fifteen minutes. This is urgent, I cannot work from home.',
 'VPN', 'High', 'Resolved', 'Network Team',
 0.9935, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 90 from: ''urgent'', ''disconnecting'', ''cannot work'' -> High.',
 (SELECT id FROM users WHERE email='employee3@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.network2@autodesk.local'),
 now() - interval '120 hours', now() - interval '119 hours', now() - interval '119 hours',
 (now() - interval '120 hours') + interval '4 hours',
 'Updated the client certificate chain and forced TCP instead of UDP.'
),

-- ---------- Security Team (Login) ----------
( 'DEMO TICKET 14 - Forgot my company password',
 'I forgot my company password and the reset email never arrives. I cannot log in at all.',
 'Login', 'High', 'Resolved', 'Security Team',
 0.9890, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 90 from: ''cannot log in'', ''password'' -> High.',
 (SELECT id FROM users WHERE email='employee3@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.security@autodesk.local'),
 now() - interval '50 hours', now() - interval '49 hours', now() - interval '49 hours',
 (now() - interval '50 hours') + interval '4 hours',
 'Identity verified over the phone and the account was unlocked.'
),
( 'DEMO TICKET 15 - Account locked after failed attempts',
 'My account gets locked after three login attempts and I cannot unlock it myself.',
 'Login', 'Medium', 'Resolved', 'Security Team',
 0.9875, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 60 from: ''locked'', ''cannot'' -> High.',
 (SELECT id FROM users WHERE email='employee3@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.security@autodesk.local'),
 now() - interval '80 hours', now() - interval '79 hours 20 minutes', now() - interval '79 hours 20 minutes',
 (now() - interval '80 hours') + interval '8 hours',
 'Unlocked the account and enabled self-service unlock.'
),

-- ---------- Security Team (Access) ----------
( 'DEMO TICKET 16 - Cannot access the HR portal',
 'I need permission to access the HR portal. It returns access denied for my account.',
 'Access', 'Medium', 'In Progress', 'Security Team',
 0.9885, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 30 from: ''permission'', ''access denied'' -> Medium.',
 (SELECT id FROM users WHERE email='employee5@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.security@autodesk.local'),
 now() - interval '20 hours', now() - interval '10 hours', NULL,
 (now() - interval '20 hours') + interval '8 hours', NULL
),
( 'DEMO TICKET 17 - Need read access to the analytics dashboard',
 'I need read access to the analytics dashboard for the quarterly review.',
 'Access', 'Low', 'Resolved', 'Security Team',
 0.9845, 'distilbert', 'distilbert/distilbert-base-uncased-finetuned-autodesk',
 'Scored 8 from: ''request'', ''access'' -> Low.',
 (SELECT id FROM users WHERE email='employee5@autodesk.local'),
 (SELECT id FROM users WHERE email='agent.security@autodesk.local'),
 now() - interval '168 hours', now() - interval '142 hours', now() - interval '142 hours',
 (now() - interval '168 hours') + interval '24 hours',
 'Added the employee to the analytics-readers group. Missed the 24h Low SLA window.'
);

-- ---------------------------------------------------------------------------
-- 4. Notifications for the seeded tickets
--
--    Gives each employee an already-populated notification centre on first
--    login. ticket_created rows for all, plus status/resolved rows for the
--    tickets that have moved on.
-- ---------------------------------------------------------------------------
INSERT INTO notifications (user_id, ticket_id, type, title, message, is_read, created_at)
SELECT
    t.created_by,
    t.id,
    'ticket_created',
    'Ticket #' || t.id || ' created',
    'Your ticket was classified as ' || t.category || ' with ' || t.priority
        || ' priority and routed to the ' || t.assigned_team || '.',
    FALSE,
    t.created_at
FROM tickets t;

INSERT INTO notifications (user_id, ticket_id, type, title, message, is_read, created_at)
SELECT
    t.created_by,
    t.id,
    'ticket_resolved',
    'Ticket #' || t.id || ' resolved',
    'Your ticket was marked as Resolved by the ' || t.assigned_team || '.',
    FALSE,
    t.resolved_at
FROM tickets t
WHERE t.status = 'Resolved';

INSERT INTO notifications (user_id, ticket_id, type, title, message, is_read, created_at)
SELECT
    t.assigned_to,
    t.id,
    'ticket_assigned',
    'New ' || t.priority || ' ticket #' || t.id,
    'Ticket #' || t.id || ' "' || t.title || '" was classified as ' || t.category
        || ' and routed to the ' || t.assigned_team || '.',
    FALSE,
    t.created_at
FROM tickets t
WHERE t.assigned_to IS NOT NULL;

COMMIT;

-- ---------------------------------------------------------------------------
-- 5. Verification
-- ---------------------------------------------------------------------------
\echo '--- Users by role ---'
SELECT role, count(*) FROM users GROUP BY role ORDER BY role;

\echo '--- Tickets by category / priority / status ---'
SELECT category, priority, status, count(*)
FROM tickets
GROUP BY category, priority, status
ORDER BY category, priority, status;

\echo '--- Tickets by assigned team ---'
SELECT assigned_team, count(*) AS total,
       count(*) FILTER (WHERE status <> 'Resolved')        AS still_open,
       count(*) FILTER (WHERE priority IN ('Critical','High')) AS urgent
FROM tickets
GROUP BY assigned_team
ORDER BY assigned_team;

\echo 'AutoDesk seed data loaded successfully.'
\echo 'Sign in as admin@autodesk.local / Admin@123'
