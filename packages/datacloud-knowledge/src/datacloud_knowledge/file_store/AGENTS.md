# AGENTS.md

**Module:** file_store
**Purpose:** 文件存储抽象 — S3/本地双后端

---

## Overview

统一文件存储接口，支持 S3 和本地文件系统两种后端，提供上传、下载、URL 生成功能。

## Structure

```
file_store/
├── manager.py         # FileManager（主入口）
├── settings.py        # FileStoreSettings（配置）
├── types.py           # 类型定义
├── errors.py          # 异常
└── backends/
    ├── __init__.py
    ├── s3.py          # S3 后端
    └── local.py       # 本地后端
```

## Where to Look

| Task | Location |
|------|----------|
| 上传文件 | `manager.py:FileManager.upload_many()` |
| 下载文件 | `manager.py:FileManager.download_many()` |
| 生成下载 URL | `manager.py:FileManager.build_download_url()` |
| S3 实现 | `backends/s3.py` |
| 本地实现 | `backends/local.py` |

## Usage

```python
from datacloud_knowledge import FileManager, FileStoreSettings

# 从环境变量创建
manager = FileManager.from_settings(FileStoreSettings())

# 上传
results = manager.upload_many([{"path": "data/file.csv", "content": ...}])

# 生成下载 URL
url = manager.build_download_url(directory="uploads", filename="file.csv")
```

## Configuration

| Env Var | Purpose |
|---------|---------|
| `S3_ENDPOINT_URL` | S3 兼容端点 |
| `S3_ACCESS_KEY` | 访问密钥 |
| `S3_SECRET_KEY` | 秘密密钥 |
| `S3_BUCKET` | 存储桶 |
| `FILE_STORE_BACKEND` | `s3` 或 `local` |

## Notes

- 自动检测后端：有 S3 配置用 S3，否则本地
- 本地后端用于开发/测试