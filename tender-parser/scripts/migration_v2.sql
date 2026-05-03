-- ============================================
-- Миграция v2 — Парсер Тендеров (Supabase)
-- Выполнить в Supabase SQL Editor
-- Добавляет: tender_snapshots, favorites, индексы, RLS
-- ============================================

-- 1. Таблица снимков тендеров (аудит)
CREATE TABLE IF NOT EXISTS tender_snapshots (
    id BIGSERIAL PRIMARY KEY,
    registry_number TEXT NOT NULL,
    source_platform TEXT NOT NULL,
    snapshot_data JSONB DEFAULT '{}',
    captured_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_snapshots_registry ON tender_snapshots(registry_number, source_platform);
CREATE INDEX IF NOT EXISTS idx_snapshots_captured ON tender_snapshots(captured_at);

-- 2. Таблица избранного (синхронизация между устройствами)
CREATE TABLE IF NOT EXISTS favorites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT,
    tender_id UUID NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(telegram_user_id, tender_id)
);

CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_favorites_tender ON favorites(tender_id);

-- 3. Индекс на original_url для быстрой дедупликации
CREATE INDEX IF NOT EXISTS idx_tenders_url ON tenders(original_url);

-- 4. Индекс на source_platform + registry_number для быстрых lookup'ов
CREATE INDEX IF NOT EXISTS idx_tenders_platform_reg ON tenders(source_platform, registry_number);

-- 5. RLS (Row Level Security) — безопасность данных
ALTER TABLE tenders ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE bot_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE bot_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE funding_programs ENABLE ROW LEVEL SECURITY;
ALTER TABLE tender_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE favorites ENABLE ROW LEVEL SECURITY;

-- Политики: публичный SELECT для анонимных пользователей, INSERT/UPDATE/DELETE для service_role
CREATE POLICY "Public read tenders" ON tenders FOR SELECT USING (true);
CREATE POLICY "Service insert tenders" ON tenders FOR INSERT WITH CHECK (true);
CREATE POLICY "Service update tenders" ON tenders FOR UPDATE USING (true);
CREATE POLICY "Service delete tenders" ON tenders FOR DELETE USING (true);

CREATE POLICY "Public read funding" ON funding_programs FOR SELECT USING (true);
CREATE POLICY "Service insert funding" ON funding_programs FOR INSERT WITH CHECK (true);
CREATE POLICY "Service update funding" ON funding_programs FOR UPDATE USING (true);

CREATE POLICY "User own subscriptions" ON subscriptions FOR SELECT USING (true);
CREATE POLICY "Service manage subscriptions" ON subscriptions FOR ALL USING (true);

CREATE POLICY "User own favorites" ON favorites FOR SELECT USING (true);
CREATE POLICY "Service manage favorites" ON favorites FOR ALL USING (true);

CREATE POLICY "Service manage notifications" ON notifications_log FOR ALL USING (true);

CREATE POLICY "User own state" ON bot_state FOR SELECT USING (true);
CREATE POLICY "Service manage state" ON bot_state FOR ALL USING (true);

CREATE POLICY "User own profile" ON bot_users FOR SELECT USING (true);
CREATE POLICY "Service manage users" ON bot_users FOR ALL USING (true);

CREATE POLICY "Service manage snapshots" ON tender_snapshots FOR ALL USING (true);
