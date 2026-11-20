"""协作协议状态：计划审批、关闭请求等。"""

import random
import threading
import time
from dataclasses import dataclass, field

from team.bus import BUS

active_teammates: dict[str, str] = {}
plan_gates: dict[str, str] = {}
plan_request_ids: dict[str, str] = {}
team_lock = threading.RLock()


@dataclass
class ProtocolState:
    request_id: str
    type: str
    sender: str
    target: str
    status: str
    payload: str
    work_version: int | None = None
    task_id: str | None = None
    created_at: float = field(default_factory=time.time)


pending_requests: dict[str, ProtocolState] = {}


def new_request_id() -> str:
    while True:
        request_id = f"req_{random.randint(0, 999999):06d}"
        if request_id not in pending_requests:
            return request_id


def match_response(response_type: str, request_id: str, approve: bool,
                   from_agent: str, to_agent: str) -> bool:
    with team_lock:
        state = pending_requests.get(request_id)
        if not state:
            print(f"  \033[31m[协议] 未知 request_id：{request_id}\033[0m")
            return False
        expected = {
            "shutdown": "shutdown_response",
            "plan_approval": "plan_approval_response",
        }[state.type]
        if response_type != expected:
            print(f"  \033[31m[协议] 期望 {expected}，"
                  f"got {response_type}\033[0m")
            return False
        if from_agent != state.target or to_agent != state.sender:
            print(f"  \033[31m[协议] {request_id} 回复方不匹配\033[0m")
            return False
        if state.status != "pending":
            return False
        state.status = "approved" if approve else "rejected"
    icon = "approved" if approve else "rejected"
    color = "32" if approve else "31"
    print(f"  \033[{color}m[protocol] {state.type} {icon} "
          f"({request_id}: {state.status})\033[0m")
    return True


def consume_lead_inbox(route_protocol=True) -> list[dict]:
    msgs = BUS.read_inbox("lead")
    if route_protocol:
        for msg in msgs:
            meta = msg.get("metadata", {})
            req_id = meta.get("request_id", "")
            msg_type = msg.get("type", "")
            if req_id and msg_type.endswith("_response"):
                match_response(msg_type, req_id, meta.get("approve", False),
                               msg.get("from", ""), msg.get("to", ""))
    return msgs


def format_team_events(msgs: list[dict]) -> str:
    lines = []
    for msg in msgs:
        request_id = msg.get("metadata", {}).get("request_id")
        suffix = f" request_id={request_id}" if request_id else ""
        lines.append(
            f"[{msg['type']}{suffix}] {msg['from']}: {msg['content']}"
        )
    return "[Team events]\n" + "\n".join(lines)