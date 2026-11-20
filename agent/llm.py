"""OpenAI Chat Completions：统一模型请求和工具格式。

核心规则：assistant 用 tool_calls 发起调用；Python 执行；role=tool 回传结果。
"""

import json
from dataclasses import dataclass

from agent.config import client


@dataclass
class ToolRequest:
    # Python 本地的工具请求结构，用来复用工具分发与 Hooks。
    id: str
    name: str
    input: dict


def to_openai_tools(tools):
    converted = []
    for tool in tools:
        converted.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool["input_schema"],
            },
        })
    return converted


def chat_completion(model, system, messages, tools=None, max_tokens=8000):
    kwargs = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = to_openai_tools(tools)
    return client.chat.completions.create(**kwargs)


def assistant_to_dict(message):
    # SDK 对象转换为普通 dict，方便写入历史消息及 JSON transcript。
    result = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        result["tool_calls"] = []
        for call in message.tool_calls:
            result["tool_calls"].append({
                "id": call.id, "type": "function",
                "function": {"name": call.function.name,
                             "arguments": call.function.arguments or "{}"},
            })
    return result


def get_tool_requests(message):
    requests = []
    for call in message.tool_calls or []:
        try:
            args = json.loads(call.function.arguments or "{}")
            if not isinstance(args, dict):
                args = {}
        except json.JSONDecodeError:
            args = {}
        requests.append(ToolRequest(call.id, call.function.name, args))
    return requests


def tool_result_message(tool_id, output):
    return {"role": "tool", "tool_call_id": tool_id, "content": str(output)}


def extract_text(content) -> str:
    # OpenAI 的 assistant.content 是字符串，不再是内容块数组。
    if isinstance(content, str):
        return content.strip()
    return ""


def has_tool_use(message) -> bool:
    return bool(message.tool_calls)