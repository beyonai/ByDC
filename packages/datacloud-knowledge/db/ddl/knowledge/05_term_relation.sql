CREATE TABLE IF NOT EXISTS term_relation (

    relation_id       VARCHAR(1000) NOT NULL PRIMARY KEY,
    source_term_id    VARCHAR(1000) NOT NULL,
    target_term_id    VARCHAR(1000) NOT NULL,
    relation_name     VARCHAR(255) NOT NULL,
    relation_category VARCHAR(16)  NOT NULL DEFAULT 'BUSINESS',
    cardinality       VARCHAR(8),
    ext_attrs         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_time      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE term_relation IS '术语关系表：存储术语间关系';
COMMENT ON COLUMN term_relation.relation_id       IS '关系ID，主键';
COMMENT ON COLUMN term_relation.source_term_id    IS '源术语ID，外键关联 term 表';
COMMENT ON COLUMN term_relation.target_term_id    IS '目标术语ID，外键关联 term 表';
COMMENT ON COLUMN term_relation.relation_name     IS '关系名称';
COMMENT ON COLUMN term_relation.relation_category IS '关系类别';
COMMENT ON COLUMN term_relation.cardinality       IS '数量约束：1:1 | 1:N | N:1 | N:N';
COMMENT ON COLUMN term_relation.ext_attrs         IS '自定义扩展属性，JSON 键值对，供业务/产品扩展';
COMMENT ON COLUMN term_relation.created_time      IS '创建时间';
COMMENT ON COLUMN term_relation.updated_time      IS '更新时间';
