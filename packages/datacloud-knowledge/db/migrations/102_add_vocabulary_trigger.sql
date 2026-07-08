-- 为 term_vocabulary 添加自动维护触发器
-- term_name INSERT 时自动去重写入 vocabulary，无需应用层手动调用

CREATE OR REPLACE FUNCTION maintain_term_vocabulary() RETURNS trigger AS $$
BEGIN
    INSERT INTO term_vocabulary (word)
    SELECT NEW.name_text
    WHERE NOT EXISTS (
        SELECT 1 FROM term_vocabulary WHERE word = NEW.name_text
    );
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_term_name_vocab ON term_name;
CREATE TRIGGER trg_term_name_vocab
    AFTER INSERT ON term_name
    FOR EACH ROW
    EXECUTE PROCEDURE maintain_term_vocabulary();

-- 回填存量 term_name 中缺失的 vocabulary 数据
INSERT INTO term_vocabulary (word)
SELECT DISTINCT name_text FROM term_name tn
WHERE NOT EXISTS (
    SELECT 1 FROM term_vocabulary tv WHERE tv.word = tn.name_text
);

-- 修复序列（空表时跳过）
SELECT setval(
    'term_vocabulary_vocab_id_seq',
    (SELECT COALESCE(MAX(vocab_id), 0) + 1 FROM term_vocabulary),
    false
);
