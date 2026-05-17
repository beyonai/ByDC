-- 存量库迁移：将 term_relation.relation_category 从旧值（"BUSINESS" / "ONTOLOGY"）
-- 迁移为新值（HAS_FIELD / HAS_OBJECT / HAS_TERM / MANY_TO_ONE）。
--
-- 迁移策略（Phase 1 OWL 统一实现）：
--   1. 若 ext_attrs 包含 "relation_type" 字段，直接使用该值作为新的 relation_category；
--   2. 否则通过 source/target term_id 的 term_type_code 段式推断；
--   3. 无法推断的行记录 WARNING 日志，不做修改。
--
-- 幂等安全：使用 DO $$ 块 + WHERE relation_category IN ('BUSINESS','ONTOLOGY') 确保
--           已迁移的行不会被重复更新；可安全重跑。
--
-- 兼容 OpenGauss / PostgreSQL 12+。

DO $$
DECLARE
    v_row_count           INTEGER := 0;
    v_migrated_count      INTEGER := 0;
    v_skipped_count       INTEGER := 0;
    v_rec                 RECORD;
    v_new_category        VARCHAR(16);
    v_source_term_code    TEXT;
    v_target_term_code    TEXT;
    v_target_type_code    TEXT;
    v_source_type_code    TEXT;
BEGIN
    -- ── 统计待迁移行数 ──────────────────────────────────────────────────────
    SELECT COUNT(*) INTO v_row_count
    FROM term_relation
    WHERE relation_category IN ('BUSINESS', 'ONTOLOGY');

    RAISE NOTICE '待迁移行数: %', v_row_count;

    -- ── 逐行迁移 ────────────────────────────────────────────────────────────
    FOR v_rec IN
        SELECT
            tr.relation_id,
            tr.relation_category AS old_category,
            tr.ext_attrs,
            st.term_code AS source_term_code,
            tt.term_code AS target_term_code,
            st.term_type_code AS source_type_code,
            tt.term_type_code AS target_type_code
        FROM term_relation tr
        LEFT JOIN term st ON st.term_id = tr.source_term_id
        LEFT JOIN term tt ON tt.term_id = tr.target_term_id
        WHERE tr.relation_category IN ('BUSINESS', 'ONTOLOGY')
    LOOP
        v_new_category := NULL;

        -- 规则1：从 ext_attrs.relation_type 读取
        IF v_rec.ext_attrs IS NOT NULL AND v_rec.ext_attrs ? 'relation_type' THEN
            v_new_category := v_rec.ext_attrs ->> 'relation_type';
        END IF;

        -- 规则2：根据 source/target 的 term_type_code 结构推断
        IF v_new_category IS NULL THEN
            v_source_type_code := v_rec.source_type_code;
            v_target_type_code := v_rec.target_type_code;

            -- 2a: target 为 prop → HAS_FIELD（无论是 object→prop 还是 view→prop）
            IF v_target_type_code = 'prop' THEN
                v_new_category := 'HAS_FIELD';

            -- 2b: source 为 view, target 为 object → HAS_OBJECT
            ELSIF v_source_type_code = 'view' AND v_target_type_code = 'object' THEN
                v_new_category := 'HAS_OBJECT';

            -- 2c: source 与 target 同类型且非 prop→prop → HAS_TERM（如 opp_status→opp_status）
            ELSIF v_source_type_code = v_target_type_code
                  AND v_source_type_code NOT IN ('prop', 'object', 'view') THEN
                v_new_category := 'HAS_TERM';

            -- 2d: 两个 object 之间 → MANY_TO_ONE
            ELSIF v_source_type_code = 'object' AND v_target_type_code = 'object' THEN
                v_new_category := 'MANY_TO_ONE';

            -- 2e: 两个 view 之间 → HAS_OBJECT
            ELSIF v_source_type_code = 'view' AND v_target_type_code = 'view' THEN
                v_new_category := 'HAS_OBJECT';
            END IF;
        END IF;

        -- 规则3：仍无法推断 → 跳过并记录
        IF v_new_category IS NULL THEN
            v_skipped_count := v_skipped_count + 1;
            RAISE WARNING '无法推断 relation_category: relation_id=%, old=%, source_type=%, target_type=%',
                v_rec.relation_id,
                v_rec.old_category,
                COALESCE(v_source_type_code, '<NULL>'),
                COALESCE(v_target_type_code, '<NULL>');
            CONTINUE;
        END IF;

        -- 合法关系类别校验
        IF v_new_category NOT IN ('HAS_FIELD', 'HAS_OBJECT', 'HAS_TERM', 'MANY_TO_ONE') THEN
            v_skipped_count := v_skipped_count + 1;
            RAISE WARNING '推断的关系类别非法: relation_id=%, new_category=%, 已跳过',
                v_rec.relation_id, v_new_category;
            CONTINUE;
        END IF;

        -- 执行更新
        UPDATE term_relation
        SET relation_category = v_new_category,
            updated_time = CURRENT_TIMESTAMP
        WHERE relation_id = v_rec.relation_id
          AND relation_category IN ('BUSINESS', 'ONTOLOGY');  -- 二次守卫，避免竞态

        v_migrated_count := v_migrated_count + 1;
    END LOOP;

    RAISE NOTICE '迁移完成: migrated=%, skipped=%',
        v_migrated_count, v_skipped_count;
END $$;

-- ── 更新列注释以反映新取值 ──────────────────────────────────────────────────
COMMENT ON COLUMN term_relation.relation_category IS
    '关系类别：HAS_FIELD=拥有属性, HAS_OBJECT=包含对象, HAS_TERM=拥有术语实例, MANY_TO_ONE=多对一关联';

-- ── 校验查询（注释，手动执行以确认迁移结果）─────────────────────────────────
-- 检查是否仍有旧值：
-- SELECT relation_category, COUNT(*) FROM term_relation GROUP BY relation_category;
-- 预期：无 BUSINESS / ONTOLOGY 行。
--
-- 检查跳过行（若有）：
-- SELECT tr.relation_id, tr.relation_category, st.term_type_code AS source_type, tt.term_type_code AS target_type
-- FROM term_relation tr
-- LEFT JOIN term st ON st.term_id = tr.source_term_id
-- LEFT JOIN term tt ON tt.term_id = tr.target_term_id
-- WHERE tr.relation_category IN ('BUSINESS', 'ONTOLOGY');
