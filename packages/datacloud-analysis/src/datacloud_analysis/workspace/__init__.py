"""Workspace package — file-system path management and sandbox mounting.

Sub-modules
-----------
mount          Mount inputs/temp/outputs/skills into a sandbox backend.
skills_loader  Scan & register built-in / enterprise / user skills.
"""

from .skills_loader import SkillLoader

__all__ = ["SkillLoader"]
