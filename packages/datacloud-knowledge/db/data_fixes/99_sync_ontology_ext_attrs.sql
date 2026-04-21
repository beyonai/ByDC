-- 本体层级冗余同步：根据 term_relation（ONTOLOGY）为 视图/对象/动作 术语填充 ext_attrs.onto。
-- 约定：视图 → object_ids；对象 → action_ids；动作 → function_ids。
-- 可重复执行（幂等）；建议在知识包导入完成后或本体关系变更后执行。

-- 1) 视图术语：ext_attrs.onto.object_ids = 直接包含的对象 term_id 列表
UPDATE term t
SET ext_attrs = (
    CASE
        WHEN COALESCE(t.ext_attrs::text, '{}') IN ('{}', 'null', '') THEN '{"onto":{"object_ids":' || COALESCE(
            (SELECT '[' || string_agg('"' || replace(r.target_term_id, '"', '\"') || '"', ',' ORDER BY r.target_term_id) || ']'
             FROM term_relation r
             JOIN term tt ON tt.term_id = r.target_term_id
             WHERE r.source_term_id = t.term_id AND r.relation_category = 'ONTOLOGY' AND tt.term_type_code = 'ONTOLOGY_OBJ'),
            '[]') || '}}'
        WHEN t.ext_attrs::text ~ '"onto"' THEN regexp_replace(t.ext_attrs::text, '"onto"\s*:\s*\{[^}]*\}',
            '"onto":{"object_ids":' || COALESCE(
                (SELECT '[' || string_agg('"' || replace(r.target_term_id, '"', '\"') || '"', ',' ORDER BY r.target_term_id) || ']'
                 FROM term_relation r
                 JOIN term tt ON tt.term_id = r.target_term_id
                 WHERE r.source_term_id = t.term_id AND r.relation_category = 'ONTOLOGY' AND tt.term_type_code = 'ONTOLOGY_OBJ'),
                '[]') || '}')
        ELSE rtrim(t.ext_attrs::text, '}') || ',"onto":{"object_ids":' || COALESCE(
            (SELECT '[' || string_agg('"' || replace(r.target_term_id, '"', '\"') || '"', ',' ORDER BY r.target_term_id) || ']'
             FROM term_relation r
             JOIN term tt ON tt.term_id = r.target_term_id
             WHERE r.source_term_id = t.term_id AND r.relation_category = 'ONTOLOGY' AND tt.term_type_code = 'ONTOLOGY_OBJ'),
            '[]') || '}}'
    END
)::jsonb
WHERE t.term_type_code = 'ONTOLOGY_VIEW';

-- 2) 对象术语：ext_attrs.onto.action_ids = 直接拥有的动作 term_id 列表
UPDATE term t
SET ext_attrs = (
    CASE
        WHEN COALESCE(t.ext_attrs::text, '{}') IN ('{}', 'null', '') THEN '{"onto":{"action_ids":' || COALESCE(
            (SELECT '[' || string_agg('"' || replace(r.target_term_id, '"', '\"') || '"', ',' ORDER BY r.target_term_id) || ']'
             FROM term_relation r
             JOIN term tt ON tt.term_id = r.target_term_id
             WHERE r.source_term_id = t.term_id AND r.relation_category = 'ONTOLOGY' AND tt.term_type_code = 'ONTOLOGY_ACTION'),
            '[]') || '}}'
        WHEN t.ext_attrs::text ~ '"onto"' THEN regexp_replace(t.ext_attrs::text, '"onto"\s*:\s*\{[^}]*\}',
            '"onto":{"action_ids":' || COALESCE(
                (SELECT '[' || string_agg('"' || replace(r.target_term_id, '"', '\"') || '"', ',' ORDER BY r.target_term_id) || ']'
                 FROM term_relation r
                 JOIN term tt ON tt.term_id = r.target_term_id
                 WHERE r.source_term_id = t.term_id AND r.relation_category = 'ONTOLOGY' AND tt.term_type_code = 'ONTOLOGY_ACTION'),
                '[]') || '}')
        ELSE rtrim(t.ext_attrs::text, '}') || ',"onto":{"action_ids":' || COALESCE(
            (SELECT '[' || string_agg('"' || replace(r.target_term_id, '"', '\"') || '"', ',' ORDER BY r.target_term_id) || ']'
             FROM term_relation r
             JOIN term tt ON tt.term_id = r.target_term_id
             WHERE r.source_term_id = t.term_id AND r.relation_category = 'ONTOLOGY' AND tt.term_type_code = 'ONTOLOGY_ACTION'),
            '[]') || '}}'
    END
)::jsonb
WHERE t.term_type_code = 'ONTOLOGY_OBJ';

-- 3) 动作术语：ext_attrs.onto.function_ids = 直接调用的函数 term_id 列表
UPDATE term t
SET ext_attrs = (
    CASE
        WHEN COALESCE(t.ext_attrs::text, '{}') IN ('{}', 'null', '') THEN '{"onto":{"function_ids":' || COALESCE(
            (SELECT '[' || string_agg('"' || replace(r.target_term_id, '"', '\"') || '"', ',' ORDER BY r.target_term_id) || ']'
             FROM term_relation r
             JOIN term tt ON tt.term_id = r.target_term_id
             WHERE r.source_term_id = t.term_id AND r.relation_category = 'ONTOLOGY' AND tt.term_type_code = 'ONTOLOGY_FUNC'),
            '[]') || '}}'
        WHEN t.ext_attrs::text ~ '"onto"' THEN regexp_replace(t.ext_attrs::text, '"onto"\s*:\s*\{[^}]*\}',
            '"onto":{"function_ids":' || COALESCE(
                (SELECT '[' || string_agg('"' || replace(r.target_term_id, '"', '\"') || '"', ',' ORDER BY r.target_term_id) || ']'
                 FROM term_relation r
                 JOIN term tt ON tt.term_id = r.target_term_id
                 WHERE r.source_term_id = t.term_id AND r.relation_category = 'ONTOLOGY' AND tt.term_type_code = 'ONTOLOGY_FUNC'),
                '[]') || '}')
        ELSE rtrim(t.ext_attrs::text, '}') || ',"onto":{"function_ids":' || COALESCE(
            (SELECT '[' || string_agg('"' || replace(r.target_term_id, '"', '\"') || '"', ',' ORDER BY r.target_term_id) || ']'
             FROM term_relation r
             JOIN term tt ON tt.term_id = r.target_term_id
             WHERE r.source_term_id = t.term_id AND r.relation_category = 'ONTOLOGY' AND tt.term_type_code = 'ONTOLOGY_FUNC'),
            '[]') || '}}'
    END
)::jsonb
WHERE t.term_type_code = 'ONTOLOGY_ACTION';
