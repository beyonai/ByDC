CREATE TABLE IF NOT EXISTS whale_datacloud.domain (
    domain_id    VARCHAR(64)  NOT NULL PRIMARY KEY,
    domain_name  VARCHAR(255) NOT NULL,
    parent_id    VARCHAR(64),
    domain_desc  TEXT,
    created_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_domain_parent
        FOREIGN KEY (parent_id) REFERENCES whale_datacloud.domain(domain_id)
);

COMMENT ON TABLE whale_datacloud.domain IS '领域表：术语分类目录，支持无限层级';
COMMENT ON COLUMN whale_datacloud.domain.domain_id   IS '领域ID，主键';
COMMENT ON COLUMN whale_datacloud.domain.domain_name IS '领域名称';
COMMENT ON COLUMN whale_datacloud.domain.parent_id   IS '父级领域ID，根节点为 NULL';
COMMENT ON COLUMN whale_datacloud.domain.domain_desc IS '领域描述';
COMMENT ON COLUMN whale_datacloud.domain.created_time IS '创建时间';
COMMENT ON COLUMN whale_datacloud.domain.updated_time IS '更新时间';
