-- 瀛橀噺搴撹縼绉伙細涓?term_name 澧炲姞 search_scope 鍒椼€?
-- 鏂扮幆澧冪敱 06_term_name.sql 寤鸿〃鏃跺凡鍖呭惈璇ュ垪锛涘吋瀹?OpenGauss锛屼笉浣跨敤 ADD COLUMN IF NOT EXISTS銆?

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'whale_datacloud' AND table_name = 'term_name' AND column_name = 'search_scope'
    ) THEN
        ALTER TABLE whale_datacloud.term_name ADD COLUMN search_scope JSONB NOT NULL DEFAULT '{}'::jsonb;
    END IF;
END $$;
COMMENT ON COLUMN whale_datacloud.term_name.search_scope IS '鍚嶇О鏍囩灞炴€э紝JSONB 鏍煎紡锛涘瓨鍌?scope_user_id/score/use_count/confirmed_count/last_used_at 绛?;

