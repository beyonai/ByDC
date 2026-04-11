-- 系统内置术语类型预置数据
-- 使用 INSERT ... SELECT WHERE NOT EXISTS 保证幂等，可重复执行，兼容 OpenGauss

-- ── 列表术语（type_category = 1）────────────────────────────────────────────────────────────────────────
INSERT INTO whale_datacloud.term_type (type_code, type_name, type_desc, type_category, is_builtin)
SELECT 'employee', '员工', '员工/人员列表术语，用于关联人员维度', 1, TRUE
WHERE NOT EXISTS (SELECT 1 FROM whale_datacloud.term_type WHERE type_code = 'employee');

-- ── 字典术语（type_category = 2）────────────────────────────────────────────────────────────────────────
INSERT INTO whale_datacloud.term_type (type_code, type_name, type_desc, type_category, is_builtin)
SELECT 'general', '通用', '通用字典/枚举类术语，如状态、类别等', 2, TRUE
WHERE NOT EXISTS (SELECT 1 FROM whale_datacloud.term_type WHERE type_code = 'general');

-- ── 本体术语（type_category = 3）────────────────────────────────────────────────────────────────────────
INSERT INTO whale_datacloud.term_type (type_code, type_name, type_desc, type_category, is_builtin)
SELECT 'view', '视图', '本体-视图类型，对应数据分析场景，包含多个对象及其关联关系', 3, TRUE
WHERE NOT EXISTS (SELECT 1 FROM whale_datacloud.term_type WHERE type_code = 'view');

INSERT INTO whale_datacloud.term_type (type_code, type_name, type_desc, type_category, is_builtin)
SELECT 'object', '对象', '本体-对象类型，对应业务实体，如客户、合同、组织', 3, TRUE
WHERE NOT EXISTS (SELECT 1 FROM whale_datacloud.term_type WHERE type_code = 'object');

INSERT INTO whale_datacloud.term_type (type_code, type_name, type_desc, type_category, is_builtin)
SELECT 'action', '动作', '本体-动作类型，对应业务操作，如查询、提交、审批', 3, TRUE
WHERE NOT EXISTS (SELECT 1 FROM whale_datacloud.term_type WHERE type_code = 'action');

INSERT INTO whale_datacloud.term_type (type_code, type_name, type_desc, type_category, is_builtin)
SELECT 'func', '函数', '本体-函数类型，对应可调用的原子函数，如聚合、查询函数', 3, TRUE
WHERE NOT EXISTS (SELECT 1 FROM whale_datacloud.term_type WHERE type_code = 'func');

INSERT INTO whale_datacloud.term_type (type_code, type_name, type_desc, type_category, is_builtin)
SELECT 'param', '参数', '本体-参数类型，对应动作或函数的输入/输出参数', 3, TRUE
WHERE NOT EXISTS (SELECT 1 FROM whale_datacloud.term_type WHERE type_code = 'param');

INSERT INTO whale_datacloud.term_type (type_code, type_name, type_desc, type_category, is_builtin)
SELECT 'prop', '属性', '本体-属性类型，对应对象的字段/属性描述', 3, TRUE
WHERE NOT EXISTS (SELECT 1 FROM whale_datacloud.term_type WHERE type_code = 'prop');
