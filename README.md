# easycode

个人学习项目：从零实现的一个集成式 Agent Harness（学习版 S15），基于 **DeepSeek + OpenAI SDK（Chat Completions 协议）**。

目标是把编码 Agent 运行时的各个核心机制亲手搭一遍，理解「prompt → model → tool calls → results → prompt」这个循环之外，任务板、多 Agent 协作、上下文管理这些工程问题是怎么解决的。

```
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
```

## 学到的东西 / 已实现的机制

- **Agent Loop**：工具分发、Hooks 拦截、输出截断恢复、定时/后台/团队事件注入
- **工具系统**：bash / 文件读写编辑 / glob / todo，Schema 与 handler 分离注册
- **任务板**：JSON 文件持久化、依赖图（防环）、跨线程/跨进程文件锁、认领与归属
- **多 Agent 协作**：队友独立线程与 Agent Loop、JSONL 信箱消息总线、计划审批 / 关闭协议、空闲自动认领任务
- **Git Worktree**：任务绑定独立工作目录，创建/移除都做失败保护
- **上下文压缩**：三层策略——工具结果预算 → 截断旧消息 → 模型摘要交接，另有超长报错后的应急压缩
- **错误恢复**：429/529 指数退避重试、备用模型降级
- **记忆**：长期记忆的提取、关键词检索、索引重建
- **Skills / MCP / Cron**：技能目录扫描按需加载、MCP 工具发现与权限策略、5 字段 cron 调度与持久化

## 目录结构

```
easycode/
├── code.py            # 入口：CLI 交互
├── agent/             # 核心层
│   ├── config.py      #   .env 加载、模型客户端、全局常量
│   ├── llm.py         #   OpenAI 协议封装（tool_calls / role=tool）
│   ├── loop.py        #   主 Agent Loop 与异步事件循环
│   ├── prompt.py      #   动态系统提示词
│   ├── memory.py      #   长期记忆
│   ├── skills.py      #   技能扫描与加载
│   ├── compaction.py  #   上下文压缩
│   ├── recovery.py    #   重试与降级
│   ├── hooks.py       #   权限校验 / 日志 Hooks
│   ├── subagent.py    #   子 Agent
│   └── console.py     #   控制台输入输出
├── tools/             # 工具层
│   ├── basic.py       #   文件 / Shell 基础工具
│   ├── tasks.py       #   任务板
│   ├── worktree.py    #   Git Worktree
│   ├── background.py  #   后台任务
│   ├── cron.py        #   定时任务
│   ├── mcp.py         #   MCP（内置 mock 服务）
│   └── registry.py    #   工具注册表与工具池合并
└── team/              # 协作层
    ├── bus.py         #   消息总线
    ├── protocol.py    #   审批 / 关闭协议
    ├── teammate.py    #   队友线程
    └── lead.py        #   Lead 管理工具
```

## 运行

需要 Python 3.10+。

```bash
pip install openai pyyaml

# 配置密钥（.env 已被 gitignore，不会入库）
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

python code.py
```

输入任务回车发送，`q` 退出。bash 工具执行前会询问确认。

`.env` 支持三项配置：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | API 密钥（必填） | 无 |
| `DEEPSEEK_BASE_URL` | 接口地址 | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 模型名 | `deepseek-v4-flash` |

## 说明

- 学习用途，MCP 部分是进程内 mock 实现，用于理解工具发现与权限策略的流程
- 运行时数据（`.tasks/`、`.memory/`、`.mailboxes/` 等）均在本地生成且已 gitignore
- 密钥只存本地 `.env`，仓库中不含任何真实凭据