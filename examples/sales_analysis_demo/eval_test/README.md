# Eval Test

该目录用于对 `sales_analysis_demo` Agent 做准确性与性能评测。

## 子目录

- `cases/`: 评测样例（输入、期望、标签）
- `configs/`: 评测运行配置（模型、并发、超时、阈值）
- `reports/`: 每次评测结果产物（建议不入库大文件）
- `baselines/`: 基线结果（用于回归对比）

## 使用

```bash
bash run_eval.sh
```
