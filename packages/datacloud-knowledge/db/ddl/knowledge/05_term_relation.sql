CREATE TABLE IF NOT EXISTS term_relation (

    relation_id              VARCHAR(1000) NOT NULL PRIMARY KEY,
    source_term_id           VARCHAR(1000),
    source_term_type_code    VARCHAR(32),
    target_term_id           VARCHAR(1000),
    target_term_type_code    VARCHAR(32),
    relation_name            VARCHAR(255) NOT NULL,
    relation_category        VARCHAR(16)  NOT NULL DEFAULT 'BUSINESS',
    cardinality              VARCHAR(8),
    ext_attrs                JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_time             TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time             TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_relation_has_source CHECK (
        source_term_id IS NOT NULL OR source_term_type_code IS NOT NULL
    ),
    CONSTRAINT chk_relation_has_target CHECK (
        target_term_id IS NOT NULL OR target_term_type_code IS NOT NULL
    )
);

COMMENT ON TABLE term_relation IS '术语关系表：存储术语间及术语类型间关系';
COMMENT ON COLUMN term_relation.relation_id            IS '关系ID，主键';
COMMENT ON COLUMN term_relation.source_term_id         IS '源术语ID';
COMMENT ON COLUMN term_relation.source_term_type_code  IS '源术语类型编码（用于类型级关系）';
COMMENT ON COLUMN term_relation.target_term_id         IS '目标术语ID';
COMMENT ON COLUMN term_relation.target_term_type_code  IS '目标术语类型编码（用于类型级关系）';
COMMENT ON COLUMN term_relation.relation_name          IS '关系名称';
COMMENT ON COLUMN term_relation.relation_category      IS '关系类别';
COMMENT ON COLUMN term_relation.cardinality            IS '数量约束：1:1 | 1:N | N:1 | N:N';
COMMENT ON COLUMN term_relation.ext_attrs              IS '自定义扩展属性';
COMMENT ON COLUMN term_relation.created_time           IS '创建时间';
COMMENT ON COLUMN term_relation.updated_time           IS '更新时间';
