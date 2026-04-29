CREATE TABLE IF NOT EXISTS term_library (
    library_id   VARCHAR(64)  NOT NULL PRIMARY KEY,
    library_code VARCHAR(32)  NOT NULL,
    library_name VARCHAR(255) NOT NULL,
    created_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_term_library_library_code UNIQUE (library_code)
);

COMMENT ON TABLE term_library IS '术语库表：管理术语来源，区分不同渠道的术语集合';
COMMENT ON COLUMN term_library.library_id   IS '术语库ID，主键';
COMMENT ON COLUMN term_library.library_code IS '术语库编码，全局唯一';
COMMENT ON COLUMN term_library.library_name IS '术语库名称，如"HR系统术语库"';
COMMENT ON COLUMN term_library.created_time IS '创建时间';
COMMENT ON COLUMN term_library.updated_time IS '更新时间';
