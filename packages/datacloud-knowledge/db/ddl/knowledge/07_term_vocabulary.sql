-- term_vocabulary：去重词汇表，作为 jieba 自定义词典数据来源。
-- 由 trigger trg_term_name_vocab 在 term_name INSERT 时自动去重写入，
-- 保证查询时直接走唯一索引，无需实时 DISTINCT 计算。
CREATE TABLE IF NOT EXISTS term_vocabulary (
    vocab_id BIGSERIAL    NOT NULL PRIMARY KEY,
    word     VARCHAR(255) NOT NULL
);

COMMENT ON TABLE  term_vocabulary IS '术语词汇表：term_name.name_text 去重后的词汇集合，作为 jieba 自定义词典数据来源；由触发器 trg_term_name_vocab 自动维护';
COMMENT ON COLUMN term_vocabulary.vocab_id IS '词汇ID，自增主键';
COMMENT ON COLUMN term_vocabulary.word     IS '词汇文本，UNIQUE 约束确保全局去重';
