CREATE TABLE IF NOT EXISTS whale_datacloud.term_knowledge (
    knowledge_id VARCHAR(64)  NOT NULL PRIMARY KEY,
    term_id      VARCHAR(64)  NOT NULL,
    desc_summary TEXT,
    "desc"       TEXT,
    ext_system   VARCHAR(32),
    ext_kb_id    VARCHAR(128),
    ext_doc_id   VARCHAR(128),
    sort_order   INTEGER      NOT NULL DEFAULT 0,
    created_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tk_term
        FOREIGN KEY (term_id) REFERENCES whale_datacloud.term(term_id),
    CONSTRAINT chk_tk_not_empty CHECK (
        desc_summary IS NOT NULL OR "desc" IS NOT NULL OR ext_doc_id IS NOT NULL
    ),
    CONSTRAINT chk_tk_ext_complete CHECK (
        ext_doc_id IS NULL OR (ext_system IS NOT NULL AND ext_kb_id IS NOT NULL)
    )
);
