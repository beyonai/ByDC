CREATE TABLE IF NOT EXISTS term_type (
    type_id       BIGSERIAL    NOT NULL PRIMARY KEY,
    type_code     VARCHAR(32)  NOT NULL,
    type_name     VARCHAR(255) NOT NULL,
    type_desc     TEXT,
    type_category INTEGER      NOT NULL,
    is_builtin    BOOLEAN      NOT NULL DEFAULT FALSE,
    library_id    VARCHAR(64)  NOT NULL,
    domain_ids    VARCHAR(64)[] NOT NULL DEFAULT '{}',
    created_time  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_term_type_library_type UNIQUE (library_id, type_code)
);

COMMENT ON TABLE term_type IS '术语类型表：定义术语的分类编码体系，按术语库隔离';
COMMENT ON COLUMN term_type.type_id       IS '自增主键';
COMMENT ON COLUMN term_type.type_code     IS '术语类型编码（同库内唯一）';
COMMENT ON COLUMN term_type.type_name     IS '术语类型名称';
COMMENT ON COLUMN term_type.type_desc     IS '术语类型描述';
COMMENT ON COLUMN term_type.type_category IS '大分类';
COMMENT ON COLUMN term_type.is_builtin    IS '是否内置：true=系统预置不可删除，false=用户自定义';
COMMENT ON COLUMN term_type.library_id    IS '所属术语库ID';
COMMENT ON COLUMN term_type.domain_ids    IS '所属领域ID数组，支持类型多领域归属';
COMMENT ON COLUMN term_type.created_time  IS '创建时间';
COMMENT ON COLUMN term_type.updated_time  IS '更新时间';
