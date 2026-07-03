CREATE TABLE IF NOT EXISTS domain_library (
    domain_id  VARCHAR(64) NOT NULL,
    library_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (domain_id, library_id)
);

COMMENT ON TABLE domain_library IS '领域-术语库关联表：支持领域与术语库的多对多关系';
COMMENT ON COLUMN domain_library.domain_id  IS '领域ID';
COMMENT ON COLUMN domain_library.library_id IS '术语库ID';
