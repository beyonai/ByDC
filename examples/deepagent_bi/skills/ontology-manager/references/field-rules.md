# 字段类型规则

## property_role 枚举

- `DIMENSION`：维度属性（用于分组、过滤）
- `MEASURE`：度量属性（用于统计、计算）

## rule_type 枚举及规则

| 属性类型 | 属性子类 | rule_type | 分组规则 | 统计函数 |
|----------|----------|-----------|----------|----------|
| 维度 | ID | `id` | 仅支持按自身分组 | — |
| 维度 | 名称 | `name` | 仅支持按自身分组 | — |
| 维度 | 时间 | `datetime` | 支持 DATE/MONTH/YEAR/QUARTER | — |
| 维度 | 账期 | `period` | 支持 DATE/MONTH/YEAR/QUARTER | — |
| 维度 | 数值 | `numeric` | — | — |
| 维度 | 描述 | `description` | — | — |
| 维度 | 虚拟标签 | `virtual_tag` | 仅支持按自身分组 | — |
| 度量 | 主键 | `primary_key` | 仅支持按自身分组 | COUNT() |
| 度量 | 普通数值 | `raw_number` | 支持 RANGE 范围分组 | SUM/AVG/MAX/MIN/TOPN/MEDIAN |
| 度量 | 普通指标 | `basic_metric` | 支持 RANGE 范围分组 | SUM/AVG/MAX/MIN/TOPN/MEDIAN |
| 度量 | 拍照指标 | `snapshot_metric` | 支持 RANGE 范围分组 | MAX/MIN/TOPN/MEDIAN |
| 度量 | 派生指标 | `derived_metric` | 支持 RANGE 范围分组 | —（比率类，不可二次聚合）|
| 度量 | 指标公式 | `formula_metric` | 支持 RANGE 范围分组 | SUM/AVG/MAX/MIN/TOPN/MEDIAN |

## role 与 rule_type 的合法组合

| property_role | 合法的 rule_type |
|---|---|
| `DIMENSION` | `id` / `name` / `datetime` / `period` / `numeric` / `description` / `virtual_tag` |
| `MEASURE` | `primary_key` / `raw_number` / `basic_metric` / `snapshot_metric` / `derived_metric` / `formula_metric` |

## 数据类型映射（OWL → SQLite）

| OWL data_type | SQLite 类型 |
|---------------|-------------|
| BIGINT / INT / INTEGER | INTEGER |
| FLOAT / DOUBLE / DECIMAL | REAL |
| BOOLEAN | INTEGER |
| VARCHAR / TEXT / STRING | TEXT |
| DATE / DATETIME / TIMESTAMP | TEXT |

## 术语类型（term_type）

| term_type | 含义 | 本期支持 |
|-----------|------|---------|
| `DICT_TERM` | 固定枚举值（如行业：IT/金融/制造） | ✅ |
| `LIST_TERM` | 动态枚举（来自数据库，如客户名称） | ❌（后续触发器实现）|

## 常见字段配置示例

**主键字段**（自动注入，无需用户填写）：
```json
{
  "property_code": "id",
  "property_name": "主键",
  "data_type": "BIGINT",
  "is_required": true,
  "ext_property": {"property_role_rule": {"property_role": "MEASURE", "rule_type": "primary_key"}}
}
```

**名称字段**：
```json
{
  "property_code": "customer_name",
  "property_name": "客户名称",
  "data_type": "VARCHAR",
  "is_required": true,
  "ext_property": {"property_role_rule": {"property_role": "DIMENSION", "rule_type": "name"}}
}
```

**时间字段**：
```json
{
  "property_code": "create_time",
  "property_name": "创建时间",
  "data_type": "DATETIME",
  "data_format": "yyyy-MM-dd HH:mm:ss",
  "ext_property": {"property_role_rule": {"property_role": "DIMENSION", "rule_type": "datetime"}}
}
```

**枚举字段（DICT_TERM）**：
```json
{
  "property_code": "industry",
  "property_name": "所属行业",
  "data_type": "VARCHAR",
  "ext_property": {"property_role_rule": {"property_role": "DIMENSION", "rule_type": "name"}},
  "term_type": "DICT_TERM",
  "term_values": [
    {"code": "IT", "name": "信息技术"},
    {"code": "FIN", "name": "金融"},
    {"code": "MFG", "name": "制造业"}
  ]
}
```

**度量字段**：
```json
{
  "property_code": "amount",
  "property_name": "金额",
  "data_type": "DECIMAL",
  "ext_property": {"property_role_rule": {"property_role": "MEASURE", "rule_type": "basic_metric"}}
}
```
