"""Pure decision policies; trusted server context must supply every input.

This is not authentication, a database write endpoint, or a live agent.
JEV = Judgment, Evidence, Value (project working definition).
"""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Status(str, Enum):
    PROCEED = "proceed"
    CLARIFY = "request_clarification"
    APPROVAL = "require_approval"
    BLOCK = "block"
    STOP = "stop"


@dataclass(frozen=True)
class Decision:
    status: Status
    reason: str
    policy_version: str = "pilot-1.0"


@dataclass(frozen=True)
class Context:
    authorized: bool
    action: str
    evidence_ids: tuple[str, ...]
    snapshot_version: str
    current_version: str
    missing_required: bool = False
    kill_switch: bool = False
    elapsed_seconds: int = 0
    steps_used: int = 0
    spent_idr: Decimal = Decimal("0")
    next_cost_upper_idr: Decimal = Decimal("0")
    # Approval is verified by the server against the action AND snapshot.
    approval_valid_for_snapshot: bool = False
    mode: str = "shadow"


@dataclass(frozen=True)
class Policy:
    max_steps: int = 4
    timeout_seconds: int = 60
    max_cost_idr: Decimal = Decimal("5000")

    def __post_init__(self):
        if self.max_steps <= 0 or self.timeout_seconds <= 0:
            raise ValueError("positive execution limits required")
        if not self.max_cost_idr.is_finite() or self.max_cost_idr <= 0:
            raise ValueError("positive finite budget required")


def decide(context: Context, policy: Policy = Policy()) -> Decision:
    """Fail closed. No numeric confidence supplied by an LLM is trusted."""
    if not context.authorized:
        return Decision(Status.BLOCK, "access_denied")
    if context.kill_switch:
        return Decision(Status.STOP, "agent_disabled")
    if context.mode not in {"shadow", "reviewed"}:
        return Decision(Status.BLOCK, "unknown_mode")
    if context.action not in {"read_gap", "draft_intervention", "publish_intervention"}:
        return Decision(Status.BLOCK, "action_not_allowed")
    costs = (context.spent_idr, context.next_cost_upper_idr)
    if any(not value.is_finite() or value < 0 for value in costs):
        return Decision(Status.BLOCK, "invalid_cost")
    if context.elapsed_seconds < 0 or context.steps_used < 0:
        return Decision(Status.BLOCK, "invalid_execution_state")
    if (context.elapsed_seconds >= policy.timeout_seconds
            or context.steps_used >= policy.max_steps
            or sum(costs) > policy.max_cost_idr):
        return Decision(Status.STOP, "execution_limit")
    if not context.snapshot_version or context.snapshot_version != context.current_version:
        return Decision(Status.CLARIFY, "stale_or_missing_snapshot")
    if context.missing_required or not context.evidence_ids:
        return Decision(Status.CLARIFY, "insufficient_evidence")
    if context.action == "publish_intervention":
        if context.mode == "shadow":
            return Decision(Status.BLOCK, "shadow_mode_no_publish")
        if not context.approval_valid_for_snapshot:
            return Decision(Status.APPROVAL, "lecturer_review_required")
    return Decision(Status.PROCEED, "policy_satisfied")
