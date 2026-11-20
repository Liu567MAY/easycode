"""子 Agent：可由主 Agent 直接调用的独立执行循环。"""

from agent.config import MODEL, WORKDIR
from agent.hooks import trigger_hooks
from agent.llm import (
    assistant_to_dict,
    chat_completion,
    extract_text,
    get_tool_requests,
    tool_result_message,
)
from tools.basic import (
    call_tool_handler,
    run_bash,
    run_edit,
    run_glob,
    run_read,
    run_write,
)

SUB_SYSTEM = (
    f"You are a coding subagent at {WORKDIR}. "
    "Complete the task, then return a concise final summary. "
    "Do not spawn more agents."
)


SUB_TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object",
                      "properties": {"command": {"type": "string"}},
                      "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "limit": {"type": "integer"},
                                     "offset": {"type": "integer"}},
                      "required": ["path"]}},
    {"name": "write_file", "description": "Write content to a file.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in a file once.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "old_text": {"type": "string"},
                                     "new_text": {"type": "string"}},
                      "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "Find files matching a glob pattern.",
     "input_schema": {"type": "object",
                      "properties": {"pattern": {"type": "string"}},
                      "required": ["pattern"]}},
]


SUB_HANDLERS = {
    "bash": run_bash, "read_file": run_read,
    "write_file": run_write, "edit_file": run_edit,
    "glob": run_glob,
}


def spawn_subagent(description: str) -> str:
    messages = [{"role": "user", "content": description}]
    for _ in range(30):
        response = chat_completion(MODEL, SUB_SYSTEM, messages, SUB_TOOLS, 8000)
        reply = response.choices[0].message
        messages.append(assistant_to_dict(reply))
        calls = get_tool_requests(reply)
        if not calls:
            break
        for block in calls:
            blocked = trigger_hooks("PreToolUse", block)
            if blocked:
                output = str(blocked)
            else:
                handler = SUB_HANDLERS.get(block.name)
                output = call_tool_handler(handler, block.input, block.name)
                trigger_hooks("PostToolUse", block, output)
            messages.append(tool_result_message(block.id, output))
    for msg in reversed(messages):
        if msg["role"] == "assistant":
            result = extract_text(msg["content"])
            if result:
                return result
    return "子 Agent 执行结束，但没有返回文字总结。"