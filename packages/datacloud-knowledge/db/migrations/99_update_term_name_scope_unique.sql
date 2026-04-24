-- 存量库迁移：按 search_scope 区分 term_name 唯一性，并清理历史全局属性名。
-- 背景：字段别名现在通过 HAS_FIELD relation 写入 view/object 作用域，不能再被
-- (term_id, name_text) 唯一索引阻止，也不能保留历史 {"scope":"global"} prop 名称。

DELETE FROM term_name tn
USING term t
WHERE tn.term_id = t.term_id
  AND t.term_type_code = 'prop'
  AND (
      tn.search_scope @> '{"scope":"global"}'::jsonb
      OR tn.search_scope = '{}'::jsonb
  );

DROP INDEX IF EXISTS uq_term_name_text;

CREATE UNIQUE INDEX IF NOT EXISTS uq_term_name_scope
ON term_name(term_id, name_text, search_scope);

COMMENT ON COLUMN term_name.search_scope IS '名称作用域与标签属性，JSONB 格式；字段别名使用 {"scope":"view|object|global","code":"..."} 限定召回范围，也可存储 scope_user_id/score/use_count/confirmed_count/last_used_at 等用户标签';
