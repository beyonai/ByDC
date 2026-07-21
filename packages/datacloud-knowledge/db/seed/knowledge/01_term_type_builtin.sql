-- 系统内置术语类型预置数据
-- 使用 INSERT ... SELECT WHERE NOT EXISTS 保证幂等，可重复执行，兼容 OpenGauss

-- ── 本体术语（type_category = 3）────────────────────────────────────────────────────────────────────────
INSERT INTO term_type (type_code, type_name, type_desc, type_category, is_builtin, library_id)
SELECT 'view', '视图', '本体-视图类型，对应数据分析场景，包含多个对象及其关联关系', 3, TRUE, '_system'
WHERE NOT EXISTS (SELECT 1 FROM term_type WHERE type_code = 'view');

INSERT INTO term_type (type_code, type_name, type_desc, type_category, is_builtin, library_id)
SELECT 'object', '对象', '本体-对象类型，对应业务实体，如客户、合同、组织', 3, TRUE, '_system'
WHERE NOT EXISTS (SELECT 1 FROM term_type WHERE type_code = 'object');

INSERT INTO term_type (type_code, type_name, type_desc, type_category, is_builtin, library_id)
SELECT 'action', '动作', '本体-动作类型，对应业务操作，如查询、提交、审批', 3, TRUE, '_system'
WHERE NOT EXISTS (SELECT 1 FROM term_type WHERE type_code = 'action');

INSERT INTO term_type (type_code, type_name, type_desc, type_category, is_builtin, library_id)
SELECT 'func', '函数', '本体-函数类型，对应可调用的原子函数，如聚合、查询函数', 3, TRUE, '_system'
WHERE NOT EXISTS (SELECT 1 FROM term_type WHERE type_code = 'func');

INSERT INTO term_type (type_code, type_name, type_desc, type_category, is_builtin, library_id)
SELECT 'param', '参数', '本体-参数类型，对应动作或函数的输入/输出参数', 3, TRUE, '_system'
WHERE NOT EXISTS (SELECT 1 FROM term_type WHERE type_code = 'param');

INSERT INTO term_type (type_code, type_name, type_desc, type_category, is_builtin, library_id)
SELECT 'prop', '属性', '本体-属性类型，对应对象的字段/属性描述', 3, TRUE, '_system'
WHERE NOT EXISTS (SELECT 1 FROM term_type WHERE type_code = 'prop');

-- ── 元类型与系统库预置数据 ───────────────────────────────────────────────────────────────────────────────
INSERT INTO term_type (type_code, type_name, type_desc, type_category, is_builtin, library_id)
SELECT 'term_type', '术语类型', '术语类型的元类型，自引用', 3, TRUE, '_system'
WHERE NOT EXISTS (SELECT 1 FROM term_type WHERE type_code = 'term_type');

INSERT INTO term_library (library_id, library_code, library_name)
SELECT '_system', '_system', '系统内置术语库'
WHERE NOT EXISTS (SELECT 1 FROM term_library WHERE library_code = '_system');

-- ── 系统内置术语类型对应术语行 ───────────────────────────────────────────────────────────────────────────
INSERT INTO term (
    term_id,
    term_code,
    term_name,
    domain_ids,
    term_type_code,
    library_id,
    term_tags
)
SELECT '_system#term_type#view', 'view', '视图', ARRAY['_system'], 'term_type', '_system', '{}'::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM term
    WHERE term_id = '_system#term_type#view'
);

INSERT INTO term (
    term_id,
    term_code,
    term_name,
    domain_ids,
    term_type_code,
    library_id,
    term_tags
)
SELECT '_system#term_type#object', 'object', '对象', ARRAY['_system'], 'term_type', '_system', '{}'::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM term
    WHERE term_id = '_system#term_type#object'
);

INSERT INTO term (
    term_id,
    term_code,
    term_name,
    domain_ids,
    term_type_code,
    library_id,
    term_tags
)
SELECT '_system#term_type#action', 'action', '动作', ARRAY['_system'], 'term_type', '_system', '{}'::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM term
    WHERE term_id = '_system#term_type#action'
);

INSERT INTO term (
    term_id,
    term_code,
    term_name,
    domain_ids,
    term_type_code,
    library_id,
    term_tags
)
SELECT '_system#term_type#func', 'func', '函数', ARRAY['_system'], 'term_type', '_system', '{}'::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM term
    WHERE term_id = '_system#term_type#func'
);

INSERT INTO term (
    term_id,
    term_code,
    term_name,
    domain_ids,
    term_type_code,
    library_id,
    term_tags
)
SELECT '_system#term_type#param', 'param', '参数', ARRAY['_system'], 'term_type', '_system', '{}'::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM term
    WHERE term_id = '_system#term_type#param'
);

INSERT INTO term (
    term_id,
    term_code,
    term_name,
    domain_ids,
    term_type_code,
    library_id,
    term_tags
)
SELECT '_system#term_type#prop', 'prop', '属性', ARRAY['_system'], 'term_type', '_system', '{}'::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM term
    WHERE term_id = '_system#term_type#prop'
);

INSERT INTO term (
    term_id,
    term_code,
    term_name,
    domain_ids,
    term_type_code,
    library_id,
    term_tags
)
SELECT '_system#term_type#employee', 'employee', '员工', ARRAY['_system'], 'term_type', '_system', '{}'::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM term
    WHERE term_id = '_system#term_type#employee'
);

INSERT INTO term (
    term_id,
    term_code,
    term_name,
    domain_ids,
    term_type_code,
    library_id,
    term_tags
)
SELECT '_system#term_type#general', 'general', '通用', ARRAY['_system'], 'term_type', '_system', '{}'::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM term
    WHERE term_id = '_system#term_type#general'
);

INSERT INTO term (
    term_id,
    term_code,
    term_name,
    domain_ids,
    term_type_code,
    library_id,
    term_tags
)
SELECT '_system#term_type#term_type', 'term_type', '术语类型', ARRAY['_system'], 'term_type', '_system', '{}'::jsonb
WHERE NOT EXISTS (
    SELECT 1
    FROM term
    WHERE term_id = '_system#term_type#term_type'
);
