"""Lead 的团队管理工具。"""

from team.bus import BUS
from team.protocol import (
    ProtocolState,
    active_teammates,
    new_request_id,
    pending_requests,
    plan_gates,
    plan_request_ids,
    team_lock,
)
from team.teammate import current_work_identity, spawn_teammate_thread


def run_request_shutdown(teammate: str) -> str:
    if teammate not in active_teammates:
        return f"Teammate '{teammate}' is not active"
    with team_lock:
        req_id = new_request_id()
        pending_requests[req_id] = ProtocolState(
            request_id=req_id, type="shutdown",
            sender="lead", target=teammate,
            status="pending", payload="")
    BUS.send("lead", teammate, "Finish the current step and shut down.",
             "shutdown_request",
             {"request_id": req_id})
    print(f"  \033[35m[protocol] shutdown_request -> {teammate} "
          f"({req_id})\033[0m")
    return f"Shutdown requested from {teammate} ({req_id})"


def run_request_plan(teammate: str, task: str) -> str:
    if teammate not in active_teammates:
        return f"Teammate '{teammate}' is not active"
    with team_lock:
        plan_gates[teammate] = "required"
    BUS.send("lead", teammate, task, "plan_request")
    return f"Plan requested from {teammate}"


def run_review_plan(request_id: str, approve: bool,
                    feedback: str = "") -> str:
    state = pending_requests.get(request_id)
    if not state:
        return f"Request {request_id} not found"
    work_version, task_id = current_work_identity(state.sender)
    with team_lock:
        state = pending_requests.get(request_id)
        if not state:
            return f"Request {request_id} not found"
        if state.type != "plan_approval":
            return f"Request {request_id} is not a plan"
        if state.status != "pending":
            return f"Request {request_id} already {state.status}"
        if state.work_version != work_version or state.task_id != task_id:
            return f"Request {request_id} belongs to an earlier assignment"
        if plan_request_ids.get(state.sender) != request_id:
            return f"Request {request_id} is not the current plan"
        state.status = "approved" if approve else "rejected"
    content = feedback or ("Plan approved." if approve
                           else "Revise the plan and submit it again.")
    BUS.send("lead", state.sender, content,
             "plan_approval_response",
             {"request_id": request_id, "approve": approve})
    icon = "approved" if approve else "rejected"
    print(f"  \033[32m[protocol] plan {icon} ({request_id})\033[0m")
    return f"Plan {state.status} ({request_id})"


def run_spawn_teammate(name: str, role: str, prompt: str,
                       task_id: str | None = None,
                       require_plan: bool = False) -> str:
    return spawn_teammate_thread(name, role, prompt, task_id, require_plan)


def run_list_teammates() -> str:
    with team_lock:
        if not active_teammates:
            return "No active teammates."
        return "\n".join(
            f"{name}: {status}"
            for name, status in sorted(active_teammates.items())
        )


def run_send_message(to: str, content: str) -> str:
    if to not in active_teammates:
        return f"Teammate '{to}' is not active"
    BUS.send("lead", to, content)
    return f"Sent to {to}"