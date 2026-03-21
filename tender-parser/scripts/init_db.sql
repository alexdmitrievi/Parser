-- ============================================
-- Парсер Тендеров — Инициализация БД (Supabase)
-- Выполнить в Supabase SQL Editor
-- ============================================

-- Тендеры
CREATE TABLE IF NOT EXISTS tenders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_platform TEXT NOT NULL,
    registry_number TEXT,
    law_type TEXT,
    purchase_method TEXT,
    title TEXT NOT NULL,
    description TEXT,
    customer_name TEXT,
    customer_inn TEXT,
    customer_region TEXT,
    okpd2_codes TEXT[] DEFAULT '{}',
    nmck NUMERIC(15,2),
    currency TEXT DEFAULT 'RUB',
    publish_date TIMESTAMPTZ,
    submission_deadline TIMESTAMPTZ,
    auction_date TIMESTAMPTZ,
    status TEXT DEFAULT 'active',
    documents_urls JSONB DEFAULT '[]',
    contact_info JSONB DEFAULT '{}',
    original_url TEXT,
    raw_data JSONB,
    niche_tags TEXT[] DEFAULT '{}',
    sources TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(source_platform, registry_number)
);

ALTER TABLE tenders ADD COLUMN IF NOT EXISTS sources TEXT[] DEFAULT '{}';

-- Полнотекстовый поиск (русский)
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (
        to_tsvector('russian', coalesce(title,'') || ' ' || coalesce(description,''))
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_tenders_fts ON tenders USING GIN(fts);
CREATE INDEX IF NOT EXISTS idx_tenders_status ON tenders(status);
CREATE INDEX IF NOT EXISTS idx_tenders_deadline ON tenders(submission_deadline);
CREATE INDEX IF NOT EXISTS idx_tenders_nmck ON tenders(nmck);
CREATE INDEX IF NOT EXISTS idx_tenders_okpd2 ON tenders USING GIN(okpd2_codes);
CREATE INDEX IF NOT EXISTS idx_tenders_niche ON tenders USING GIN(niche_tags);
CREATE INDEX IF NOT EXISTS idx_tenders_region ON tenders(customer_region);
CREATE INDEX IF NOT EXISTS idx_tenders_created ON tenders(created_at);

-- Автообновление updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tenders_updated_at ON tenders;
CREATE TRIGGER tenders_updated_at
    BEFORE UPDATE ON tenders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- Подписки
CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT NOT NULL,
    name TEXT,
    keywords TEXT[] DEFAULT '{}',
    okpd2_prefixes TEXT[] DEFAULT '{}',
    regions TEXT[] DEFAULT '{}',
    min_nmck NUMERIC(15,2),
    max_nmck NUMERIC(15,2),
    law_types TEXT[] DEFAULT '{}',
    niche_tags TEXT[] DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subs_user ON subscriptions(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_subs_active ON subscriptions(is_active);


-- Лог уведомлений
CREATE TABLE IF NOT EXISTS notifications_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID REFERENCES subscriptions(id) ON DELETE CASCADE,
    tender_id UUID REFERENCES tenders(id) ON DELETE CASCADE,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(subscription_id, tender_id)
);


-- Пользователи бота
CREATE TABLE IF NOT EXISTS bot_users (
    telegram_user_id BIGINT PRIMARY KEY,
    username TEXT DEFAULT '',
    first_name TEXT DEFAULT '',
    language TEXT DEFAULT 'ru',
    is_premium BOOLEAN DEFAULT FALSE,
    max_subscriptions INT DEFAULT 3,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Состояние диалогов бота (wizard и т.п.; опционально — handler может использовать callback_data)
CREATE TABLE IF NOT EXISTS bot_state (
    telegram_user_id BIGINT PRIMARY KEY,
    state TEXT DEFAULT '',
    data JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);


-- RLS (Row Level Security) — опционально для production
-- ALTER TABLE tenders ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Public read" ON tenders FOR SELECT USING (true);
