CREATE TABLE IF NOT EXISTS term_domain (
    domain_id    VARCHAR(64)  NOT NULL PRIMARY KEY,
    domain_code  VARCHAR(64)  NOT NULL,
    domain_name  VARCHAR(255) NOT NULL,
    parent_id    VARCHAR(64),
    library_id   VARCHAR(64)  NOT NULL,
    domain_desc  TEXT,
    created_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_term_domain_library_code UNIQUE (library_id, domain_code),
    CONSTRAINT uq_term_domain_library_name_parent UNIQUE (library_id, parent_id, domain_name)
);

COMMENT ON TABLE term_domain IS '术语领域表：术语库内的分类维度，支持无限层级，绑定单一术语库';
COMMENT ON COLUMN term_domain.domain_id   IS '领域ID，主键';
COMMENT ON COLUMN term_domain.domain_code IS '领域编码（同库内唯一），供API层使用code↔id翻译';
COMMENT ON COLUMN term_domain.domain_name IS '领域名称';
COMMENT ON COLUMN term_domain.parent_id   IS '父级领域ID，根节点为NULL';
COMMENT ON COLUMN term_domain.library_id  IS '所属术语库ID';
COMMENT ON COLUMN term_domain.domain_desc IS '领域描述';
COMMENT ON COLUMN term_domain.created_time IS '创建时间';
COMMENT ON COLUMN term_domain.updated_time IS '更新时间';
