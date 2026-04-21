CREATE TABLE IF NOT EXISTS whale_datacloud.term_name (
    name_id            VARCHAR(1000) NOT NULL PRIMARY KEY,
    term_id            VARCHAR(1000) NOT NULL,
    name_text          VARCHAR(255) NOT NULL,
    search_scope       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    name_keywords      tsvector,
    name_embedding     vector(1024),
    name_keywords_jieba tsvector,
    created_time       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE whale_datacloud.term_name IS '术语名称表：存储术语的所有名称（标准名称、别名、缩写等）；name_text=term.term_name 为标准名称，其余为别名';
COMMENT ON COLUMN whale_datacloud.term_name.name_id              IS '名称ID，主键';
COMMENT ON COLUMN whale_datacloud.term_name.term_id              IS '术语ID，外键关联 term 表';
COMMENT ON COLUMN whale_datacloud.term_name.name_text            IS '名称文本；与 term.term_name 相同则为标准名称，不同则为别名';
COMMENT ON COLUMN whale_datacloud.term_name.search_scope         IS '名称标签属性，JSONB 格式；存储 scope_user_id/score/use_count/confirmed_count/last_used_at 等';
COMMENT ON COLUMN whale_datacloud.term_name.name_keywords        IS 'BM25 全文搜索向量，基于 name_text 单字分词';
COMMENT ON COLUMN whale_datacloud.term_name.name_embedding       IS '向量语义召回，1024 维 embedding';
COMMENT ON COLUMN whale_datacloud.term_name.name_keywords_jieba  IS 'BM25 全文搜索向量，基于 jieba 中文分词（词级粒度，由应用层填充）';
COMMENT ON COLUMN whale_datacloud.term_name.created_time         IS '创建时间';
COMMENT ON COLUMN whale_datacloud.term_name.updated_time         IS '更新时间';
