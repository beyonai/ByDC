CREATE TABLE IF NOT EXISTS whale_datacloud.term (
    term_id        VARCHAR(64)  NOT NULL PRIMARY KEY,
    term_name      VARCHAR(255) NOT NULL,
    desc_summary   TEXT,
    parent_term_id VARCHAR(64),
    owl_doc_id     VARCHAR(128),
    domain_id      VARCHAR(64)  NOT NULL,
    term_type_code VARCHAR(32)  NOT NULL,
    library_id     VARCHAR(64),
    term_tags      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_time   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_term_parent
        FOREIGN KEY (parent_term_id) REFERENCES whale_datacloud.term(term_id),
    CONSTRAINT fk_term_domain
        FOREIGN KEY (domain_id) REFERENCES whale_datacloud.domain(domain_id),
    CONSTRAINT fk_term_term_type
        FOREIGN KEY (term_type_code) REFERENCES whale_datacloud.term_type(type_code),
    CONSTRAINT fk_term_library
        FOREIGN KEY (library_id) REFERENCES whale_datacloud.term_library(library_id)
);
