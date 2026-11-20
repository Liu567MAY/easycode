#!/usr/bin/env python3
"""
s15: Integrated Harness - OpenAI Chat Completions 版本（模块化结构）。

目录说明：
    code.py          入口：CLI 交互与启动
    agent/           核心层：配置(config)、模型协议(llm)、提示词(prompt)、
                     记忆(memory)、技能(skills)、上下文压缩(compaction)、
                     错误恢复(recovery)、Hooks(hooks)、子 Agent(subagent)、
                     主循环(loop)、控制台(console)
    tools/           工具层：文件/Shell(basic)、任务板(tasks)、Worktree(worktree)、
                     后台任务(background)、定时任务(cron)、MCP(mcp)、
                     工具注册表(registry)
    team/            协作层：消息总线(bus)、协作协议(protocol)、
                     队友线程(teammate)、Lead 管理工具(lead)

Run:  python code.py
Need: pip install openai pyyaml
配置: 复制 .env.example 为 .env，填入 DEEPSEEK_API_KEY（.env 已被 gitignore）。

    scheduled work ----+                    +---- team events
                       v                    v
    +---------------------------------------------------+
    | Agent loop                                        |
    | prompt -> model -> tool calls -> results -> prompt |
    +-------------------------+-------------------------+
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
    built-in tools      persistent teams      MCP tools
"""

import threading

from agent import config
from agent.console import CONSOLE
from agent.hooks import trigger_hooks
from agent.loop import (
    agent_lock,
    agent_loop,
    async_event_loop,
    print_turn_assistants,
    update_context,
)
from tools.cron import start_runtime_services

if __name__ == "__main__":
    config.CLI_ACTIVE = True
    start_runtime_services()
    print("S15：DeepSeek + OpenAI SDK 集成式 Agent Harness")
    print("请输入任务，按 Enter 发送；输入 q 退出。\n")
    history = []
    context = update_context({}, [])
    session_state = {"active_user_request": "(no active user request)"}
    threading.Thread(target=async_event_loop,
                     args=(history, context, session_state), daemon=True).start()
    while True:
        try:
            query = CONSOLE.ask(config.PROMPT)
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        with agent_lock:
            trigger_hooks("UserPromptSubmit", query)
            turn_start = len(history)
            session_state["active_user_request"] = query
            history.append({"role": "user", "content": query})
            agent_loop(history, context, query)
            context = update_context(context, history)
            print_turn_assistants(history, turn_start)
        print()