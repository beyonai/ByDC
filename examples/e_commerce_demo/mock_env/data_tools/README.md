# data_tools

离线资源构建脚本，用于 `mock_env` 知识库导入包。

## 工具

### convert_yizhuang_terms.py

将 `docs/亦庄术语库导入文件/` 下的 Excel 术语文件转换为 import_package 格式：

- **字典术语**：`字典术语-*.xlsx` → `resource/knowledge/import_package/terms/dict_terms.jsonl`
- **列表术语**：`列表术语-*.xlsx` → `resource/knowledge/import_package/terms/list_terms.jsonl`
- **术语类型**：自动提取并追加到 `term_types/custom.jsonl`

输出术语统一挂载到 `DOMAIN_002`、`LIB_002`。

**运行**：

```bash
python convert_yizhuang_terms.py
```

**依赖**：`pandas`、`openpyxl`
