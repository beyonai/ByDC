CREATE TABLE IF NOT EXISTS whale_datacloud.term_vocabulary (
    vocab_id BIGSERIAL    NOT NULL PRIMARY KEY,
    word     VARCHAR(255) NOT NULL
);

COMMENT ON TABLE whale_datacloud.term_vocabulary IS '术语词汇表：TermName.name_text 去重后的词汇集合，作为 jieba 自定义词典数据来源；frequency 和 pos 在导出时实时计算，不在本表存储';
COMMENT ON COLUMN whale_datacloud.term_vocabulary.vocab_id IS '词汇ID，自增主键';
COMMENT ON COLUMN whale_datacloud.term_vocabulary.word     IS '词汇文本，UNIQUE 约束确保去重';
