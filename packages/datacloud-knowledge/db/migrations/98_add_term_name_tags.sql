-- 存量库迁移：为 term_name 增加 search_scope 列。
-- 新环境由 06_term_name.sql 建表时已包含该列；兼容 OpenGauss，不使用 ADD COLUMN IF NOT EXISTS。

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud' AND table_name = 'term_name' AND column_name = 'search_scope'
    ) THEN
        ALTER TABLE term_name ADD COLUMN search_scope JSONB NOT NULL DEFAULT '{}'::jsonb;
    END IF;
END $$;
COMMENT ON COLUMN term_name.search_scope IS '名称作用域与标签属性，JSONB 格式；字段别名使用 {"scope":"view|object|global","code":"..."} 限定召回范围，也可存储 scope_user_id/score/use_count/confirmed_count/last_used_at 等用户标签';
