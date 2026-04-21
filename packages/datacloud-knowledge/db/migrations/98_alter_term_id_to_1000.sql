-- 迁移：将 term_id 相关字段扩展到 VARCHAR(1000)
-- 说明：仅在当前列长度不是 1000 时执行，幂等安全

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud'
          AND table_name = 'term'
          AND column_name = 'term_id'
          AND character_maximum_length IS DISTINCT FROM 1000
    ) THEN
        ALTER TABLE whale_datacloud.term
            ALTER COLUMN term_id TYPE VARCHAR(1000);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud'
          AND table_name = 'term'
          AND column_name = 'parent_term_id'
          AND character_maximum_length IS DISTINCT FROM 1000
    ) THEN
        ALTER TABLE whale_datacloud.term
            ALTER COLUMN parent_term_id TYPE VARCHAR(1000);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud'
          AND table_name = 'term_relation'
          AND column_name = 'source_term_id'
          AND character_maximum_length IS DISTINCT FROM 1000
    ) THEN
        ALTER TABLE whale_datacloud.term_relation
            ALTER COLUMN source_term_id TYPE VARCHAR(1000);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud'
          AND table_name = 'term_relation'
          AND column_name = 'target_term_id'
          AND character_maximum_length IS DISTINCT FROM 1000
    ) THEN
        ALTER TABLE whale_datacloud.term_relation
            ALTER COLUMN target_term_id TYPE VARCHAR(1000);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud'
          AND table_name = 'term_relation'
          AND column_name = 'action_term_id'
          AND character_maximum_length IS DISTINCT FROM 1000
    ) THEN
        ALTER TABLE whale_datacloud.term_relation
            ALTER COLUMN action_term_id TYPE VARCHAR(1000);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud'
          AND table_name = 'term_relation'
          AND column_name = 'relation_id'
          AND character_maximum_length IS DISTINCT FROM 1000
    ) THEN
        ALTER TABLE whale_datacloud.term_relation
            ALTER COLUMN relation_id TYPE VARCHAR(1000);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud'
          AND table_name = 'term_name'
          AND column_name = 'name_id'
          AND character_maximum_length IS DISTINCT FROM 1000
    ) THEN
        ALTER TABLE whale_datacloud.term_name
            ALTER COLUMN name_id TYPE VARCHAR(1000);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud'
          AND table_name = 'term_name'
          AND column_name = 'term_id'
          AND character_maximum_length IS DISTINCT FROM 1000
    ) THEN
        ALTER TABLE whale_datacloud.term_name
            ALTER COLUMN term_id TYPE VARCHAR(1000);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud'
          AND table_name = 'term_knowledge'
          AND column_name = 'knowledge_id'
          AND character_maximum_length IS DISTINCT FROM 1000
    ) THEN
        ALTER TABLE whale_datacloud.term_knowledge
            ALTER COLUMN knowledge_id TYPE VARCHAR(1000);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud'
          AND table_name = 'term_knowledge'
          AND column_name = 'term_id'
          AND character_maximum_length IS DISTINCT FROM 1000
    ) THEN
        ALTER TABLE whale_datacloud.term_knowledge
            ALTER COLUMN term_id TYPE VARCHAR(1000);
    END IF;
END $$;
