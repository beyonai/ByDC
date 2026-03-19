-- 存量库迁移：为 term_library / term 增加全局唯一编码列（library_code / term_code）；
-- term_type 已有 type_code 唯一，仅补充格式约束。
-- 可重复执行（兼容 OpenGauss，不使用 ADD COLUMN IF NOT EXISTS）；已有数据按规则回填以满足 CHECK。

-- ── 1. term_library.library_code ───────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud' AND table_name = 'term_library' AND column_name = 'library_code'
    ) THEN
        ALTER TABLE whale_datacloud.term_library ADD COLUMN library_code VARCHAR(32);
    END IF;
END $$;

UPDATE whale_datacloud.term_library
SET library_code = 'L' || UPPER(SUBSTRING(MD5(COALESCE(library_id, '')), 1, 31))
WHERE library_code IS NULL;

ALTER TABLE whale_datacloud.term_library
    ALTER COLUMN library_code SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_term_library_library_code'
          AND conrelid = 'whale_datacloud.term_library'::regclass
    ) THEN
        ALTER TABLE whale_datacloud.term_library
            ADD CONSTRAINT uq_term_library_library_code UNIQUE (library_code);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_term_library_library_code'
          AND conrelid = 'whale_datacloud.term_library'::regclass
    ) THEN
        ALTER TABLE whale_datacloud.term_library
            ADD CONSTRAINT chk_term_library_library_code
            CHECK (library_code ~ '^[A-Z][A-Z0-9_]{1,31}$');
    END IF;
END $$;

COMMENT ON COLUMN whale_datacloud.term_library.library_code IS '术语库编码，全局唯一，大写字母+数字+下划线';

-- ── 2. term_type：仅补充 type_code 格式约束（type_code 已 UNIQUE）────────────
-- 允许首字母大小写及后续字母数字下划线，兼容 camelCase/snake_case（如 orgName、period_type）
ALTER TABLE whale_datacloud.term_type DROP CONSTRAINT IF EXISTS chk_term_type_type_code;
ALTER TABLE whale_datacloud.term_type
    ADD CONSTRAINT chk_term_type_type_code
    CHECK (type_code ~ '^[A-Za-z][A-Za-z0-9_]{1,31}$');

-- ── 3. term.term_code ─────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud' AND table_name = 'term' AND column_name = 'term_code'
    ) THEN
        ALTER TABLE whale_datacloud.term ADD COLUMN term_code VARCHAR(64);
    END IF;
END $$;

UPDATE whale_datacloud.term
SET term_code = CASE
    WHEN COALESCE(term_id, '') ~ '^[A-Za-z]'
    THEN UPPER(SUBSTRING(REGEXP_REPLACE(term_id, '[^A-Za-z0-9_]', '_', 'g'), 1, 64))
    ELSE 'T' || UPPER(SUBSTRING(MD5(term_id), 1, 63))
END
WHERE term_code IS NULL;

ALTER TABLE whale_datacloud.term
    ALTER COLUMN term_code SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_term_term_code'
          AND conrelid = 'whale_datacloud.term'::regclass
    ) THEN
        ALTER TABLE whale_datacloud.term
            ADD CONSTRAINT uq_term_term_code UNIQUE (term_code);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_term_term_code'
          AND conrelid = 'whale_datacloud.term'::regclass
    ) THEN
        ALTER TABLE whale_datacloud.term
            ADD CONSTRAINT chk_term_term_code
            CHECK (term_code ~ '^[A-Za-z][A-Za-z0-9_]{1,63}$');
    END IF;
END $$;

-- 存量库：若约束已存在且为旧规则，需 DROP 后重新 ADD（与 term_type 一致）
ALTER TABLE whale_datacloud.term DROP CONSTRAINT IF EXISTS chk_term_term_code;
ALTER TABLE whale_datacloud.term
    ADD CONSTRAINT chk_term_term_code
    CHECK (term_code ~ '^[A-Za-z][A-Za-z0-9_]{1,63}$');

COMMENT ON COLUMN whale_datacloud.term.term_code IS '术语编码，全局唯一，首字母+字母数字下划线';
