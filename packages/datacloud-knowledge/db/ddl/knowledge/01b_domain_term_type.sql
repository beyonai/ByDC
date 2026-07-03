CREATE TABLE IF NOT EXISTS domain_term_type (
    domain_id VARCHAR(64) NOT NULL,
    type_code VARCHAR(32) NOT NULL,
    PRIMARY KEY (domain_id, type_code)
);

COMMENT ON TABLE domain_term_type IS '领域-术语类型关联表：支持领域与术语类型的多对多关系';
COMMENT ON COLUMN domain_term_type.domain_id  IS '领域ID';
COMMENT ON COLUMN domain_term_type.type_code  IS '术语类型编码';
