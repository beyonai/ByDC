CREATE TABLE IF NOT EXISTS domain (
    domain_id    VARCHAR(64)  NOT NULL PRIMARY KEY,
    domain_name  VARCHAR(255) NOT NULL,
    parent_id    VARCHAR(64),
    domain_desc  TEXT,
    created_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE domain IS '领域表：术语分类目录，支持无限层级';
COMMENT ON COLUMN domain.domain_id   IS '领域ID，主键';
COMMENT ON COLUMN domain.domain_name IS '领域名称';
COMMENT ON COLUMN domain.parent_id   IS '父级领域ID，根节点为 NULL';
COMMENT ON COLUMN domain.domain_desc IS '领域描述';
COMMENT ON COLUMN domain.created_time IS '创建时间';
COMMENT ON COLUMN domain.updated_time IS '更新时间';
