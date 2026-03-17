CREATE TABLE IF NOT EXISTS whale_datacloud.term_name (
    name_id      VARCHAR(64)  NOT NULL PRIMARY KEY,
    term_id      VARCHAR(64)  NOT NULL,
    name_text    VARCHAR(255) NOT NULL,
    created_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_term_name_term
        FOREIGN KEY (term_id) REFERENCES whale_datacloud.term(term_id)
);
