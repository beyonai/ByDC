-- =====================================================
-- term_name 鎼滅储鑳藉姏澧炲己锛欱M25 + 鍚戦噺妫€绱?
-- 鍏煎 GaussDB/OpenGauss锛堝唴缃?vector 绫诲瀷锛屾棤闇€ pgvector 鎵╁睍锛?
-- =====================================================

-- GaussDB/OpenGauss 鍐呯疆 vector 绫诲瀷锛屾棤闇€瀹夎 pgvector 鎵╁睍
-- 鑻ヤ负鏍囧噯 PostgreSQL锛岄渶鍏堟墽琛? CREATE EXTENSION vector;

-- 姝ラ 1: 娣诲姞 tsvector 鍒楋紙BM25 鍏ㄦ枃鎼滅储锛?
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud' AND table_name = 'term_name' AND column_name = 'name_keywords'
    ) THEN
        ALTER TABLE whale_datacloud.term_name ADD COLUMN name_keywords tsvector;
        COMMENT ON COLUMN whale_datacloud.term_name.name_keywords IS 'BM25 鍏ㄦ枃鎼滅储鍚戦噺锛屽熀浜?name_text 鍗曞瓧鍒嗚瘝';
    END IF;
END $$;

-- 姝ラ 2: 娣诲姞 vector 鍒楋紙璇箟鍚戦噺妫€绱級
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud' AND table_name = 'term_name' AND column_name = 'name_embedding'
    ) THEN
        ALTER TABLE whale_datacloud.term_name ADD COLUMN name_embedding vector(1024);
        COMMENT ON COLUMN whale_datacloud.term_name.name_embedding IS '鍚戦噺璇箟鍙洖锛?024 缁?embedding';
    END IF;
END $$;

-- 姝ラ 3: 鍒涘缓 tsvector 鑷姩鏇存柊瑙﹀彂鍣ㄥ嚱鏁帮紙鍗曞瓧鍒嗚瘝锛?
-- 浣跨敤 array_to_string + string_to_array 瀹炵幇鍗曞瓧鍒嗚瘝锛屽吋瀹?GaussDB
CREATE OR REPLACE FUNCTION whale_datacloud.term_name_tsv_trigger() RETURNS trigger AS $$
BEGIN
    -- 鍗曞瓧鍒嗚瘝锛氬皢 "浼佷笟鍒嗘瀽" 杞崲涓?"浼?涓?鍒?鏋?锛屼娇鐢?simple 閰嶇疆绱㈠紩
    NEW.name_keywords := to_tsvector('simple', array_to_string(string_to_array(COALESCE(NEW.name_text, ''), NULL), ' '));
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

-- 姝ラ 4: 鍒涘缓瑙﹀彂鍣?
DO $$
BEGIN
    DROP TRIGGER IF EXISTS tsvector_update_term_name ON whale_datacloud.term_name;
    CREATE TRIGGER tsvector_update_term_name
        BEFORE INSERT OR UPDATE ON whale_datacloud.term_name
        FOR EACH ROW
        EXECUTE FUNCTION whale_datacloud.term_name_tsv_trigger();
END $$;

-- 姝ラ 5: 涓哄瓨閲忔暟鎹～鍏?tsvector锛堜粎鎵ц涓€娆★紝鍙墜鍔ㄨ繍琛岋級
-- UPDATE whale_datacloud.term_name
-- SET name_keywords = to_tsvector('simple', array_to_string(string_to_array(COALESCE(name_text, ''), NULL), ' '));
