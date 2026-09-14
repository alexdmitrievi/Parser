-- ============================================================
-- TenderPars — Production Migration v3
-- Fixes: indexes, constraints, FTS cleanup, RLS security
-- Run: via Supabase SQL Editor on production database
-- ============================================================

-- 1. INSTALL pg_trgm for trigram indexes (required for ILIKE performance)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. TRIGRAM INDEXES — fix full-table scans on all ILIKE queries
CREATE INDEX IF NOT EXISTS idx_tenders_title_trgm    ON tenders USING GIN(title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tenders_desc_trgm     ON tenders USING GIN(description gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tenders_cust_trgm     ON tenders USING GIN(customer_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tenders_region_trgm   ON tenders USING GIN(customer_region gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_funding_name_trgm     ON funding_programs USING GIN(program_name gin_trgm_ops);

-- 3. MISSING PERFORMANCE INDEXES
CREATE INDEX IF NOT EXISTS idx_tenders_publish       ON tenders(publish_date);
CREATE INDEX IF NOT EXISTS idx_tenders_law           ON tenders(law_type);
CREATE INDEX IF NOT EXISTS idx_tenders_purchase      ON tenders(purchase_method);
CREATE INDEX IF NOT EXISTS idx_funding_amount_min    ON funding_programs(amount_min);
CREATE INDEX IF NOT EXISTS idx_funding_deadline      ON funding_programs(deadline);
CREATE INDEX IF NOT EXISTS idx_notif_tender          ON notifications_log(tender_id);
CREATE INDEX IF NOT EXISTS idx_subs_user_active      ON subscriptions(telegram_user_id, is_active);

-- 4. DATA INTEGRITY — FK constraints on user-scoped tables
ALTER TABLE subscriptions 
    ADD CONSTRAINT IF NOT EXISTS fk_subs_user 
    FOREIGN KEY (telegram_user_id) REFERENCES bot_users(telegram_user_id) ON DELETE CASCADE;

ALTER TABLE favorites 
    ADD CONSTRAINT IF NOT EXISTS fk_fav_user 
    FOREIGN KEY (telegram_user_id) REFERENCES bot_users(telegram_user_id) ON DELETE CASCADE;

ALTER TABLE bot_state 
    ADD CONSTRAINT IF NOT EXISTS fk_state_user 
    FOREIGN KEY (telegram_user_id) REFERENCES bot_users(telegram_user_id) ON DELETE CASCADE;

-- 5. NOT NULL constraint for required field
ALTER TABLE funding_programs ALTER COLUMN program_type SET NOT NULL;

-- 6. DROP DEAD WEIGHT — FTS columns and indexes (never queried, write overhead)
-- Uncomment if FTS is confirmed unused:
-- DROP INDEX IF EXISTS idx_tenders_fts;
-- DROP INDEX IF EXISTS idx_funding_fts;
-- ALTER TABLE tenders DROP COLUMN IF EXISTS fts;
-- ALTER TABLE funding_programs DROP COLUMN IF EXISTS fts;

-- 7. DROP REDUNDANT INDEX — UNIQUE constraint already creates one
-- DROP INDEX IF EXISTS idx_tenders_platform_reg;

-- 8. RLS SECURITY FIX — proper policies (replace all USING(true))
-- Drop all existing policies first
DO $$ DECLARE r RECORD; BEGIN
    FOR r IN SELECT policyname, tablename FROM pg_policies WHERE schemaname = 'public'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', r.policyname, r.tablename);
    END LOOP;
END $$;

-- Public tables: read-only for everyone
CREATE POLICY "public_read_tenders"       ON tenders           FOR SELECT USING (true);
CREATE POLICY "public_read_funding"       ON funding_programs  FOR SELECT USING (true);

-- Service role only for mutations on public tables
CREATE POLICY "service_manage_tenders"    ON tenders           FOR ALL 
    USING (auth.role() = 'service_role') 
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_manage_funding"    ON funding_programs  FOR ALL 
    USING (auth.role() = 'service_role') 
    WITH CHECK (auth.role() = 'service_role');

-- User-scoped tables: isolate by auth.uid() or telegram_user_id
-- Note: This assumes the JWT contains sub = telegram_user_id when users authenticate
-- If using anon key, service_role can still access via bypass
CREATE POLICY "user_own_subscriptions"    ON subscriptions     FOR SELECT 
    USING (auth.role() = 'service_role' OR telegram_user_id = (auth.jwt()->>'sub')::bigint);

CREATE POLICY "service_manage_subs"       ON subscriptions     FOR ALL 
    USING (auth.role() = 'service_role') 
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "user_own_favorites"        ON favorites         FOR SELECT 
    USING (auth.role() = 'service_role' OR telegram_user_id = (auth.jwt()->>'sub')::bigint);

CREATE POLICY "service_manage_favorites"  ON favorites         FOR ALL 
    USING (auth.role() = 'service_role') 
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "user_own_bot_state"        ON bot_state         FOR SELECT 
    USING (auth.role() = 'service_role' OR telegram_user_id = (auth.jwt()->>'sub')::bigint);

CREATE POLICY "service_manage_bot_state"  ON bot_state         FOR ALL 
    USING (auth.role() = 'service_role') 
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "user_own_bot_users"        ON bot_users         FOR SELECT 
    USING (auth.role() = 'service_role' OR telegram_user_id = (auth.jwt()->>'sub')::bigint);

CREATE POLICY "service_manage_bot_users"  ON bot_users         FOR ALL 
    USING (auth.role() = 'service_role') 
    WITH CHECK (auth.role() = 'service_role');

-- System tables: service role only
CREATE POLICY "service_manage_notif_log"  ON notifications_log FOR ALL 
    USING (auth.role() = 'service_role') 
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_manage_snapshots"  ON tender_snapshots  FOR ALL 
    USING (auth.role() = 'service_role') 
    WITH CHECK (auth.role() = 'service_role');

-- Add DELETE policy for funding_programs (was missing)
CREATE POLICY "service_delete_funding"    ON funding_programs  FOR DELETE 
    USING (auth.role() = 'service_role');
