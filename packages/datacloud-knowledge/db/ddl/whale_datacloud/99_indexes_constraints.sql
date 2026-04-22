-- term_library
CREATE INDEX IF NOT EXISTS idx_lib_name
    ON term_library(library_name);

-- domain
CREATE INDEX IF NOT EXISTS idx_domain_parent
    ON domain(parent_id);

CREATE INDEX IF NOT EXISTS idx_domain_name
    ON domain(domain_name);

-- term_type
CREATE INDEX IF NOT EXISTS idx_type_name
    ON term_type(type_name);

CREATE INDEX IF NOT EXISTS idx_type_category
    ON term_type(type_category);

-- term
CREATE INDEX IF NOT EXISTS idx_term_tags
    ON term USING GIN (term_tags);

CREATE INDEX IF NOT EXISTS idx_term_ext_attrs
    ON term USING GIN (ext_attrs);

CREATE INDEX IF NOT EXISTS idx_term_name
    ON term(term_name);

CREATE INDEX IF NOT EXISTS idx_term_parent
    ON term(parent_term_id);

CREATE INDEX IF NOT EXISTS idx_term_owl
    ON term(owl_doc_id)
    WHERE owl_doc_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_term_domain
    ON term(domain_id);

CREATE INDEX IF NOT EXISTS idx_term_type
    ON term(term_type_code);

CREATE INDEX IF NOT EXISTS idx_term_library
    ON term(library_id);

-- term_knowledge
CREATE INDEX IF NOT EXISTS idx_tk_term
    ON term_knowledge(term_id);

CREATE INDEX IF NOT EXISTS idx_tk_summary_fts
    ON term_knowledge
    USING GIN (to_tsvector('simple', COALESCE(desc_summary, '')));

CREATE INDEX IF NOT EXISTS idx_tk_desc_fts
    ON term_knowledge
    USING GIN (to_tsvector('simple', COALESCE("desc", '')));

CREATE INDEX IF NOT EXISTS idx_tk_ext_doc
    ON term_knowledge(ext_system, ext_kb_id, ext_doc_id)
    WHERE ext_doc_id IS NOT NULL;

-- term_relation
CREATE UNIQUE INDEX IF NOT EXISTS idx_tr_unique_relation
    ON term_relation(source_term_id, target_term_id, relation_name);

CREATE INDEX IF NOT EXISTS idx_tr_source
    ON term_relation(source_term_id);

CREATE INDEX IF NOT EXISTS idx_tr_target
    ON term_relation(target_term_id);

CREATE INDEX IF NOT EXISTS idx_tr_category
    ON term_relation(relation_category);

CREATE INDEX IF NOT EXISTS idx_tr_action
    ON term_relation(action_term_id)
    WHERE action_term_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tr_ext_attrs
    ON term_relation USING GIN (ext_attrs);

-- term_name
CREATE INDEX IF NOT EXISTS idx_tn_name_text
    ON term_name(name_text);

CREATE INDEX IF NOT EXISTS idx_tn_term
    ON term_name(term_id);

-- 根术语：库内唯一（library_id + term_type_code + term_code）
CREATE UNIQUE INDEX IF NOT EXISTS uq_term_root
    ON term(library_id, term_type_code, term_code)
    WHERE parent_term_id IS NULL AND library_id IS NOT NULL;

-- 子术语：父节点内唯一（parent_term_id + term_code）
CREATE UNIQUE INDEX IF NOT EXISTS uq_term_child
    ON term(parent_term_id, term_code)
    WHERE parent_term_id IS NOT NULL;

-- 术语名称：同一术语下名称不重复
CREATE UNIQUE INDEX IF NOT EXISTS uq_term_name_text
    ON term_name(term_id, name_text);

-- term_vocabulary：唯一索引保障去重查询极速（不依赖实时 DISTINCT）
CREATE UNIQUE INDEX IF NOT EXISTS idx_vocab_word
    ON term_vocabulary(word);

-- term_name
CREATE INDEX IF NOT EXISTS idx_tn_search_scope
    ON term_name USING GIN (search_scope);

-- term_name BM25 GIN 索引
CREATE INDEX IF NOT EXISTS idx_tn_name_keywords
    ON term_name USING GIN (name_keywords);

-- term_name 向量 HNSW 索引（余弦距离）
CREATE INDEX IF NOT EXISTS idx_tn_name_embedding_hnsw
    ON term_name
    USING hnsw (name_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- term_name jieba 分词 BM25 GIN 索引
CREATE INDEX IF NOT EXISTS idx_tn_name_keywords_jieba
    ON term_name USING GIN (name_keywords_jieba);
