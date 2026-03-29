CREATE TABLE IF NOT EXISTS whale_datacloud.term_relation (

    relation_id       VARCHAR(255) NOT NULL PRIMARY KEY,
    source_term_id    VARCHAR(255) NOT NULL,
    target_term_id    VARCHAR(255) NOT NULL,
    relation_name     VARCHAR(255) NOT NULL,
    relation_category VARCHAR(16)  NOT NULL DEFAULT 'BUSINESS',
    cardinality       VARCHAR(8),
    action_term_id    VARCHAR(255),
    ext_attrs         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_time      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE whale_datacloud.term_relation IS '术语关系表：存储术语间的本体论结构关系（ONTOLOGY）和业务自定义关系（BUSINESS）';
COMMENT ON COLUMN whale_datacloud.term_relation.relation_id       IS '关系ID，主键';
COMMENT ON COLUMN whale_datacloud.term_relation.source_term_id    IS '源术语ID，外键关联 term 表';
COMMENT ON COLUMN whale_datacloud.term_relation.target_term_id    IS '目标术语ID，外键关联 term 表';
COMMENT ON COLUMN whale_datacloud.term_relation.relation_name     IS '关系名称，格式"源术语_动词_目标术语"；ONTOLOGY 类使用标准枚举，BUSINESS 类自由定义';
COMMENT ON COLUMN whale_datacloud.term_relation.relation_category IS '关系类别：ONTOLOGY=本体论结构关系，BUSINESS=业务自定义关系，默认 BUSINESS';
COMMENT ON COLUMN whale_datacloud.term_relation.cardinality       IS '数量约束：1:1 | 1:N | N:1 | N:N';
COMMENT ON COLUMN whale_datacloud.term_relation.action_term_id    IS '绑定的动作术语ID（term_type_code=ACTION），BUSINESS 关系推荐填写，ONTOLOGY 通常为 NULL';
COMMENT ON COLUMN whale_datacloud.term_relation.ext_attrs         IS '自定义扩展属性，JSON 键值对，供业务/产品扩展';
COMMENT ON COLUMN whale_datacloud.term_relation.created_time      IS '创建时间';
COMMENT ON COLUMN whale_datacloud.term_relation.updated_time      IS '更新时间';
