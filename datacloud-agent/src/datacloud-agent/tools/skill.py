"""T_SKILL_BUILD — distil analysis patterns into reusable skill plugins (design §3.1).

When the Agent identifies a reusable analysis pattern during a task it
calls ``build_skill`` to generate a conformant ``.py`` skill file and
save it to the user's private skills directory.

The generated file follows the SKILL_META + run() convention understood
by ``workspace.skills_loader.SkillLoader``.
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def build_skill(
    name: str,
    description: str,
    code: str,
    skills_private_dir: str,
    version: str = "1.0.0",
) -> str:
    """Generate and save a reusable skill plugin to the user's private skill library.

    The coding LLM is expected to produce the ``code`` argument (the full
    ``run()`` function body).  This tool wraps it in the required file
    structure and writes it to disk.

    Args:
        name:               Skill name (used as filename and ``SKILL_META["name"]``).
        description:        Human-readable description for prompt injection.
        code:               The ``run(...)`` function source (body only or full def).
        skills_private_dir: Absolute path to the user's private skills directory.
        version:            Semantic version string.

    Returns:
        Absolute path of the saved skill file.
    """
    dest_dir = Path(skills_private_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"{name}.py"

    # Ensure the provided code is a complete function definition.
    if not code.strip().startswith("def run"):
        code = f"def run(*args, **kwargs):\n{textwrap.indent(code, '    ')}"

    skill_source = textwrap.dedent(f'''\
        """User skill: {name} — {description}"""

        SKILL_META = {{
            "name": "{name}",
            "description": "{description}",
            "version": "{version}",
            "author": "agent",
        }}

        {code}
    ''')

    dest_file.write_text(skill_source, encoding="utf-8")
    logger.info("build_skill: saved '%s' to %s", name, dest_file)
    return str(dest_file)
