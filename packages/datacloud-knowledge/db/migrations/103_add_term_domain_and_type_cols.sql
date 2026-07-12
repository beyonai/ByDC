-- Migration: Add term_domain table, library_id + domain_ids to term_type,
-- and term_type_code columns to term_relation.
-- Idempotent — safe to run multiple times on existing databases.

-- ═══════════════════════════════════════════════════════════════════════════════
-- 1. term_domain — new table replacing domain + domain_library + domain_term_type
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS term_domain (
    domain_id    VARCHAR(64)  NOT NULL PRIMARY KEY,
    domain_code  VARCHAR(64)  NOT NULL,
    domain_name  VARCHAR(255) NOT NULL,
    parent_id    VARCHAR(64),
    library_id   VARCHAR(64)  NOT NULL,
    domain_desc  TEXT,
    created_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_term_domain_library_code UNIQUE (library_id, domain_code),
    CONSTRAINT uq_term_domain_library_name_parent UNIQUE (library_id, parent_id, domain_name)
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 2. term_type — add library_id + domain_ids[], replace UNIQUE constraint
-- ═══════════════════════════════════════════════════════════════════════════════

-- 2a. Add library_id (nullable first, then backfill)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'term_type' AND column_name = 'library_id'
    ) THEN
        ALTER TABLE term_type ADD COLUMN library_id VARCHAR(64);
    END IF;
END $$;

-- 2b. Backfill library_id from term table (pick library with most terms for each type_code)
UPDATE term_type tt
SET library_id = subq.library_id
FROM (
    SELECT
        term_type_code,
        library_id,
        ROW_NUMBER() OVER (PARTITION BY term_type_code ORDER BY cnt DESC) AS rn
    FROM (
        SELECT term_type_code, library_id, COUNT(*) AS cnt
        FROM term
        WHERE library_id IS NOT NULL
        GROUP BY term_type_code, library_id
    ) agg
) subq
WHERE tt.type_code = subq.term_type_code AND subq.rn = 1
  AND tt.library_id IS NULL;

-- 2c. Any remaining NULL → use a fallback (shouldn't happen in practice)
-- If no term rows reference this type_code, set a placeholder
UPDATE term_type SET library_id = 'default' WHERE library_id IS NULL;

-- 2d. Make library_id NOT NULL
ALTER TABLE term_type ALTER COLUMN library_id SET NOT NULL;

-- 2e. Add domain_ids[] array column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'term_type' AND column_name = 'domain_ids'
    ) THEN
        ALTER TABLE term_type ADD COLUMN domain_ids VARCHAR(64)[] NOT NULL DEFAULT '{}';
    END IF;
END $$;

-- 2f. Add GIN index for domain_ids (like term.domain_ids)
CREATE INDEX IF NOT EXISTS idx_term_type_domain_ids ON term_type USING GIN (domain_ids);

-- 2g. Replace UNIQUE constraint: type_code → (library_id, type_code)
DO $$
BEGIN
    -- Drop old unique constraint on type_code alone
    ALTER TABLE term_type DROP CONSTRAINT IF EXISTS uq_term_type_type_code;
    -- Drop if already exists from previous run
    ALTER TABLE term_type DROP CONSTRAINT IF EXISTS uq_term_type_library_type;
    -- Create new unique constraint
    ALTER TABLE term_type ADD CONSTRAINT uq_term_type_library_type UNIQUE (library_id, type_code);
EXCEPTION
    WHEN undefined_object THEN NULL;
END $$;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 3. term_relation — add term_type_code columns + CHECK constraints
-- ═══════════════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'term_relation' AND column_name = 'source_term_type_code'
    ) THEN
        ALTER TABLE term_relation
            ADD COLUMN source_term_type_code VARCHAR(32),
            ADD COLUMN target_term_type_code VARCHAR(32);
    END IF;
END $$;

-- Migrate existing mirror-term relations: if source_term_id is a mirror term
-- (term_type_code = 'term_type'), move it to source_term_type_code
UPDATE term_relation tr
SET source_term_type_code = mt.term_code,
    source_term_id = NULL
FROM term mt
WHERE tr.source_term_id = mt.term_id
  AND mt.term_type_code = 'term_type';

-- Same for target side
UPDATE term_relation tr
SET target_term_type_code = mt.term_code,
    target_term_id = NULL
FROM term mt
WHERE tr.target_term_id = mt.term_id
  AND mt.term_type_code = 'term_type';

-- Add CHECK constraints (drop first in case of re-run)
DO $$
BEGIN
    ALTER TABLE term_relation DROP CONSTRAINT IF EXISTS chk_relation_has_source;
    ALTER TABLE term_relation DROP CONSTRAINT IF EXISTS chk_relation_has_target;
    ALTER TABLE term_relation
        ADD CONSTRAINT chk_relation_has_source CHECK (
            source_term_id IS NOT NULL OR source_term_type_code IS NOT NULL
        ),
        ADD CONSTRAINT chk_relation_has_target CHECK (
            target_term_id IS NOT NULL OR target_term_type_code IS NOT NULL
        );
EXCEPTION
    WHEN undefined_object THEN NULL;
END $$;

-- Make source_term_id/target_term_id nullable (may already be, but ensure)
ALTER TABLE term_relation ALTER COLUMN source_term_id DROP NOT NULL;
ALTER TABLE term_relation ALTER COLUMN target_term_id DROP NOT NULL;
