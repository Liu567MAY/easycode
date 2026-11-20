"""Skills：扫描技能目录并按需加载。"""

from agent.config import SKILLS_DIR
from agent.utils import parse_frontmatter

SKILL_REGISTRY: dict[str, dict] = {}


def scan_skills():
    SKILL_REGISTRY.clear()
    if not SKILLS_DIR.exists():
        return
    skills_root = SKILLS_DIR.resolve()
    for directory in sorted(SKILLS_DIR.iterdir()):
        if not directory.is_dir():
            continue
        manifest = directory / "SKILL.md"
        if not manifest.exists():
            continue
        if not manifest.resolve().is_relative_to(skills_root):
            continue
        raw = manifest.read_text()
        meta, body = parse_frontmatter(raw)
        raw_name = meta.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        name = name or directory.name
        raw_desc = meta.get("description")
        desc = raw_desc.strip() if isinstance(raw_desc, str) else ""
        desc = desc or body.split("\n", 1)[0].lstrip("#").strip()
        SKILL_REGISTRY[name] = {
            "name": name,
            "description": desc,
            "content": raw,
        }


scan_skills()


def list_skills() -> str:
    if not SKILL_REGISTRY:
        return "(no skills found)"
    return "\n".join(
        f"- {skill['name']}: {skill['description']}"
        for skill in SKILL_REGISTRY.values())


def load_skill(name: str) -> str:
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        available = ", ".join(SKILL_REGISTRY.keys()) or "(none)"
        return f"Skill not found: {name}. Available: {available}"
    return skill["content"]