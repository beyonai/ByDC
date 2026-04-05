"""数据分析技能执行脚本。

通过 SkillsMiddleware / execute 工具调用，对 CSV/JSON 数据进行统计分析。

用法（由 Agent 通过 execute 工具调用）::

    python run.py --input data.csv --output result.json
    python run.py --input data.json --output result.json --format json
"""

from __future__ import annotations

import argparse
import json
import sys


def analyze(input_path: str, output_path: str, fmt: str = "csv") -> dict:
    try:
        import pandas as pd  # noqa: PLC0415
    except ImportError:
        print("pandas 未安装，请运行: pip install pandas", file=sys.stderr)
        sys.exit(1)

    if fmt == "json":
        df = pd.read_json(input_path)
    else:
        df = pd.read_csv(input_path)

    # 描述性统计
    stats = {}
    for col in df.select_dtypes(include="number").columns:
        stats[col] = {
            "count": int(df[col].count()),
            "mean": float(df[col].mean()),
            "std": float(df[col].std()),
            "min": float(df[col].min()),
            "max": float(df[col].max()),
            "q25": float(df[col].quantile(0.25)),
            "q75": float(df[col].quantile(0.75)),
        }

    # 异常值检测（IQR 方法）
    outliers: dict = {}
    for col in df.select_dtypes(include="number").columns:
        q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
        iqr = q3 - q1
        mask = (df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)
        vals = df[mask][col].tolist()
        if vals:
            outliers[col] = vals

    result = {
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns": list(df.columns),
        "stats": stats,
        "outliers": outliers,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, default=str, indent=2)

    print(f"Analysis complete: {len(df)} rows, {len(stats)} numeric columns")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="数据分析技能")
    parser.add_argument("--input", required=True, help="输入文件路径 (CSV/JSON)")
    parser.add_argument("--output", default="analysis_result.json", help="输出结果文件路径")
    parser.add_argument("--format", default="csv", choices=["csv", "json"], help="输入文件格式")
    args = parser.parse_args()
    analyze(args.input, args.output, args.format)
