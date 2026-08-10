-- ============================================================
-- JustSpeak Supabase Schema
-- Run this entire file in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'GREETING',
    slots JSONB NOT NULL DEFAULT '{}',
    current_slot_index INTEGER NOT NULL DEFAULT 0,
    confirmation_index INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Submissions table
CREATE TABLE IF NOT EXISTS submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    reference_number TEXT NOT NULL,
    form_data JSONB NOT NULL,
    submitted_at TIMESTAMPTZ DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;

-- Allow all operations (tighten for production)
CREATE POLICY "Allow all sessions" ON sessions FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all submissions" ON submissions FOR ALL USING (true) WITH CHECK (true);

-- Index for quick session lookup
CREATE INDEX IF NOT EXISTS sessions_created_at_idx ON sessions (created_at DESC);
CREATE INDEX IF NOT EXISTS submissions_session_id_idx ON submissions (session_id);
