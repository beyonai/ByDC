CREATE TABLE IF NOT EXISTS whale_datacloud.term_type (
    type_code    VARCHAR(32)  NOT NULL PRIMARY KEY,
    type_name    VARCHAR(255) NOT NULL,
    type_desc    TEXT,
    type         INTEGER      NOT NULL,
    created_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
