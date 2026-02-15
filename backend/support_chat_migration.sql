-- ============================================================
-- Support Chat RAG Migration
-- Run in Supabase SQL Editor after prior migrations.
-- ============================================================

-- 1) Knowledge documents
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    source_path   TEXT NOT NULL,
    source_type   TEXT NOT NULL DEFAULT 'markdown',
    content_hash  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active', -- active | archived
    metadata_json JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_slug ON knowledge_documents(slug);
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_status ON knowledge_documents(status);

-- 2) Knowledge chunks (embeddings stored as JSONB float arrays)
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id    UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_index    INTEGER NOT NULL DEFAULT 0,
    content        TEXT NOT NULL,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    embedding      JSONB,  -- float[] as JSON for portability
    metadata_json  JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_knowledge_chunks_doc_idx
    ON knowledge_chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_doc
    ON knowledge_chunks(document_id);

-- 3) Support chat logs
CREATE TABLE IF NOT EXISTS support_chat_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID REFERENCES profiles(id) ON DELETE SET NULL,
    session_id       TEXT NOT NULL,
    question         TEXT NOT NULL,
    answer           TEXT NOT NULL,
    citations        JSONB,
    retrieved_chunks JSONB,
    confidence       DOUBLE PRECISION,
    needs_human      BOOLEAN NOT NULL DEFAULT false,
    user_feedback    TEXT, -- up | down
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_support_chat_logs_user ON support_chat_logs(user_id);
CREATE INDEX IF NOT EXISTS ix_support_chat_logs_session ON support_chat_logs(session_id);

-- RLS policies
ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_chat_logs ENABLE ROW LEVEL SECURITY;

-- Read access for authenticated users (support answers are grounded in product docs)
DROP POLICY IF EXISTS "Knowledge docs readable" ON knowledge_documents;
CREATE POLICY "Knowledge docs readable"
    ON knowledge_documents FOR SELECT
    USING (auth.role() = 'authenticated');

DROP POLICY IF EXISTS "Knowledge chunks readable" ON knowledge_chunks;
CREATE POLICY "Knowledge chunks readable"
    ON knowledge_chunks FOR SELECT
    USING (auth.role() = 'authenticated');

-- Users can read their own support logs
DROP POLICY IF EXISTS "Users read own support logs" ON support_chat_logs;
CREATE POLICY "Users read own support logs"
    ON support_chat_logs FOR SELECT
    USING (user_id = auth.uid());

-- Service role full access (backend writes logs and indexes docs)
DROP POLICY IF EXISTS "Service role full docs" ON knowledge_documents;
CREATE POLICY "Service role full docs"
    ON knowledge_documents FOR ALL
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full chunks" ON knowledge_chunks;
CREATE POLICY "Service role full chunks"
    ON knowledge_chunks FOR ALL
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full support logs" ON support_chat_logs;
CREATE POLICY "Service role full support logs"
    ON support_chat_logs FOR ALL
    USING (true) WITH CHECK (true);
