CREATE TABLE IF NOT EXISTS whale_datacloud.term_library (
    library_id   VARCHAR(64)  NOT NULL PRIMARY KEY,
    library_name VARCHAR(255) NOT NULL,
    created_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE whale_datacloud.term_library IS '术语库表：管理术语来源，区分不同渠道的术语集合';
COMMENT ON COLUMN whale_datacloud.term_library.library_id   IS '术语库ID，主键';
COMMENT ON COLUMN whale_datacloud.term_library.library_name IS '术语库名称，如"HR系统术语库"';
COMMENT ON COLUMN whale_datacloud.term_library.created_time IS '创建时间';
COMMENT ON COLUMN whale_datacloud.term_library.updated_time IS '更新时间';
