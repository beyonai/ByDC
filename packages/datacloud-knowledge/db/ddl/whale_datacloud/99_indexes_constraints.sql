-- term_library
CREATE INDEX IF NOT EXISTS idx_lib_name
    ON whale_datacloud.term_library(library_name);

-- domain
CREATE INDEX IF NOT EXISTS idx_domain_parent
    ON whale_datacloud.domain(parent_id);

CREATE INDEX IF NOT EXISTS idx_domain_name
    ON whale_datacloud.domain(domain_name);

-- term_type
CREATE INDEX IF NOT EXISTS idx_type_name
    ON whale_datacloud.term_type(type_name);

CREATE INDEX IF NOT EXISTS idx_type_category
    ON whale_datacloud.term_type(type_category);

-- term
CREATE INDEX IF NOT EXISTS idx_term_tags
    ON whale_datacloud.term USING GIN (term_tags);

CREATE INDEX IF NOT EXISTS idx_term_ext_attrs
    ON whale_datacloud.term USING GIN (ext_attrs);

CREATE INDEX IF NOT EXISTS idx_term_name
    ON whale_datacloud.term(term_name);

CREATE INDEX IF NOT EXISTS idx_term_parent
    ON whale_datacloud.term(parent_term_id);

CREATE INDEX IF NOT EXISTS idx_term_owl
    ON whale_datacloud.term(owl_doc_id)
    WHERE owl_doc_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_term_domain
    ON whale_datacloud.term(domain_id);

CREATE INDEX IF NOT EXISTS idx_term_type
    ON whale_datacloud.term(term_type_code);

CREATE INDEX IF NOT EXISTS idx_term_library
    ON whale_datacloud.term(library_id);

-- term_knowledge
CREATE INDEX IF NOT EXISTS idx_tk_term
    ON whale_datacloud.term_knowledge(term_id);

CREATE INDEX IF NOT EXISTS idx_tk_summary_fts
    ON whale_datacloud.term_knowledge
    USING GIN (to_tsvector('simple', COALESCE(desc_summary, '')));

CREATE INDEX IF NOT EXISTS idx_tk_desc_fts
    ON whale_datacloud.term_knowledge
    USING GIN (to_tsvector('simple', COALESCE("desc", '')));

CREATE INDEX IF NOT EXISTS idx_tk_ext_doc
    ON whale_datacloud.term_knowledge(ext_system, ext_kb_id, ext_doc_id)
    WHERE ext_doc_id IS NOT NULL;

-- term_relation
CREATE UNIQUE INDEX IF NOT EXISTS idx_tr_unique_relation
    ON whale_datacloud.term_relation(source_term_id, target_term_id, relation_name);

CREATE INDEX IF NOT EXISTS idx_tr_source
    ON whale_datacloud.term_relation(source_term_id);

CREATE INDEX IF NOT EXISTS idx_tr_target
    ON whale_datacloud.term_relation(target_term_id);

CREATE INDEX IF NOT EXISTS idx_tr_category
    ON whale_datacloud.term_relation(relation_category);

CREATE INDEX IF NOT EXISTS idx_tr_action
    ON whale_datacloud.term_relation(action_term_id)
    WHERE action_term_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tr_ext_attrs
    ON whale_datacloud.term_relation USING GIN (ext_attrs);

-- term_name
CREATE INDEX IF NOT EXISTS idx_tn_name_text
    ON whale_datacloud.term_name(name_text);

CREATE INDEX IF NOT EXISTS idx_tn_term
    ON whale_datacloud.term_name(term_id);

-- term_vocabulary：唯一索引保障去重查询极速（不依赖实时 DISTINCT）
CREATE UNIQUE INDEX IF NOT EXISTS idx_vocab_word
    ON whale_datacloud.term_vocabulary(word);

-- term_name
CREATE INDEX IF NOT EXISTS idx_tn_search_scope
    ON whale_datacloud.term_name USING GIN (search_scope);

-- term_name BM25 GIN 索引
CREATE INDEX IF NOT EXISTS idx_tn_name_keywords
    ON whale_datacloud.term_name USING GIN (name_keywords);

-- term_name 向量 HNSW 索引（余弦距离）
CREATE INDEX IF NOT EXISTS idx_tn_name_embedding_hnsw
    ON whale_datacloud.term_name
    USING hnsw (name_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- term_name jieba 分词 BM25 GIN 索引
CREATE INDEX IF NOT EXISTS idx_tn_name_keywords_jieba
    ON whale_datacloud.term_name USING GIN (name_keywords_jieba);
