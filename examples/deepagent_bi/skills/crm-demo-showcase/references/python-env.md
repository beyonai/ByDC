# Python 环境参考

## 环境变量

| 变量 | 说明 | 必需 |
|------|------|------|
| `BEYOND_TOKEN` | 门户服务认证 Token | ✅ |
| `USER_CODE` | 当前用户编码 | ✅ |
| `BE_DOMAINNAME` | 默认 `ByaiService` | 否 |
| `REDIS_HOST` | Redis 主机 | 否 |
| `REDIS_PORT` | 默认 `6379` | 否 |
| `REDIS_PASSWORD` | Redis 密码 | 否 |

## 脚本路径约定

所有脚本以 skill 根目录为基准，通过 `/tmp/ont_env/bin/python` 执行：

```bash
export BE_DOMAINNAME=${BE_DOMAINNAME:-ByaiService}

# 结构化本体
/tmp/ont_env/bin/python scripts/ontology/structured/<script>.py '<JSON>'

# 非结构化本体
/tmp/ont_env/bin/python scripts/ontology/unstructured/<script>.py '<JSON>'

# 周报/会议纪要
/tmp/ont_env/bin/python scripts/weekly-report/<script>.py [--args]
```

> `list_mounted_resources.py` 的 `resource_id` 是 Agent 自身的数字后缀（如 `agent-10014603` → `10014603`），**不是** baiying_call 用的业务 resourceId。

## 手动安装（备选）

若 `bash scripts/setup.sh` 不可用：

```bash
export PATH="$HOME/.local/bin:$PATH"
which uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
[ -f /tmp/ont_env/bin/python ] || uv venv --python 3.12 --link-mode copy /tmp/ont_env
uv pip install --python /tmp/ont_env/bin/python -r scripts/requirements.txt \
  -i https://mirrors.aliyun.com/pypi/simple/ --extra-index-url https://pypi.org/simple/
```
