import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

sql = Path("data/sql/01-crm_demo.sql").read_text(encoding="utf-8")
# 找 nextval 引用
matches = re.findall(r"nextval\(['\"]([^'\"]+)['\"]", sql)
logger.info("nextval refs: %s", matches[:10])
