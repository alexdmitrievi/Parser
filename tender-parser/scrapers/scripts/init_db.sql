-- Схема БД для парсера тендеров и бота (Supabase / PostgreSQL)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS tenders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    registry_number TEXT NOT NULL,
    title TEXT NOT NULL,
    nmck NUMERIC,
    customer_name TEXT,
    customer_region TEXT,
    submission_deadline TIMESTAMPTZ,
    law_type TEXT,
    status TEXT DEFAULT 'active',
    source_platform TEXT NOT NULL,
    sources TEXT[] DEFAULT '{}',
    niche_tags TEXT[] DEFAULT '{}',
    description TEXT,
    documents_urls TEXT[] DEFAULT '{}',
    external_url TEXT,
    raw_payload JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT tenders_registry_unique UNIQUE (registry_number)
);

CREATE INDEX IF NOT EXISTS idx_tenders_registry ON tenders(registry_number);
CREATE INDEX IF NOT EXISTS idx_tenders_status ON tenders(status);
CREATE INDEX IF NOT EXISTS idx_tenders_deadline ON tenders(submission_deadline);

CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT NOT NULL,
    niche TEXT,
    keywords TEXT,
    region TEXT,
    nmck_min NUMERIC,
    nmck_max NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subs_user ON subscriptions(telegram_user_id);

CREATE TABLE IF NOT EXISTS bot_state (
    telegram_user_id BIGINT PRIMARY KEY,
    state JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS web_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT NOT NULL UNIQUE,
    telegram_username TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Миграция со старой схемы (если таблица tenders уже была без полей)
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS sources TEXT[] DEFAULT '{}';
