-- 存量库迁移：为 term_name 增加 search_scope 列。
-- 新环境由 06_term_name.sql 建表时已包含该列；兼容 OpenGauss，不使用 ADD COLUMN IF NOT EXISTS。

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud' AND table_name = 'term_name' AND column_name = 'search_scope'
    ) THEN
        ALTER TABLE whale_datacloud.term_name ADD COLUMN search_scope JSONB NOT NULL DEFAULT '{}'::jsonb;
    END IF;
END $$;
COMMENT ON COLUMN whale_datacloud.term_name.search_scope IS '名称标签属性，JSONB 格式；存储 scope_user_id/score/use_count/confirmed_count/last_used_at 等';
