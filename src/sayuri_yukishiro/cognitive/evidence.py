from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class ExecutionReceipt:
    id: str
    session_id: str
    step_id: str
    capability: str
    status: str
    evidence: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_receipt(
    *,
    session_id: str,
    step_id: str,
    capability: str,
    status: str,
    evidence: dict[str, Any] | None = None,
) -> ExecutionReceipt:
    return ExecutionReceipt(
        id=str(uuid4()),
        session_id=session_id,
        step_id=step_id,
        capability=capability,
        status=status,
        evidence=dict(evidence or {}),
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
