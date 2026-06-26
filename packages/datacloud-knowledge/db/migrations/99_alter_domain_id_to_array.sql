-- 将 term.domain_id VARCHAR(64) 改为 domain_ids VARCHAR(64)[]
-- 幂等：重复执行自动跳过
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'term' AND column_name = 'domain_ids'
    ) THEN
        RAISE NOTICE '已迁移，跳过';
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'term' AND column_name = 'domain_id'
    ) THEN
        RAISE NOTICE 'domain_id 列不存在，跳过';
        RETURN;
    END IF;

    ALTER TABLE term ALTER COLUMN domain_id TYPE VARCHAR(64)[] USING ARRAY[domain_id];
    ALTER TABLE term RENAME COLUMN domain_id TO domain_ids;
    ALTER TABLE term ALTER COLUMN domain_ids SET DEFAULT '{}';

    DROP INDEX IF EXISTS idx_term_domain;
    CREATE INDEX IF NOT EXISTS idx_term_domain_ids ON term USING GIN (domain_ids);

    RAISE NOTICE '迁移完成';
END $$;
