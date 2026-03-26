CREATE TABLE IF NOT EXISTS whale_datacloud.term_name (
    name_id      VARCHAR(255) NOT NULL PRIMARY KEY,
    term_id      VARCHAR(255) NOT NULL,
    name_text    VARCHAR(255) NOT NULL,
    created_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE whale_datacloud.term_name IS '术语名称表：存储术语的所有名称（标准名称、别名、缩写等）；name_text=term.term_name 为标准名称，其余为别名';
COMMENT ON COLUMN whale_datacloud.term_name.name_id      IS '名称ID，主键';
COMMENT ON COLUMN whale_datacloud.term_name.term_id      IS '术语ID，外键关联 term 表';
COMMENT ON COLUMN whale_datacloud.term_name.name_text    IS '名称文本；与 term.term_name 相同则为标准名称，不同则为别名';
COMMENT ON COLUMN whale_datacloud.term_name.created_time IS '创建时间';
COMMENT ON COLUMN whale_datacloud.term_name.updated_time IS '更新时间';
