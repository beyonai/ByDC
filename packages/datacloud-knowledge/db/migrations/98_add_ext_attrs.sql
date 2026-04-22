-- 存量库迁移：为 term、term_relation 增加扩展属性列 ext_attrs。
-- 新环境由 04_term.sql / 05_term_relation.sql 建表时已包含该列；兼容 OpenGauss，不使用 ADD COLUMN IF NOT EXISTS。

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud' AND table_name = 'term' AND column_name = 'ext_attrs'
    ) THEN
        ALTER TABLE term ADD COLUMN ext_attrs JSONB NOT NULL DEFAULT '{}'::jsonb;
    END IF;
END $$;
COMMENT ON COLUMN term.ext_attrs IS '自定义扩展属性，JSON 键值对，供业务/产品扩展；与 term_tags（标签、别名）分离';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud' AND table_name = 'term_relation' AND column_name = 'ext_attrs'
    ) THEN
        ALTER TABLE term_relation ADD COLUMN ext_attrs JSONB NOT NULL DEFAULT '{}'::jsonb;
    END IF;
END $$;
COMMENT ON COLUMN term_relation.ext_attrs IS '自定义扩展属性，JSON 键值对，供业务/产品扩展';
