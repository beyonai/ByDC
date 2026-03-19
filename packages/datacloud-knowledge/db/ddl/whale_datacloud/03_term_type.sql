CREATE TABLE IF NOT EXISTS whale_datacloud.term_type (
    type_id       BIGSERIAL    NOT NULL PRIMARY KEY,
    type_code     VARCHAR(32)  NOT NULL,
    type_name     VARCHAR(255) NOT NULL,
    type_desc     TEXT,
    type_category INTEGER      NOT NULL,
    is_builtin    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_time  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_term_type_type_code UNIQUE (type_code),
    CONSTRAINT chk_term_type_type_code CHECK (type_code ~ '^[A-Za-z][A-Za-z0-9_]{1,31}$')
);

COMMENT ON TABLE whale_datacloud.term_type IS '术语类型表：定义术语的分类编码体系，扁平化设计';
COMMENT ON COLUMN whale_datacloud.term_type.type_id       IS '自增主键';
COMMENT ON COLUMN whale_datacloud.term_type.type_code     IS '术语类型编码，唯一，如 OBJ/VIEW/ACTION/FUNC/PARAM/PROP/EMPLOYEE';
COMMENT ON COLUMN whale_datacloud.term_type.type_name     IS '术语类型名称';
COMMENT ON COLUMN whale_datacloud.term_type.type_desc     IS '术语类型描述';
COMMENT ON COLUMN whale_datacloud.term_type.type_category IS '大分类：1=列表术语, 2=字典术语, 3=本体术语, 4=文档名称术语';
COMMENT ON COLUMN whale_datacloud.term_type.is_builtin    IS '是否内置：true=系统预置不可删除，false=用户自定义';
COMMENT ON COLUMN whale_datacloud.term_type.created_time  IS '创建时间';
COMMENT ON COLUMN whale_datacloud.term_type.updated_time  IS '更新时间';
