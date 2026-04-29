-- =====================================================
-- term_name 搜索能力增强：BM25 + 向量检索
-- 兼容 GaussDB/OpenGauss（内置 vector 类型，无需 pgvector 扩展）
-- =====================================================

-- GaussDB/OpenGauss 内置 vector 类型，无需安装 pgvector 扩展
-- 若为标准 PostgreSQL，需先执行: CREATE EXTENSION vector;

-- 步骤 1: 添加 tsvector 列（BM25 全文搜索）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'term_name' AND column_name = 'name_keywords'
    ) THEN
        ALTER TABLE term_name ADD COLUMN name_keywords tsvector;
        COMMENT ON COLUMN term_name.name_keywords IS 'BM25 全文搜索向量，基于 name_text 单字分词';
    END IF;
END $$;

-- 步骤 2: 添加 vector 列（语义向量检索）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'term_name' AND column_name = 'name_embedding'
    ) THEN
        ALTER TABLE term_name ADD COLUMN name_embedding vector(1024);
        COMMENT ON COLUMN term_name.name_embedding IS '向量语义召回，1024 维 embedding';
    END IF;
END $$;

-- 步骤 3: 创建 tsvector 自动更新触发器函数（单字分词）
-- 使用 array_to_string + string_to_array 实现单字分词，兼容 GaussDB
CREATE OR REPLACE FUNCTION term_name_tsv_trigger() RETURNS trigger AS $$
BEGIN
    -- 单字分词：将 "企业分析" 转换为 "企 业 分 析"，使用 simple 配置索引
    NEW.name_keywords := to_tsvector('simple', array_to_string(string_to_array(COALESCE(NEW.name_text, ''), NULL), ' '));
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

-- 步骤 4: 创建触发器
DO $$
BEGIN
    DROP TRIGGER IF EXISTS tsvector_update_term_name ON term_name;
    CREATE TRIGGER tsvector_update_term_name
        BEFORE INSERT OR UPDATE ON term_name
        FOR EACH ROW
        EXECUTE FUNCTION term_name_tsv_trigger();
END $$;

-- 步骤 5: 为存量数据填充 tsvector（仅执行一次，可手动运行）
-- UPDATE term_name
-- SET name_keywords = to_tsvector('simple', array_to_string(string_to_array(COALESCE(name_text, ''), NULL), ' '));


-- =====================================================
-- 步骤 6: 添加 jieba 分词 tsvector 列（词级全文搜索）
-- 由应用层 Python jieba 分词后写入，不使用 DB trigger。
-- =====================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'term_name' AND column_name = 'name_keywords_jieba'
    ) THEN
        ALTER TABLE term_name ADD COLUMN name_keywords_jieba tsvector;
        COMMENT ON COLUMN term_name.name_keywords_jieba IS 'BM25 全文搜索向量，基于 jieba 中文分词（词级粒度，由应用层填充）';
    END IF;
END $$;