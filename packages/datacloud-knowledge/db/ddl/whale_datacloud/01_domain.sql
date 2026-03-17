CREATE TABLE IF NOT EXISTS whale_datacloud.domain (
    domain_id VARCHAR(64) NOT NULL PRIMARY KEY,
    domain_name VARCHAR(255) NOT NULL,
    parent_id VARCHAR(64),
    domain_desc TEXT,
    created_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_domain_parent
        FOREIGN KEY (parent_id) REFERENCES whale_datacloud.domain(domain_id)
);
