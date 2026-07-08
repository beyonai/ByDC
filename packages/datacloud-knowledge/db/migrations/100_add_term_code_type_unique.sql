-- Add unique constraint for term_code + term_type_code when both parent_term_id and library_id are NULL
-- Required for bulk INSERT ON CONFLICT in _batch_sync_entity_terms
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_term_code_type_null_lib'
    ) THEN
        CREATE UNIQUE INDEX uq_term_code_type_null_lib
            ON term (term_type_code, term_code)
            WHERE parent_term_id IS NULL AND library_id IS NULL;
    END IF;
END $$;
