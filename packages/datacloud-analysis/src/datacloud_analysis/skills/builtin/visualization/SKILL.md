---
name: visualization
description: 将数据生成为可视化图表（折线图、柱状图、饼图、散点图），输出为 PNG 文件
allowed_tools: [execute, read_file, write_file, emit_result]
metadata:
  category: visualization
  input_format: csv/json file path or inline data dict
  output_format: png image file path
---

# 数据可视化技能

## 适用场景
- 用户要求"画图"、"生成图表"、"可视化"时
- 需要折线图（趋势）、柱状图（对比）、饼图（占比）、散点图（相关性）时
- 数据分析结果需要图形化呈现时

## 执行步骤
1. 使用 `read_file` 读取数据文件或接收内联数据
2. 使用 `write_file` 创建绘图脚本（`chart_script.py`）
3. 使用 `execute` 运行脚本，生成 PNG 文件
4. 调用 `emit_result(result_type="csv_file", file_path="chart.png")` 输出

## 图表脚本模板

### 折线图（趋势分析）
```python
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams["font.family"] = ["SimHei", "DejaVu Sans"]

df = pd.read_csv("data.csv")
plt.figure(figsize=(10, 6))
for col in df.columns[1:]:  # 假设第一列为 X 轴
    plt.plot(df.iloc[:, 0], df[col], marker="o", label=col)
plt.title("趋势图")
plt.xlabel(df.columns[0])
plt.legend()
plt.tight_layout()
plt.savefig("chart.png", dpi=150)
print("Chart saved: chart.png")
```

### 柱状图（对比分析）
```python
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams["font.family"] = ["SimHei", "DejaVu Sans"]

df = pd.read_csv("data.csv")
ax = df.set_index(df.columns[0]).plot(kind="bar", figsize=(10, 6))
ax.set_title("对比图")
plt.tight_layout()
plt.savefig("chart.png", dpi=150)
print("Chart saved: chart.png")
```

## 注意事项
- 中文显示需设置 `matplotlib.rcParams["font.family"] = ["SimHei", "DejaVu Sans"]`
- 输出文件命名建议加时间戳避免覆盖：`chart_{timestamp}.png`
- 若 matplotlib 未安装，提示用户：`pip install matplotlib`
