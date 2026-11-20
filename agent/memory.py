"""记忆模块：读取 / 检索 / 提取 / 持久化长期记忆。"""

import json
import re

import yaml

from agent.config import MODEL, WORKDIR
from agent.llm import chat_completion
from agent.utils import parse_frontmatter


class MemoryRuntime:
    def __init__(self):
        self.memory_dir = WORKDIR / ".memory"
        self.memory_index = self.memory_dir / "MEMORY.md"

    def list_memories(self):
        records = []
        if not self.memory_dir.exists():
            return records
        for path in sorted(self.memory_dir.glob("*.md")):
            if path.name == "MEMORY.md" or not path.resolve().is_relative_to(self.memory_dir.resolve()):
                continue
            raw = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(raw)
            records.append({"filename": path.name, "name": meta.get("name", path.stem),
                            "description": meta.get("description", ""), "body": body})
        return records

    def rebuild_index(self):
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        lines = []
        for item in self.list_memories():
            lines.append(f"- [{item['name']}]({item['filename']}) - {item['description']}")
        self.memory_index.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def read_memory_index(self):
        if self.memory_index.is_file():
            return self.memory_index.read_text(encoding="utf-8").strip()
        return ""

    def load_memories(self, messages):
        # 先按关键词筛选，避免每一轮都额外请求一次模型。
        records = self.list_memories()
        if not records:
            return ""
        user_texts = []
        for item in messages[-6:]:
            if item.get("role") == "user":
                user_texts.append(str(item.get("content", "")))
        recent = " ".join(user_texts)
        keywords = re.findall(r"[a-z0-9_]{3,}|[一-鿿]{2,}", recent.lower())
        ranked = []
        for item in records:
            title = f"{item['name']} {item['description']}".lower()
            score = sum(word in title for word in keywords)
            if score:
                ranked.append((score, item))
        ranked.sort(key=lambda pair: -pair[0])
        selected = [item for _, item in ranked[:5]]
        return json.dumps(selected, ensure_ascii=False)[:20000] if selected else ""

    def extract_memories(self, messages):
        # 仅存长期有效的信息；临时要求（如“本次会话”）不记忆。
        recent = []
        for item in messages[-12:]:
            if item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
                recent.append(f"{item['role']}: {item['content'][:1500]}")
        if not recent:
            return False
        instructions = (
            "提取对未来会话持续有用的事实和偏好。只返回 JSON 数组。"
            "每项必须有 scope='persistent'、type（user/feedback/project/reference）、"
            "name、description、body 字段。不要提取临时任务、一次性问题、敏感个人信息，"
            "不确定是否长期有效就返回 []。示例：[]。"
        )
        try:
            chat_messages = [{"role": "user", "content": "\n".join(recent)}]
            response = chat_completion(MODEL, instructions, chat_messages, max_tokens=700)
            raw = response.choices[0].message.content or "[]"
            # 部分兼容服务会将 JSON 包在 Markdown 中。
            match = re.search(r"\[[\s\S]*\]", raw)
            candidates = json.loads(match.group(0) if match else raw)
            if not isinstance(candidates, list):
                return False
        except Exception as exc:
            print(f"[记忆] 提取失败，本轮跳过：{exc}")
            return False
        known = self.list_memories()
        existing = " ".join(str(item["name"]).lower() for item in known)
        count = 0
        for item in candidates[:5]:
            if not isinstance(item, dict) or item.get("scope") != "persistent":
                continue
            if item.get("type") not in ("user", "feedback", "project", "reference"):
                continue
            name = str(item.get("name", "")).strip()
            description = str(item.get("description", "")).strip()
            body = str(item.get("body", "")).strip()
            if not name or not description or not body or name.lower() in existing:
                continue
            text = f"{name} {description} {body}".lower()
            if any(word in text for word in ("本次会话", "这次任务", "临时", "今天", "仅这次", "this session", "for now")):
                continue
            slug = re.sub(r"[^a-zA-Z0-9_一-鿿-]", "-", name).strip("-")[:60]
            if not slug:
                continue
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            path = self.memory_dir / f"{slug}.md"
            if path.exists():
                continue
            meta = yaml.safe_dump({"name": name, "description": description,
                                   "type": item["type"]}, allow_unicode=True, sort_keys=False).strip()
            path.write_text(f"---\n{meta}\n---\n\n{body}\n", encoding="utf-8")
            count += 1
        if count:
            self.rebuild_index()
            print(f"[记忆] 新增长期记忆 {count} 条")
        return count > 0

    def consolidate_memories(self):
        self.rebuild_index()


MEMORY_RUNTIME = MemoryRuntime()