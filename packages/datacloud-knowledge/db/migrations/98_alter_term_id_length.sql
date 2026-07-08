-- 迁移：将 term_id 相关字段从 VARCHAR(64) 扩展到 VARCHAR(255)
-- 原因：term_id = library_code#term_type_code#term_code 可能超过64字符
-- 执行：psql -h <host> -U <user> -d <db> -f 98_alter_term_id_length.sql

BEGIN;

-- 1. term 表
ALTER TABLE term
    ALTER COLUMN term_id TYPE VARCHAR(255),
    ALTER COLUMN term_code TYPE VARCHAR(255),
    ALTER COLUMN parent_term_id TYPE VARCHAR(255);

-- 2. term_relation 表
ALTER TABLE term_relation
    ALTER COLUMN relation_id TYPE VARCHAR(1000),
    ALTER COLUMN source_term_id TYPE VARCHAR(255),
    ALTER COLUMN target_term_id TYPE VARCHAR(255);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'term_relation'
          AND column_name = 'action_term_id'
    ) THEN
        ALTER TABLE term_relation
            ALTER COLUMN action_term_id TYPE VARCHAR(255);
    END IF;
END $$;

-- 3. term_name 表
ALTER TABLE term_name
    ALTER COLUMN name_id TYPE VARCHAR(255),
    ALTER COLUMN term_id TYPE VARCHAR(255);

-- 4. term_knowledge 表
ALTER TABLE term_knowledge
    ALTER COLUMN knowledge_id TYPE VARCHAR(255),
    ALTER COLUMN term_id TYPE VARCHAR(255);

COMMIT;