"""数据可视化技能执行脚本。

通过 SkillsMiddleware / execute 工具调用，将数据生成为 PNG 图表文件。

用法（由 Agent 通过 execute 工具调用）::

    python run.py --input data.csv --output chart.png --type line
    python run.py --input data.csv --output chart.png --type bar --x-col 月份
"""

from __future__ import annotations

import argparse
import sys


def make_chart(
    input_path: str,
    output_path: str,
    chart_type: str = "bar",
    x_col: str | None = None,
) -> None:
    try:
        import matplotlib  # noqa: PLC0415
        import matplotlib.pyplot as plt  # noqa: PLC0415
        import pandas as pd  # noqa: PLC0415
    except ImportError as exc:
        print(f"依赖未安装: {exc}。请运行: pip install pandas matplotlib", file=sys.stderr)
        sys.exit(1)

    # 中文字体支持
    matplotlib.rcParams["font.family"] = ["SimHei", "WenQuanYi Micro Hei", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False

    df = pd.read_csv(input_path) if input_path.endswith(".csv") else pd.read_json(input_path)

    x_column = x_col or df.columns[0]
    y_columns = [c for c in df.columns if c != x_column]

    fig, ax = plt.subplots(figsize=(10, 6))

    if chart_type == "line":
        for col in y_columns:
            ax.plot(df[x_column], df[col], marker="o", label=col)
        ax.legend()
    elif chart_type == "bar":
        df.set_index(x_column)[y_columns].plot(kind="bar", ax=ax)
    elif chart_type == "pie" and y_columns:
        col = y_columns[0]
        ax.pie(df[col], labels=df[x_column], autopct="%1.1f%%")
        ax.set_title(col)
    elif chart_type == "scatter" and len(y_columns) >= 1:
        y_col = y_columns[0]
        ax.scatter(df[x_column], df[y_col], alpha=0.7)
        ax.set_xlabel(x_column)
        ax.set_ylabel(y_col)
    else:
        df.set_index(x_column)[y_columns].plot(ax=ax)

    ax.set_title(f"{chart_type.capitalize()} Chart")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Chart saved: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="数据可视化技能")
    parser.add_argument("--input", required=True, help="输入文件路径 (CSV/JSON)")
    parser.add_argument("--output", default="chart.png", help="输出图片路径")
    parser.add_argument(
        "--type",
        default="bar",
        choices=["line", "bar", "pie", "scatter"],
        help="图表类型",
    )
    parser.add_argument("--x-col", help="X 轴列名（默认第一列）")
    args = parser.parse_args()
    make_chart(args.input, args.output, args.type, args.x_col)
