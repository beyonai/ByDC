---
name: data-analysis
description: 针对结构化数据集进行统计分析，包括描述性统计、相关性分析、异常检测、趋势分析
allowed_tools: [execute, read_file, write_file, emit_result]
metadata:
  category: analytics
  input_format: csv/json file path or inline data
  output_format: statistical summary + optional charts
---

# 数据分析技能

## 适用场景
- 用户要求"分析数据"、"统计摘要"、"找异常值"时
- 收到 CSV/JSON 格式数据需要提炼洞察时
- 需要计算同比/环比、增长率、排名等指标时
- 用户要求"描述性统计"、"相关性分析"、"离群值检测"时

## 执行步骤
1. 使用 `read_file` 读取数据文件（CSV/JSON）
2. 使用 `write_file` 创建分析脚本（`analysis_script.py`）
3. 脚本内容：加载数据 → 计算指标 → 输出结果到 `analysis_result.json`
4. 使用 `execute` 运行脚本
5. 使用 `read_file` 读取 `analysis_result.json`
6. 调用 `emit_result` 输出结果

## 分析脚本模板

```python
import pandas as pd
import json

# 读取数据
df = pd.read_csv("input.csv")  # 或 pd.read_json

# 描述性统计
stats = df.describe().to_dict()

# 数值列异常值检测（IQR 方法）
numeric_cols = df.select_dtypes(include="number").columns
outliers = {}
for col in numeric_cols:
    q1, q3 = df[col].quantile([0.25, 0.75])
    iqr = q3 - q1
    mask = (df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)
    outliers[col] = df[mask][col].tolist()

result = {"stats": stats, "outliers": outliers, "row_count": len(df)}
with open("analysis_result.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, default=str)
print("Analysis complete")
```

## 输出格式
```json
{
  "stats": { "列名": { "count": 100, "mean": 50.0, "std": 10.0, ... } },
  "outliers": { "金额": [9999.0, 0.1] },
  "row_count": 100
}
```
