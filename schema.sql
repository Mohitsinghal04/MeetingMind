-- ============================================================
-- MeetingMind — Database Schema
-- Multi-Agent Productivity Assistant with MCP Integration
-- Run this in Cloud Shell after Day 1 GCP setup
-- ============================================================

-- HOW TO RUN:
-- gcloud sql connect meetingmind-db --user=meetingmind_user --database=meetingmind
-- Then paste everything below

-- NOTE: This schema supports the MCP-wrapped database operations.
-- MCP servers (calendar, tasks, notes) use these tables via db_tools.py

-- ── CREATE TABLES ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS meetings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transcript  TEXT,
    summary     TEXT,
    session_id  VARCHAR(255),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id  UUID REFERENCES meetings(id) ON DELETE SET NULL,
    task_name   TEXT NOT NULL,
    owner       VARCHAR(255) DEFAULT 'Unassigned',
    deadline    VARCHAR(255) DEFAULT 'Not specified',
    priority    VARCHAR(50)  DEFAULT 'Medium',
    status      VARCHAR(50)  DEFAULT 'Pending',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       VARCHAR(500),
    content     TEXT,
    meeting_id  UUID REFERENCES meetings(id) ON DELETE SET NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memory (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  VARCHAR(255),
    key         VARCHAR(255),
    value       TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, key)
);

-- ── INDEXES ──────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_owner    ON tasks(LOWER(owner));
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_notes_title    ON notes(LOWER(title));
CREATE INDEX IF NOT EXISTS idx_memory_session ON memory(session_id);
CREATE INDEX IF NOT EXISTS idx_meetings_session ON meetings(session_id);

-- ── SEED DATA (for demo — makes DuplicateCheck & NotesAgent useful) ──

INSERT INTO meetings (id, transcript, summary, session_id, created_at)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'In our Q2 planning meeting, we discussed the mobile app launch timeline. Priya will lead design, Mohit handles backend. Budget of 500K was approved by finance. Launch date set for end of Q2. We also need to set up the architecture this week.',
    'Q2 planning session. Mobile app launch confirmed for end of Q2. Budget 500K approved. Priya leads design, Mohit leads backend. Architecture setup needed urgently.',
    'demo-session',
    NOW() - INTERVAL '7 days'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO notes (id, title, content, meeting_id, created_at)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    'Q2 Planning Session — Key Decisions',
    'Mobile app launch set for end of Q2. Budget approved at 500K. Team of 4 assigned. Priya leads design, Mohit handles backend. Launch blocked on architecture setup. Client prefers weekly status updates every Monday.',
    '00000000-0000-0000-0000-000000000001',
    NOW() - INTERVAL '7 days'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO tasks (id, meeting_id, task_name, owner, deadline, priority, status, created_at)
VALUES
    (
        '00000000-0000-0000-0000-000000000003',
        '00000000-0000-0000-0000-000000000001',
        'Set up mobile app backend architecture',
        'Mohit',
        '2026-04-01',
        'High',
        'In Progress',
        NOW() - INTERVAL '7 days'
    ),
    (
        '00000000-0000-0000-0000-000000000004',
        '00000000-0000-0000-0000-000000000001',
        'Create UI wireframes for mobile app',
        'Priya',
        '2026-03-30',
        'High',
        'Pending',
        NOW() - INTERVAL '7 days'
    ),
    (
        '00000000-0000-0000-0000-000000000005',
        '00000000-0000-0000-0000-000000000001',
        'Get final budget sign-off from finance',
        'Mohit',
        '2026-03-28',
        'High',
        'Pending',
        NOW() - INTERVAL '7 days'
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO memory (id, session_id, key, value, created_at)
VALUES
    (
        '00000000-0000-0000-0000-000000000006',
        'demo-session',
        'team_leads',
        'Mohit is the backend lead. Priya is the design lead.',
        NOW() - INTERVAL '7 days'
    ),
    (
        '00000000-0000-0000-0000-000000000007',
        'demo-session',
        'project_name',
        'Mobile app launch project for Q2 2026',
        NOW() - INTERVAL '7 days'
    ),
    (
        '00000000-0000-0000-0000-000000000008',
        'demo-session',
        'client_preference',
        'Client prefers weekly status updates every Monday morning',
        NOW() - INTERVAL '7 days'
    )
ON CONFLICT (session_id, key) DO NOTHING;

-- ── VERIFY ───────────────────────────────────────────────────

SELECT 'meetings' as table_name, COUNT(*) as rows FROM meetings
UNION ALL
SELECT 'tasks',   COUNT(*) FROM tasks
UNION ALL
SELECT 'notes',   COUNT(*) FROM notes
UNION ALL
SELECT 'memory',  COUNT(*) FROM memory;

-- Expected output:
-- meetings | 1
-- tasks    | 3
-- notes    | 1
-- memory   | 3
