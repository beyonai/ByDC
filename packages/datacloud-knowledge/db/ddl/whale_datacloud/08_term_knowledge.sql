CREATE TABLE IF NOT EXISTS whale_datacloud.term_knowledge (
    knowledge_id VARCHAR(64)  NOT NULL PRIMARY KEY,
    term_id      VARCHAR(64)  NOT NULL,
    desc_summary TEXT,
    "desc"       TEXT,
    ext_system   VARCHAR(32),
    ext_kb_id    VARCHAR(128),
    ext_doc_id   VARCHAR(128),
    sort_order   INTEGER      NOT NULL DEFAULT 0,
    created_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_tk_not_empty CHECK (
        desc_summary IS NOT NULL OR "desc" IS NOT NULL OR ext_doc_id IS NOT NULL
    ),
    CONSTRAINT chk_tk_ext_complete CHECK (
        ext_doc_id IS NULL OR (ext_system IS NOT NULL AND ext_kb_id IS NOT NULL)
    )
);

COMMENT ON TABLE whale_datacloud.term_knowledge IS '术语关联知识表：挂载术语的业务知识，支持内部落地和外挂知识库两种模式';
COMMENT ON COLUMN whale_datacloud.term_knowledge.knowledge_id IS '知识ID，主键';
COMMENT ON COLUMN whale_datacloud.term_knowledge.term_id      IS '归属术语ID，外键关联 term 表';
COMMENT ON COLUMN whale_datacloud.term_knowledge.desc_summary IS '知识摘要，约200字；内部落地时填写，用于快速展示与关键字检索';
COMMENT ON COLUMN whale_datacloud.term_knowledge."desc"       IS '知识原文，完整内容；内部落地时填写，支持本地全文检索';
COMMENT ON COLUMN whale_datacloud.term_knowledge.ext_system   IS '外部系统编码，如 RAGFLOW/DIFY/CONFLUENCE；外挂模式时必填';
COMMENT ON COLUMN whale_datacloud.term_knowledge.ext_kb_id    IS '外部知识库ID，在对应系统内唯一标识知识库；外挂模式时必填';
COMMENT ON COLUMN whale_datacloud.term_knowledge.ext_doc_id   IS '外部文档ID，在对应知识库内唯一标识文档；由外部 KB 负责 chunk embedding 与向量检索';
COMMENT ON COLUMN whale_datacloud.term_knowledge.sort_order   IS '同一术语下多条知识的展示排序，默认 0';
COMMENT ON COLUMN whale_datacloud.term_knowledge.created_time IS '创建时间';
COMMENT ON COLUMN whale_datacloud.term_knowledge.updated_time IS '更新时间';
