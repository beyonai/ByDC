-- 00_create_schema.sql
-- 破坏性重建：DROP 所有表后重建 schema。
-- 注意：此文件由执行端在运行时注入 schema 名（SET search_path）。
-- 表名使用裸名，依赖 search_path 解析。

DROP TABLE IF EXISTS term_relation CASCADE;
DROP TABLE IF EXISTS term_knowledge CASCADE;
DROP TABLE IF EXISTS term_name CASCADE;
DROP TABLE IF EXISTS term_vocabulary CASCADE;
DROP TABLE IF EXISTS term CASCADE;
DROP TABLE IF EXISTS term_type CASCADE;
DROP TABLE IF EXISTS term_library CASCADE;
DROP TABLE IF EXISTS domain CASCADE;
