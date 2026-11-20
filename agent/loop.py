"""主 Agent Loop：理解整个 Harness 最重要的入口。

一轮执行：注入任务 -> 整理上下文 -> 请求模型 -> 执行工具 -> 回传结果。
"""

import threading
import time

from agent.compaction import (
    compact_history,
    estimate_size,
    micro_compact,
    reactive_compact,
    snip_compact,
    tool_result_budget,
)
from agent.config import (
    CONTEXT_LIMIT,
    CONTINUATION_PROMPT,
    DEFAULT_MAX_TOKENS,
    ESCALATED_MAX_TOKENS,
    MAX_RECOVERY_RETRIES,
)
from agent.console import terminal_print
from agent.hooks import trigger_hooks
from agent.llm import (
    assistant_to_dict,
    chat_completion,
    get_tool_requests,
    tool_result_message,
)
from agent.memory import MEMORY_RUNTIME
from agent.prompt import assemble_system_prompt
from agent.recovery import RecoveryState, is_prompt_too_long_error, with_retry
from team.protocol import active_teammates, consume_lead_inbox, format_team_events
from tools.background import (
    collect_background_results,
    has_pending_background,
    should_run_background,
    start_background_task,
)
from tools.basic import call_tool_handler
from tools.cron import (
    CronJob,
    acknowledge_cron_jobs,
    consume_cron_queue,
    cron_lock,
    cron_queue,
    restore_cron_jobs,
)
from tools.mcp import mcp_clients
from tools.registry import assemble_tool_pool
from tools.tasks import release_completed_assignment

rounds_since_todo = 0
agent_lock = threading.Lock()


def update_context(context: dict, messages: list) -> dict:
    return {
        "memory_catalog": MEMORY_RUNTIME.read_memory_index(),
        "memories": MEMORY_RUNTIME.load_memories(messages),
        "connected_mcp": list(mcp_clients.keys()),
        "active_teammates": list(active_teammates.keys()),
    }


def remember_after_turn(messages: list) -> None:
    if MEMORY_RUNTIME.extract_memories(messages):
        MEMORY_RUNTIME.consolidate_memories()


def prepare_context(messages: list, active_request: str) -> list:
    # 每次请求模型前统一压缩过长的对话历史。
    messages[:] = tool_result_budget(messages)
    messages[:] = snip_compact(messages)
    messages[:] = micro_compact(messages)
    if estimate_size(messages) > CONTEXT_LIMIT:
        messages[:] = compact_history(messages, active_request)
    return messages


def append_background_notifications(messages: list):
    for note in collect_background_results():
        messages.append({"role": "user", "content": note})


def inject_background_notifications(messages: list):
    append_background_notifications(messages)


def call_llm(messages: list, context: dict, tools: list,
             state: RecoveryState, max_tokens: int):
    system = assemble_system_prompt(context)
    return with_retry(
        lambda: chat_completion(state.current_model, system, messages, tools, max_tokens),
        state)


def agent_loop(messages: list, context: dict, active_request: str):
    global rounds_since_todo
    tools, handlers = assemble_tool_pool()
    state = RecoveryState()
    max_tokens = DEFAULT_MAX_TOKENS

    unacknowledged_cron_jobs: list[CronJob] = []
    while True:
        fired = consume_cron_queue()
        unacknowledged_cron_jobs.extend(fired)
        for job in fired:
            messages.append({"role": "user",
                             "content": f"[Scheduled] {job.prompt}"})
            print(f"  \033[35m[定时任务注入] {job.prompt[:60]}\033[0m")
        if fired:
            scheduled_requests = "\n".join(
                f"Run scheduled task: {job.prompt}" for job in fired)
            active_request = f"{active_request}\n{scheduled_requests}".strip()

        inject_background_notifications(messages)

        if rounds_since_todo >= 3:
            messages.append({"role": "user",
                             "content": "<reminder>Update your todos.</reminder>"})
            rounds_since_todo = 0

        prepare_context(messages, active_request)
        context = update_context(context, messages)
        tools, handlers = assemble_tool_pool()

        try:
            response = call_llm(messages, context, tools, state, max_tokens)
        except Exception as e:
            if is_prompt_too_long_error(e) and not state.has_attempted_reactive_compact:
                messages[:] = reactive_compact(messages, active_request)
                state.has_attempted_reactive_compact = True
                continue
            restore_cron_jobs(unacknowledged_cron_jobs)
            messages.append({"role": "assistant", "content": f"[错误] {type(e).__name__}: {e}"})
            release_completed_assignment("agent")
            return

        acknowledge_cron_jobs(unacknowledged_cron_jobs)
        unacknowledged_cron_jobs.clear()

        reply = response.choices[0].message
        if response.choices[0].finish_reason == "length":
            if not state.has_escalated:
                max_tokens = ESCALATED_MAX_TOKENS
                state.has_escalated = True
                print(f"  \033[33m[输出截断] 增加输出上限至 {max_tokens} 并重试\033[0m")
                continue
            # 输出长度被截断时，工具参数可能不完整；不可把未完成的工具调用放进历史。
            if reply.content:
                messages.append({"role": "assistant", "content": reply.content})
            if state.recovery_count < MAX_RECOVERY_RETRIES:
                messages.append({"role": "user", "content": CONTINUATION_PROMPT})
                state.recovery_count += 1
                continue
            release_completed_assignment("agent")
            return

        max_tokens = DEFAULT_MAX_TOKENS
        state.has_escalated = False
        messages.append(assistant_to_dict(reply))
        calls = get_tool_requests(reply)
        if not calls:
            trigger_hooks("Stop", messages)
            remember_after_turn(messages)
            release_completed_assignment("agent")
            return

        results = []
        compact_requested = False
        for block in calls:
            print(f"\033[36m> 调用工具：{block.name}\033[0m")

            if block.name == "compact":
                results.append(tool_result_message(
                    block.id, "[模型请求压缩上下文，本轮结束后将生成摘要。]"))
                compact_requested = True
                continue

            blocked = trigger_hooks("PreToolUse", block)
            if blocked:
                results.append(tool_result_message(block.id, blocked))
                continue

            if should_run_background(block.name, block.input):
                try:
                    bg_id = start_background_task(block, handlers)
                    output = (f"[Background task {bg_id} started] "
                              "Result will arrive as a task_notification.")
                except Exception as exc:
                    output = (f"Error: Failed to start background task: "
                              f"{type(exc).__name__}: {exc}")
                results.append(tool_result_message(block.id, output))
                continue

            handler = handlers.get(block.name)
            output = call_tool_handler(handler, block.input, block.name)
            trigger_hooks("PostToolUse", block, output)
            print(str(output)[:300])

            if block.name == "todo_write":
                rounds_since_todo = 0
            else:
                rounds_since_todo += 1

            results.append(tool_result_message(block.id, output))

        messages.extend(results)
        append_background_notifications(messages)
        if compact_requested:
            messages[:] = compact_history(messages, active_request)


def print_turn_assistants(messages: list, turn_start: int):
    for msg in messages[turn_start:]:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            terminal_print(content)


def async_event_loop(history: list, context: dict, session_state: dict):
    while True:
        time.sleep(1)
        with agent_lock:
            with cron_lock:
                fired = list(cron_queue)
            inbox = consume_lead_inbox(route_protocol=True)
            if not fired and not inbox and not has_pending_background():
                continue
            turn_start = len(history)
            scheduled_requests = []
            for job in fired:
                scheduled_requests.append(f"Run scheduled task: {job.prompt}")
                terminal_print(
                    f"  \033[35m[cron auto] {job.prompt[:60]}\033[0m")
            if inbox:
                history.append({"role": "user",
                                "content": format_team_events(inbox)})
                terminal_print(
                    f"  \033[33m[team auto] {len(inbox)} events\033[0m")
            active_request = (
                "\n".join(scheduled_requests)
                if scheduled_requests
                else session_state["active_user_request"]
            )
            agent_loop(history, context, active_request)
            context.update(update_context(context, history))
            print_turn_assistants(history, turn_start)