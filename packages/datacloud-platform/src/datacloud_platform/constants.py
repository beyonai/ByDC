"""datacloud-platform 全局常量。

所有模块从本文件引用常量，避免分散硬编码。
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════
# 系统标识
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_SYSTEM_CODE = "BYCLAW_DATACLOUD"
"""默认系统标识 — 用于 ByClaw 同步、OpenGaussEntityStore 默认 base_id 等。
所有需要 systemCode / default_base_id 的模块统一从此引用。
"""
