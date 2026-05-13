"""OpenGauss 后端适配器 — 术语读、搜、写的完整实现。

实现 contracts/ 层的三个协议：
- reader.py: PostgresTermReader ← contracts.TermReader
- engine.py: PostgresSearchEngine ← contracts.TermSearchEngine
- writer.py: PostgresTermWriter ← contracts.TermWriter

私有基础设施在 _db/ 子包中，外部不应直接导入。
"""
