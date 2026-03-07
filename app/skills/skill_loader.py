"""
Loads named prompt sections from a SKILL.md file.

WHY this exists: All agent prompts live in SKILL.md files under
app/skills/{agent-name}/SKILL.md. This utility parses them and serves
them to Python code by section key. No prompt text ever appears in Python.

Sections are delimited by ### headers followed by a fenced code block:
    ### Section Name (`SECTION_KEY`)
    ```
    ...prompt text...
    ```

Usage:
    loader = SkillLoader("claude-trade-agent")
    system = loader.get("BATCH_TRIAGE_SYSTEM")
    user = loader.render("BATCH_TRIAGE_USER", symbol="QQQ", current_price=459.44)

    # Or use the cached module-level helper:
    from app.skills.skill_loader import get_skill
    prompt = get_skill("claude-trade-agent").render("DEEP_DIVE_USER", **context)
"""

import re
from pathlib import Path
from functools import lru_cache


class SkillLoader:
    SKILLS_DIR = Path(__file__).parent

    def __init__(self, skill_name: str):
        skill_path = self.SKILLS_DIR / skill_name / "SKILL.md"
        if not skill_path.exists():
            raise FileNotFoundError(
                f"SKILL.md not found at {skill_path}. "
                f"Expected: app/skills/{skill_name}/SKILL.md"
            )
        text = skill_path.read_text(encoding="utf-8")
        self._sections = self._parse(text)
        self.prompt_version = self._extract_version(text)

    def get(self, section_name: str) -> str:
        """Return the raw text of a named prompt section."""
        if section_name not in self._sections:
            available = ", ".join(sorted(self._sections.keys()))
            raise KeyError(
                f"Prompt section '{section_name}' not found in SKILL.md. "
                f"Available sections: {available}"
            )
        return self._sections[section_name]

    def render(self, section_name: str, **kwargs) -> str:
        """
        Render a prompt template, filling {{variable}} slots.

        Also handles {{#if var}}...{{/if}} conditional blocks —
        the block is included only if the variable is truthy.
        """
        template = self.get(section_name)
        template = self._process_conditionals(template, kwargs)
        for key, value in kwargs.items():
            template = template.replace(f"{{{{{key}}}}}", str(value) if value is not None else "")
        return template

    def list_sections(self) -> list[str]:
        """Return all available section keys in this SKILL.md."""
        return sorted(self._sections.keys())

    def _parse(self, text: str) -> dict:
        """
        Extract named fenced code blocks from markdown.

        Looks for the pattern:
            ### Any Title Text (`SECTION_KEY`)
            ```[optional language]
            ...content...
            ```
        """
        pattern = r"###.*?\(`([A-Z_]+)`\)\n\n```[a-z]*\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        return {name: content.strip() for name, content in matches}

    def _process_conditionals(self, template: str, ctx: dict) -> str:
        """
        Process {{#if var}}...{{/if}} blocks.

        If the variable is truthy, the block content is kept (with the
        tags removed). If falsy, the entire block is removed.
        """
        pattern = r"\{\{#if (\w+)\}\}(.*?)\{\{/if\}\}"

        def replace(m):
            var, block = m.group(1), m.group(2)
            return block if ctx.get(var) else ""

        return re.sub(pattern, replace, template, flags=re.DOTALL)

    def _extract_version(self, text: str) -> str:
        """Pull the version field from the YAML frontmatter."""
        match = re.search(r"^version:\s*(.+)$", text, re.MULTILINE)
        return match.group(1).strip() if match else "unversioned"


@lru_cache(maxsize=16)
def get_skill(skill_name: str) -> SkillLoader:
    """
    Return a cached SkillLoader for the given agent name.

    WHY lru_cache: SKILL.md files are read once at first call and
    reused for the lifetime of the process. No file I/O on every
    request. Cache holds up to 16 skill loaders (more than enough).
    """
    return SkillLoader(skill_name)
