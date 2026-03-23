CREATE TABLE IF NOT EXISTS whale_datacloud.term (
    term_id        VARCHAR(64)  NOT NULL PRIMARY KEY,
    term_code      VARCHAR(64)  NOT NULL,
    term_name      VARCHAR(255) NOT NULL,
    desc_summary   TEXT,
    parent_term_id VARCHAR(64),
    owl_doc_id     VARCHAR(128),
    domain_id      VARCHAR(64)  NOT NULL,
    term_type_code VARCHAR(32)  NOT NULL,
    library_id     VARCHAR(64),
    term_tags      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    ext_attrs      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_time   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE whale_datacloud.term IS '术语主表：存储所有术语及其核心属性';
COMMENT ON COLUMN whale_datacloud.term.term_id        IS '术语ID，主键';
COMMENT ON COLUMN whale_datacloud.term.term_code      IS '术语编码';
COMMENT ON COLUMN whale_datacloud.term.term_name      IS '术语标准名称，全局唯一规范名';
COMMENT ON COLUMN whale_datacloud.term.desc_summary   IS '术语描述摘要，约100字，用于快速展示；完整知识在 term_knowledge 表';
COMMENT ON COLUMN whale_datacloud.term.parent_term_id IS '父术语ID：NULL=概念术语，有值=实例术语（指向所属概念的 term_id）';
COMMENT ON COLUMN whale_datacloud.term.owl_doc_id     IS 'OWL本体定义文件ID，仅本体术语（type_category=3）填写，其余为 NULL';
COMMENT ON COLUMN whale_datacloud.term.domain_id      IS '所属领域ID，外键关联 domain 表';
COMMENT ON COLUMN whale_datacloud.term.term_type_code IS '术语类型编码，外键关联 term_type(type_code)';
COMMENT ON COLUMN whale_datacloud.term.library_id     IS '所属术语库ID，外键关联 term_library 表，允许为空';
COMMENT ON COLUMN whale_datacloud.term.term_tags      IS '术语标签属性，JSONB 格式；key=标签维度术语ID，value={type, value}';
COMMENT ON COLUMN whale_datacloud.term.ext_attrs      IS '自定义扩展属性，JSON 键值对，供业务/产品扩展；与 term_tags（标签、别名）分离';
COMMENT ON COLUMN whale_datacloud.term.created_time   IS '创建时间';
COMMENT ON COLUMN whale_datacloud.term.updated_time   IS '更新时间';
