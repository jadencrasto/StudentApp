-- ============================================================
-- SAIS Database Schema
-- Run this once to set up all tables
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- TABLE: users
-- Stores registered students
-- ============================================================
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       VARCHAR(255) UNIQUE NOT NULL,
    username    VARCHAR(100) UNIQUE NOT NULL,
    full_name   VARCHAR(255),
    hashed_password TEXT NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: assignments
-- Academic tasks: assignments, exams, quizzes, announcements
-- ============================================================
CREATE TABLE assignments (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    title       VARCHAR(500) NOT NULL,
    subject     VARCHAR(255),                          -- "Data Structures", "Physics", etc.
    task_type   VARCHAR(50) CHECK (task_type IN (      -- what kind of task
                    'assignment', 'exam', 'quiz',
                    'project', 'announcement', 'other'
                )) DEFAULT 'assignment',
    description TEXT,
    deadline    DATE,                                  -- extracted or manually set
    priority    VARCHAR(20) CHECK (priority IN (
                    'low', 'medium', 'high'
                )) DEFAULT 'medium',
    status      VARCHAR(30) CHECK (status IN (
                    'pending', 'in_progress', 'completed', 'overdue'
                )) DEFAULT 'pending',

    source_document_id UUID,                           -- linked doc if extracted by AI
    classroom_id       VARCHAR(255),                    -- Google Classroom assignment ID (for dedup on sync)
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_assignments_user_id ON assignments(user_id);
CREATE INDEX idx_assignments_deadline ON assignments(deadline);
CREATE INDEX idx_assignments_status   ON assignments(status);

-- ============================================================
-- TABLE: subjects
-- Master list of subjects a user is enrolled in
-- Used for attendance tracking
-- ============================================================
CREATE TABLE subjects (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,                 -- "Mathematics", "Physics Lab"
    code        VARCHAR(50),                           -- "CS301", "PHY102"
    total_classes INT DEFAULT 0,                       -- updated as classes are logged
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_subjects_user_id ON subjects(user_id);

-- ============================================================
-- TABLE: attendance_records
-- One row per class session per subject
-- ============================================================
CREATE TABLE attendance_records (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id  UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,

    class_date  DATE NOT NULL,
    status      VARCHAR(20) CHECK (status IN (
                    'present', 'absent', 'late', 'excused'
                )) NOT NULL,
    notes       VARCHAR(500),

    created_at  TIMESTAMPTZ DEFAULT NOW(),

    -- Prevent duplicate entries for same subject + same date
    UNIQUE(user_id, subject_id, class_date)
);

CREATE INDEX idx_attendance_user_id    ON attendance_records(user_id);
CREATE INDEX idx_attendance_subject_id ON attendance_records(subject_id);
CREATE INDEX idx_attendance_date       ON attendance_records(class_date);

-- ============================================================
-- TABLE: activities
-- Extracurricular activities (clubs, sports, events, etc.)
-- ============================================================
CREATE TABLE activities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    title           VARCHAR(500) NOT NULL,
    category        VARCHAR(100),                      -- "Sports", "Cultural", "Tech Club"
    activity_date   DATE NOT NULL,
    start_time      TIME,
    end_time        TIME,
    location        VARCHAR(255),
    description     TEXT,
    has_conflict    BOOLEAN DEFAULT FALSE,             -- set by AI conflict checker
    conflict_detail TEXT,                              -- which assignment conflicts

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_activities_user_id ON activities(user_id);
CREATE INDEX idx_activities_date    ON activities(activity_date);

-- ============================================================
-- TABLE: documents
-- Uploaded files (PDF, images, text)
-- Stores raw extracted text + metadata
-- ============================================================
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    original_filename   VARCHAR(500),
    file_type           VARCHAR(50),                   -- "pdf", "image", "txt"
    file_path           TEXT,                          -- where stored on disk/cloud
    raw_text            TEXT,                          -- OCR or direct extracted text

    -- AI extraction results stored as JSON
    extracted_data      JSONB DEFAULT '{}',
    -- Example: { "subject": "Physics", "deadline": "2025-03-10",
    --            "task_type": "assignment", "title": "Wave Optics HW" }

    extraction_status   VARCHAR(30) CHECK (extraction_status IN (
                            'pending', 'processing', 'done', 'failed'
                        )) DEFAULT 'pending',
    extraction_error    TEXT,

    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_documents_user_id ON documents(user_id);

-- ============================================================
-- TABLE: alerts
-- AI-generated warnings and predictions
-- ============================================================
CREATE TABLE alerts (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    alert_type  VARCHAR(50) CHECK (alert_type IN (
                    'overload',          -- 3+ deadlines in 7 days
                    'attendance_low',    -- attendance projected below 75%
                    'activity_conflict', -- activity clashes with deadline
                    'deadline_soon',     -- deadline within 24 hours
                    'custom'
                )) NOT NULL,
    severity    VARCHAR(20) CHECK (severity IN (
                    'info', 'warning', 'critical'
                )) DEFAULT 'warning',
    title       VARCHAR(500) NOT NULL,
    message     TEXT NOT NULL,
    is_read     BOOLEAN DEFAULT FALSE,
    expires_at  DATE,                                  -- auto-dismiss after this date

    -- Optional: link alert to specific records
    related_assignment_id UUID REFERENCES assignments(id) ON DELETE SET NULL,
    related_activity_id   UUID REFERENCES activities(id)  ON DELETE SET NULL,
    related_subject_id    UUID REFERENCES subjects(id)    ON DELETE SET NULL,

    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_user_id  ON alerts(user_id);
CREATE INDEX idx_alerts_is_read  ON alerts(is_read);
CREATE INDEX idx_alerts_type     ON alerts(alert_type);

-- ============================================================
-- HELPER FUNCTION: update updated_at automatically
-- ============================================================
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to tables that have updated_at
CREATE TRIGGER set_updated_at_users
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_assignments
    BEFORE UPDATE ON assignments
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_activities
    BEFORE UPDATE ON activities
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- ============================================================
-- ATTENDANCE VIEW
-- Pre-computed attendance % per user per subject
-- Use this in your API instead of recalculating every time
-- ============================================================
CREATE OR REPLACE VIEW attendance_summary AS
SELECT
    ar.user_id,
    ar.subject_id,
    s.name                                          AS subject_name,
    s.code                                          AS subject_code,
    COUNT(*)                                        AS total_classes,
    COUNT(*) FILTER (WHERE ar.status = 'present')  AS present_count,
    COUNT(*) FILTER (WHERE ar.status = 'late')     AS late_count,
    COUNT(*) FILTER (WHERE ar.status = 'absent')   AS absent_count,
    ROUND(
        (COUNT(*) FILTER (WHERE ar.status IN ('present', 'late'))::NUMERIC
        / NULLIF(COUNT(*), 0)) * 100, 2
    )                                               AS attendance_percentage,
    CASE
        WHEN ROUND(
            (COUNT(*) FILTER (WHERE ar.status IN ('present', 'late'))::NUMERIC
            / NULLIF(COUNT(*), 0)) * 100, 2
        ) < 75 THEN TRUE
        ELSE FALSE
    END                                             AS below_threshold
FROM attendance_records ar
JOIN subjects s ON s.id = ar.subject_id
GROUP BY ar.user_id, ar.subject_id, s.name, s.code;
