-- 存量库迁移：为 term_library / term 增加全局唯一编码列（library_code / term_code）；
-- 可重复执行（兼容 OpenGauss，不使用 ADD COLUMN IF NOT EXISTS）。

-- ── 1. term_library.library_code ───────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud' AND table_name = 'term_library' AND column_name = 'library_code'
    ) THEN
        ALTER TABLE term_library ADD COLUMN library_code VARCHAR(32);
    END IF;
END $$;

UPDATE term_library
SET library_code = 'L' || UPPER(SUBSTRING(MD5(COALESCE(library_id, '')), 1, 31))
WHERE library_code IS NULL;

ALTER TABLE term_library
    ALTER COLUMN library_code SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_term_library_library_code'
          AND conrelid = 'term_library'::regclass
    ) THEN
        ALTER TABLE term_library
            ADD CONSTRAINT uq_term_library_library_code UNIQUE (library_code);
    END IF;
END $$;

ALTER TABLE term_library DROP CONSTRAINT IF EXISTS chk_term_library_library_code;

COMMENT ON COLUMN term_library.library_code IS '术语库编码，全局唯一';

-- ── 2. term_type：卸掉历史格式 CHECK（若有）────────────────────────────────
ALTER TABLE term_type DROP CONSTRAINT IF EXISTS chk_term_type_type_code;

-- ── 3. term.term_code ─────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud' AND table_name = 'term' AND column_name = 'term_code'
    ) THEN
        ALTER TABLE term ADD COLUMN term_code VARCHAR(64);
    END IF;
END $$;

UPDATE term
SET term_code = 'T' || UPPER(SUBSTRING(MD5(COALESCE(term_id, '')), 1, 63))
WHERE term_code IS NULL;

ALTER TABLE term
    ALTER COLUMN term_code SET NOT NULL;

ALTER TABLE term DROP CONSTRAINT IF EXISTS uq_term_term_code;

ALTER TABLE term DROP CONSTRAINT IF EXISTS chk_term_term_code;

COMMENT ON COLUMN term.term_code IS '术语编码';
