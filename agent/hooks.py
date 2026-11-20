"""Hooks：权限校验与日志扩展。

Hooks 独立于业务工具；权限、日志、停止事件都可单独挂载。
"""

import threading

from agent.config import WORKDIR
from agent.console import CONSOLE, terminal_print

HOOKS = {"UserPromptSubmit": [], "PreToolUse": [],
         "PostToolUse": [], "Stop": []}


def register_hook(event: str, callback):
    HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result
    return None


DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
# MCP 工具权限策略；由 tools.registry.assemble_tool_pool 在合并工具池时刷新。
mcp_tool_policies: dict[str, str] = {}


def permission_hook(block):
    # 工具执行前检查权限：允许、拒绝或询问用户。
    if block.name == "bash":
        command = block.input.get("command", "")
        if not isinstance(command, str):
            return "Permission denied: shell command must be a string"
        for pattern in DENY_LIST:
            if pattern in command:
                return f"Permission denied: '{pattern}' is on the deny list"
        if threading.current_thread() is not threading.main_thread():
            return ("Permission denied: interactive shell approval is unavailable "
                    "during an asynchronous turn")
        terminal_print("\n\033[33m[permission] shell command\033[0m")
        terminal_print(f"  {command}")
        choice = CONSOLE.ask("  Allow? [y/N] ").strip().lower()
        if choice not in ("y", "yes"):
            return "Permission denied by user"
    if block.name in ("read_file", "write_file", "edit_file"):
        path = block.input.get("path", "")
        if not isinstance(path, str):
            return "Permission denied: path must be a string"
        if not (WORKDIR / path).resolve().is_relative_to(WORKDIR):
            return "Permission denied: path is outside the workspace"
    if (block.name.startswith("mcp__")
            and mcp_tool_policies.get(block.name, "confirm") != "allow"):
        if threading.current_thread() is not threading.main_thread():
            return ("Permission denied: interactive MCP approval is unavailable "
                    "during an asynchronous turn")
        terminal_print(f"\n\033[33m[permission] MCP tool: {block.name}\033[0m")
        choice = CONSOLE.ask("  Allow? [y/N] ").strip().lower()
        if choice not in ("y", "yes"):
            return "Permission denied by user"
    return None


def log_hook(block):
    print(f"\033[90m[HOOK] {block.name}\033[0m")
    return None


def large_output_hook(block, output):
    if len(str(output)) > 100000:
        print(f"\033[33m[HOOK] {block.name} 输出过长："
              f"{len(str(output))} chars\033[0m")
    return None


def user_prompt_hook(query: str):
    print(f"\033[90m[HOOK] UserPromptSubmit: {WORKDIR}\033[0m")
    return None


def stop_hook(messages: list):
    count = sum(1 for item in messages if item.get("role") == "tool")
    print(f"\033[90m[HOOK] Stop: {count} 条工具结果\033[0m")
    return None


register_hook("UserPromptSubmit", user_prompt_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", stop_hook)