import re
from pathlib import Path

sql = Path("data/sql/01-crm_demo.sql").read_text(encoding="utf-8")
# 找 nextval 引用
matches = re.findall(r"nextval\(['\"]([^'\"]+)['\"]", sql)
print("nextval refs:", matches[:10])
