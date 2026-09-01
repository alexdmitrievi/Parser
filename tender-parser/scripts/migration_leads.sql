-- ============================================
-- Migration: домен leads (китайские импортёры)
-- Выполнять в Supabase SQL Editor.
--
-- Миграция ИДЕМПОТЕНТНА: повторный запуск ничего не ломает и не теряет данные.
-- Все объекты имеют префикс leads_ и не пересекаются с существующими
-- таблицами (tenders, funding_programs, subscriptions и прочими).
--
-- Применяется только если вы используете LEADS_STORAGE=supabase.
-- По умолчанию домен работает на локальном SQLite и эта миграция не нужна.
-- ============================================

-- ──────────────── Компании ────────────────

CREATE TABLE IF NOT EXISTS leads_companies (
    id               bigserial PRIMARY KEY,
    -- Ключ дедупликации: 'domain:<домен>' либо 'name:<название>|<провинция>'
    dedup_key        text        NOT NULL,
    company_name_en  text        NOT NULL DEFAULT '',
    company_name_zh  text        NOT NULL DEFAULT '',
    province         text        NOT NULL DEFAULT '',
    city             text        NOT NULL DEFAULT '',
    website          text        NOT NULL DEFAULT '',
    domain           text        NOT NULL DEFAULT '',
    phones           text[]      NOT NULL DEFAULT '{}',
    wechat           text        NOT NULL DEFAULT '',
    whatsapp         text        NOT NULL DEFAULT '',
    matched_keywords text[]      NOT NULL DEFAULT '{}',
    profile          text        NOT NULL DEFAULT '',
    industry_guess   text        NOT NULL DEFAULT '',
    source_url       text        NOT NULL DEFAULT '',
    source_name      text        NOT NULL DEFAULT '',
    enrich_status    text        NOT NULL DEFAULT 'pending',
    enrich_note      text        NOT NULL DEFAULT '',
    first_seen       timestamptz NOT NULL DEFAULT now(),
    last_seen        timestamptz NOT NULL DEFAULT now(),
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- Уникальность по ключу дедупликации — на неё опирается upsert.
CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_companies_dedup_key
    ON leads_companies (dedup_key);

CREATE INDEX IF NOT EXISTS idx_leads_companies_profile   ON leads_companies (profile);
CREATE INDEX IF NOT EXISTS idx_leads_companies_province  ON leads_companies (province);
CREATE INDEX IF NOT EXISTS idx_leads_companies_status    ON leads_companies (enrich_status);
CREATE INDEX IF NOT EXISTS idx_leads_companies_domain    ON leads_companies (domain);

-- Колонки вида деятельности и предложений/запросов — отдельными ALTER,
-- чтобы миграция оставалась идемпотентной для уже существующих таблиц.
ALTER TABLE leads_companies ADD COLUMN IF NOT EXISTS country text NOT NULL DEFAULT '';
ALTER TABLE leads_companies ADD COLUMN IF NOT EXISTS activity text NOT NULL DEFAULT '';
ALTER TABLE leads_companies ADD COLUMN IF NOT EXISTS offers   text[] NOT NULL DEFAULT '{}';
ALTER TABLE leads_companies ADD COLUMN IF NOT EXISTS requests text[] NOT NULL DEFAULT '{}';

-- ──────────────── Почты ────────────────

CREATE TABLE IF NOT EXISTS leads_emails (
    id          bigserial PRIMARY KEY,
    company_id  bigint      NOT NULL REFERENCES leads_companies (id) ON DELETE CASCADE,
    email       text        NOT NULL,
    -- role  — обезличенный ящик (info@, sales@, export@): идёт в экспорт
    -- personal — именной: выгружается только с флагом --include-personal
    kind        text        NOT NULL DEFAULT 'role',
    -- Страница, с которой снят адрес, — чтобы находку можно было проверить
    source_url  text        NOT NULL DEFAULT '',
    first_seen  timestamptz NOT NULL DEFAULT now(),
    last_seen   timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_emails_company_email
    ON leads_emails (company_id, email);

CREATE INDEX IF NOT EXISTS idx_leads_emails_company ON leads_emails (company_id);
CREATE INDEX IF NOT EXISTS idx_leads_emails_kind    ON leads_emails (kind);

-- ──────────────── Лог прогонов ────────────────

CREATE TABLE IF NOT EXISTS leads_runs (
    id          bigserial PRIMARY KEY,
    command     text        NOT NULL,
    profile     text        NOT NULL DEFAULT '',
    found       integer     NOT NULL DEFAULT 0,
    inserted    integer     NOT NULL DEFAULT 0,
    updated     integer     NOT NULL DEFAULT 0,
    status      text        NOT NULL DEFAULT 'success',
    note        text        NOT NULL DEFAULT '',
    duration_ms integer     NOT NULL DEFAULT 0,
    started_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_leads_runs_started ON leads_runs (started_at DESC);

-- ──────────────── RLS ────────────────
-- Проект работает с RLS на всех таблицах (см. migration_v4.sql).
-- Домен leads — внутренний инструмент: политик для anon нет, доступ только
-- по service_role, который RLS обходит.

ALTER TABLE leads_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads_emails    ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads_runs      ENABLE ROW LEVEL SECURITY;

-- ──────────────── Сводка для /leads_stats ────────────────

CREATE OR REPLACE FUNCTION get_leads_stats()
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    result jsonb;
BEGIN
    SELECT jsonb_build_object(
        'companies', (SELECT count(*) FROM leads_companies),
        'companies_with_emails', (
            SELECT count(DISTINCT company_id) FROM leads_emails
        ),
        'emails', (SELECT count(*) FROM leads_emails),
        'emails_role', (SELECT count(*) FROM leads_emails WHERE kind = 'role'),
        'emails_personal', (SELECT count(*) FROM leads_emails WHERE kind <> 'role'),
        'by_profile', (
            SELECT coalesce(jsonb_object_agg(p, n), '{}'::jsonb)
            FROM (
                SELECT coalesce(nullif(trim(profile), ''), '(без профиля)') AS p,
                       count(*) AS n
                FROM leads_companies GROUP BY p
            ) t
        ),
        'by_province', (
            SELECT coalesce(jsonb_object_agg(pr, n), '{}'::jsonb)
            FROM (
                SELECT coalesce(nullif(trim(province), ''), '(не определена)') AS pr,
                       count(*) AS n
                FROM leads_companies GROUP BY pr
            ) t
        ),
        'by_enrich_status', (
            SELECT coalesce(jsonb_object_agg(st, n), '{}'::jsonb)
            FROM (
                SELECT enrich_status AS st, count(*) AS n
                FROM leads_companies GROUP BY enrich_status
            ) t
        )
    ) INTO result;
    RETURN result;
END;
$$;
