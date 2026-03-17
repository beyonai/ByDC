CREATE TABLE IF NOT EXISTS whale_datacloud.term_vocabulary (
    vocab_id BIGSERIAL    NOT NULL PRIMARY KEY,
    word     VARCHAR(255) NOT NULL
);
