# Python 环境搭建

数据操作和本体管理（演示四/五/六）依赖 Python 环境。纯 `baiying_call` 查询（演示一/二/三）无需此环境。

## 首次搭建

```bash
export PATH="$HOME/.local/bin:$PATH"
which uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
[ -f /tmp/ont_env/bin/python ] || uv venv --python 3.12 --link-mode copy /tmp/ont_env

uv pip install --python /tmp/ont_env/bin/python by-datacloud by-framework \
  -i https://mirrors.aliyun.com/pypi/simple/ --extra-index-url https://pypi.org/simple/

# 验证
/tmp/ont_env/bin/python -c "import by_framework; import by_datacloud; print('OK')"
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `BEYOND_TOKEN` | 门户服务认证 Token |
| `USER_CODE` | 当前用户编码 |
| `BE_DOMAINNAME` | 默认 `ByaiService` |
| `REDIS_HOST` | Redis 主机 |
| `REDIS_PORT` | 默认 `6379` |
| `REDIS_PASSWORD` | Redis 密码 |

## 脚本路径约定

所有脚本以 skill 根目录为基准，通过 `/tmp/ont_env/bin/python` 执行：

```bash
export BE_DOMAINNAME=${BE_DOMAINNAME:-ByaiService}

# 统一调用格式
/tmp/ont_env/bin/python scripts/ontology/structured/<script>.py '<JSON>'
/tmp/ont_env/bin/python scripts/ontology/unstructured/<script>.py '<JSON>'
/tmp/ont_env/bin/python scripts/weekly-report/<script>.py [--args]

# baiying_call 前置校验（查全部已挂载资源，返回后按 resourceCode 匹配）
/tmp/ont_env/bin/python scripts/ontology/structured/list_mounted_resources.py \
  '{"resource_id": <Agent的resource_id>}'

# 可选：按名称过滤（keyword 匹配 resourceName 中文名，如"综合分析"）
# /tmp/ont_env/bin/python ... '{"resource_id": <id>, "keyword": "综合分析"}'
```

> `list_mounted_resources.py` 的 `resource_id` 是当前 Agent 自身的 ID（从 Agent 编码中的数字后缀提取），**不是** baiying_call 所用的 `resource_id=10000104`。
