"""
v0.6.0 TargetExecution IR

group / map executor が共通で扱う「1 つの target を実行する」単位。

query_group:
  各 instrument に対し単一 CommandStep の Plan を作って TargetExecution にラップ
map_recipe:
  各 target に対し Recipe 由来 Plan + bindings を持つ TargetExecution
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from visa_mcp.experiment_ir import Plan


@dataclass
class TargetExecution:
    """1 つの target の実行単位"""
    target_id: str
    plan: Plan
    required_resources: list[str]  # canonical sorted
    bindings: dict[str, str] = field(default_factory=dict)   # logical role → alias
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FailurePolicy:
    """Group/Map Job の失敗時挙動

    mode:
      - "continue":                    失敗 target を記録し、他 target は継続
      - "stop_on_first_error":         最初の失敗で未開始 target を skipped に
      - "stop_if_failure_rate_exceeds":失敗率が閾値超過で未開始を skipped

    retry: 同一 target を全体再実行する最大回数 (target 単位リトライ、step 部分リトライではない)
    stop_if_failure_rate_exceeds_threshold: 0.0-1.0
    cancel_running_on_policy_stop:
      stop_on_first_error / stop_if_failure_rate_exceeds 時に、既に実行中の
      target に対して cancel を要求するか (True なら after_current_step 相当)
    retry_safe_shutdown_before_retry:
      retry の前に target の safe_shutdown を試行するか (v0.6.0 は予約フィールド、
      未実装)
    """
    mode: str = "continue"
    retry: int = 0
    stop_if_failure_rate_exceeds_threshold: float = 0.5
    cancel_running_on_policy_stop: bool = False
    retry_safe_shutdown_before_retry: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "FailurePolicy":
        if not d:
            return cls()
        return cls(
            mode=d.get("mode", "continue"),
            retry=int(d.get("retry", 0)),
            stop_if_failure_rate_exceeds_threshold=float(
                d.get("stop_if_failure_rate_exceeds", 0.5)
            ),
            cancel_running_on_policy_stop=bool(d.get("cancel_running_on_policy_stop", False)),
            retry_safe_shutdown_before_retry=bool(
                d.get("retry_safe_shutdown_before_retry", False)
            ),
        )

    VALID_MODES = ("continue", "stop_on_first_error", "stop_if_failure_rate_exceeds")

    def validate(self) -> None:
        if self.mode not in self.VALID_MODES:
            raise ValueError(
                f"failure_policy.mode は {self.VALID_MODES} のいずれか: {self.mode!r}"
            )
        if self.retry < 0:
            raise ValueError(f"failure_policy.retry は 0 以上: {self.retry}")
        if not (0.0 <= self.stop_if_failure_rate_exceeds_threshold <= 1.0):
            raise ValueError(
                f"stop_if_failure_rate_exceeds 閾値は 0..1: "
                f"{self.stop_if_failure_rate_exceeds_threshold}"
            )
