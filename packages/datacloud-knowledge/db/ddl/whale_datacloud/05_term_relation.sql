CREATE TABLE IF NOT EXISTS whale_datacloud.term_relation (
    relation_id       VARCHAR(64)  NOT NULL PRIMARY KEY,
    source_term_id    VARCHAR(64)  NOT NULL,
    target_term_id    VARCHAR(64)  NOT NULL,
    relation_name     VARCHAR(255) NOT NULL,
    relation_category VARCHAR(16)  NOT NULL DEFAULT 'BUSINESS',
    cardinality       VARCHAR(8),
    action_term_id    VARCHAR(64),
    created_time      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tr_source
        FOREIGN KEY (source_term_id) REFERENCES whale_datacloud.term(term_id),
    CONSTRAINT fk_tr_target
        FOREIGN KEY (target_term_id) REFERENCES whale_datacloud.term(term_id),
    CONSTRAINT fk_tr_action
        FOREIGN KEY (action_term_id) REFERENCES whale_datacloud.term(term_id)
);
