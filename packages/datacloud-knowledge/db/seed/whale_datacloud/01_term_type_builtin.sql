-- 系统内置术语类型预置数据
-- 使用 ON CONFLICT DO NOTHING 保证幂等，可重复执行

INSERT INTO whale_datacloud.term_type
    (type_code, type_name, type_desc, type_category, is_builtin)
VALUES

    -- ── 字典术语（type_category = 2）────────────────────────────────────────
    ('GENERAL',         '通用',   '通用字典/枚举类术语，如状态、类别等',                         2, TRUE),

    -- ── 本体术语（type_category = 3）────────────────────────────────────────
    ('ONTOLOGY_VIEW',   '视图',   '本体-视图类型，对应数据分析场景，包含多个对象及其关联关系',   3, TRUE),
    ('ONTOLOGY_OBJ',    '对象',   '本体-对象类型，对应业务实体，如客户、合同、组织',             3, TRUE),
    ('ONTOLOGY_ACTION', '动作',   '本体-动作类型，对应业务操作，如查询、提交、审批',             3, TRUE),
    ('ONTOLOGY_FUNC',   '函数',   '本体-函数类型，对应可调用的原子函数，如聚合、查询函数',       3, TRUE),
    ('ONTOLOGY_PARAM',  '参数',   '本体-参数类型，对应动作或函数的输入/输出参数',               3, TRUE),
    ('ONTOLOGY_PROP',   '属性',   '本体-属性类型，对应对象的字段/属性描述',                     3, TRUE)

ON CONFLICT (type_code) DO NOTHING;
