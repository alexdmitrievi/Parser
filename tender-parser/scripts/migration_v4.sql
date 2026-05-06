-- ============================================
-- Migration v4: Production hardening
-- Execute in Supabase SQL Editor
-- ============================================

-- RPC: DB-side aggregation for /api/stats
CREATE OR REPLACE FUNCTION get_tender_stats()
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    result jsonb;
BEGIN
    SELECT jsonb_build_object(
        'total', (SELECT count(*) FROM tenders),
        'platforms', (SELECT count(DISTINCT source_platform) FROM tenders),
        'by_niche', (
            SELECT coalesce(jsonb_object_agg(niche, cnt), '{}'::jsonb)
            FROM (
                SELECT unnest(niche_tags) as niche, count(*) as cnt
                FROM tenders GROUP BY niche
            ) t
        ),
        'by_region', (
            SELECT coalesce(jsonb_object_agg(region, cnt), '{}'::jsonb)
            FROM (
                SELECT coalesce(nullif(trim(customer_region), ''), 'unknown') as region, count(*) as cnt
                FROM tenders GROUP BY region
            ) t
        ),
        'created_last_7_days', (
            SELECT count(*) FROM tenders
            WHERE created_at > now() - interval '7 days'
        )
    ) INTO result;
    RETURN result;
END;
$$;


-- RPC: DB-side aggregation for /api/meta
CREATE OR REPLACE FUNCTION get_tender_meta()
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    result jsonb;
BEGIN
    SELECT jsonb_build_object(
        'niches', (
            SELECT coalesce(jsonb_agg(jsonb_build_object('name', niche, 'count', cnt)), '[]'::jsonb)
            FROM (
                SELECT unnest(niche_tags) as niche, count(*) as cnt
                FROM tenders GROUP BY niche ORDER BY cnt DESC
            ) t
        ),
        'platforms', (
            SELECT coalesce(jsonb_agg(jsonb_build_object('id', platform, 'name', platform, 'count', cnt)), '[]'::jsonb)
            FROM (
                SELECT source_platform as platform, count(*) as cnt
                FROM tenders WHERE source_platform IS NOT NULL AND source_platform != ''
                GROUP BY platform ORDER BY cnt DESC
            ) t
        ),
        'methods', (
            SELECT coalesce(jsonb_agg(jsonb_build_object('id', method, 'name', method, 'count', cnt)), '[]'::jsonb)
            FROM (
                SELECT purchase_method as method, count(*) as cnt
                FROM tenders WHERE purchase_method IS NOT NULL AND purchase_method != ''
                GROUP BY method ORDER BY cnt DESC
            ) t
        )
    ) INTO result;
    RETURN result;
END;
$$;


-- RPC: DB-side aggregation for /api/funding/meta
CREATE OR REPLACE FUNCTION get_funding_meta()
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    result jsonb;
BEGIN
    SELECT jsonb_build_object(
        'total_active', (SELECT count(*) FROM funding_programs WHERE status = 'active'),
        'by_type', (
            SELECT coalesce(jsonb_agg(jsonb_build_object('type', ptype, 'count', cnt)), '[]'::jsonb)
            FROM (
                SELECT program_type as ptype, count(*) as cnt
                FROM funding_programs WHERE status = 'active'
                GROUP BY ptype ORDER BY cnt DESC
            ) t
        ),
        'by_platform', (
            SELECT coalesce(jsonb_agg(jsonb_build_object('platform', plat, 'count', cnt)), '[]'::jsonb)
            FROM (
                SELECT source_platform as plat, count(*) as cnt
                FROM funding_programs WHERE status = 'active'
                GROUP BY plat ORDER BY cnt DESC
            ) t
        )
    ) INTO result;
    RETURN result;
END;
$$;


-- Scrape health log
CREATE TABLE IF NOT EXISTS scrape_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scraper_name TEXT NOT NULL,
    source_group TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success',
    tenders_found INT DEFAULT 0,
    tenders_inserted INT DEFAULT 0,
    error_message TEXT,
    duration_ms INT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_scrape_log_name ON scrape_log(scraper_name);
CREATE INDEX IF NOT EXISTS idx_scrape_log_status ON scrape_log(status);
CREATE INDEX IF NOT EXISTS idx_scrape_log_started ON scrape_log(started_at);


-- Rate limits table (replaces in-memory rate limiter)
CREATE TABLE IF NOT EXISTS rate_limits (
    ip TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    window_start TIMESTAMPTZ DEFAULT NOW(),
    count INT DEFAULT 1,
    PRIMARY KEY (ip, endpoint)
);

CREATE INDEX IF NOT EXISTS idx_rate_limits_window ON rate_limits(window_start);


-- Add customer_name to FTS column for broader search coverage
ALTER TABLE tenders DROP COLUMN IF EXISTS fts CASCADE;
ALTER TABLE tenders ADD COLUMN fts tsvector
    GENERATED ALWAYS AS (
        to_tsvector('russian',
            coalesce(title,'') || ' ' ||
            coalesce(description,'') || ' ' ||
            coalesce(customer_name,'')
        )
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_tenders_fts ON tenders USING GIN(fts);


-- RLS for production use
ALTER TABLE tenders ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON tenders;
CREATE POLICY "Public read" ON tenders FOR SELECT USING (true);
DROP POLICY IF EXISTS "Service insert" ON tenders;
CREATE POLICY "Service insert" ON tenders FOR INSERT WITH CHECK (true);
DROP POLICY IF EXISTS "Service update" ON tenders;
CREATE POLICY "Service update" ON tenders FOR UPDATE USING (true);

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Owner access" ON subscriptions;
CREATE POLICY "Owner access" ON subscriptions FOR ALL USING (true);

ALTER TABLE funding_programs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read funding" ON funding_programs;
CREATE POLICY "Public read funding" ON funding_programs FOR SELECT USING (true);
DROP POLICY IF EXISTS "Service insert funding" ON funding_programs;
CREATE POLICY "Service insert funding" ON funding_programs FOR INSERT WITH CHECK (true);
DROP POLICY IF EXISTS "Service update funding" ON funding_programs;
CREATE POLICY "Service update funding" ON funding_programs FOR UPDATE USING (true);
