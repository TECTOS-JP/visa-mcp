"""
Job Manager + Executor (v0.5.0-rc2)

- JobManager: recipe を非同期 Job として登録・追跡・キャンセル
- バックグラウンドは asyncio.create_task で実行
- 状態は SQLite (JobStore) に同期
- cancel_mode は immediate / after_current_step / safe_shutdown の 3 種類
- recipe Step 単位で cancel チェック (各 step 開始前に確認)
- WaitStep 実行中は短いインターバルで cancel チェックして即時停止可能
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from typing import Any

from visa_mcp.experiment_ir import CommandStep, Plan, WaitStep
from visa_mcp.job.state_machine import (
    CancelMode,
    JobStatus,
    is_terminal,
)
from visa_mcp.job.store import JobStore, JobRecord
from visa_mcp.recipe_executor import (
    _execute_command_step,
    _execute_wait_step,
    recipe_to_plan,
)
from visa_mcp.session_manager import SessionManager
from visa_mcp.visa_manager import VisaManager

logger = logging.getLogger(__name__)


# wait step を細かいスライスに分割して cancel に即応するためのインターバル
_WAIT_SLICE_S = 0.2


class JobNotFoundError(Exception):
    pass


class JobAlreadyTerminalError(Exception):
    pass


class _JobRuntime:
    """asyncio.Task と cancel 要求フラグの組"""

    def __init__(self, task: asyncio.Task) -> None:
        self.task = task
        self.cancel_mode: CancelMode | None = None  # 設定されたら cancel 要求中


class JobManager:
    """
    バックグラウンド Job の管理。

    使い方:
        manager = JobManager(visa, session_mgr, store)
        job_id = await manager.start_recipe_job("GPIB0::1::INSTR", "safe_output_on", {"target_v": 5})
        await manager.cancel(job_id, CancelMode.SAFE_SHUTDOWN)
    """

    def __init__(
        self,
        visa: VisaManager,
        session_mgr: SessionManager,
        store: JobStore | None = None,
    ) -> None:
        self._visa = visa
        self._sessions = session_mgr
        self._store = store or JobStore()
        self._runtimes: dict[str, _JobRuntime] = {}
        # 起動時に running/waiting を interrupted に遷移
        self._store.mark_interrupted_on_startup()

    @property
    def store(self) -> JobStore:
        return self._store

    # ---------- public API ----------

    async def start_recipe_job(
        self,
        resource_name: str,
        recipe_name: str,
        parameters: dict[str, Any] | None,
        *,
        owner: str = "",
        override_safety: bool = False,
        override_reason: str = "",
    ) -> JobRecord:
        """
        recipe を Job として登録し、即座に bg 実行を開始。返り値は登録直後の JobRecord (queued)。

        起動失敗 (定義なし / 必須パラメータ欠落) は SQLite 上で failed として記録した上で返す。
        """
        parameters = parameters or {}
        session = self._sessions.get_session(resource_name)
        if session is None or session.definition is None:
            return self._record_immediate_failure(
                resource_name, recipe_name, parameters,
                error_class="not_found",
                summary=f"{resource_name} は未識別、または YAML 定義がありません。",
            )
        recipe = session.definition.recipes.get(recipe_name)
        if recipe is None:
            return self._record_immediate_failure(
                resource_name, recipe_name, parameters,
                error_class="not_found",
                summary=f"recipe '{recipe_name}' は定義されていません",
            )
        # 必須パラメータチェック
        for p in recipe.parameters:
            if p.required and p.name not in parameters and p.default is None:
                return self._record_immediate_failure(
                    resource_name, recipe_name, parameters,
                    error_class="validation",
                    summary=f"必須パラメータ '{p.name}' が指定されていません",
                )

        # JOB 登録
        job_id = self._new_job_id()
        rec = self._store.create_job(
            job_id=job_id,
            owner=owner,
            resource_name=resource_name,
            recipe=recipe_name,
            parameters=parameters,
        )

        # バックグラウンド実行開始
        task = asyncio.create_task(
            self._run_job(
                rec,
                override_safety=override_safety,
                override_reason=override_reason,
            ),
            name=f"job-{job_id}",
        )
        self._runtimes[job_id] = _JobRuntime(task)
        return rec

    def get(self, job_id: str) -> JobRecord:
        rec = self._store.get(job_id)
        if rec is None:
            raise JobNotFoundError(f"job not found: {job_id}")
        return rec

    def list_jobs(
        self,
        status_filter: list[str] | None = None,
        limit: int = 50,
        owner: str | None = None,
    ) -> list[JobRecord]:
        return self._store.list_jobs(status_filter, limit, owner)

    async def cancel(
        self,
        job_id: str,
        cancel_mode: CancelMode = CancelMode.AFTER_CURRENT_STEP,
        timeout_s: float | None = 30.0,
    ) -> JobRecord:
        """
        Job のキャンセルを要求し、終端状態に遷移するまで待機する。

        immediate           : asyncio.Task をキャンセル (asyncio.CancelledError)
        after_current_step  : 次の step 開始前にキャンセル
        safe_shutdown       : YAML safe_shutdown を実行してからキャンセル
        """
        rec = self.get(job_id)
        if is_terminal(rec.status):
            return rec

        runtime = self._runtimes.get(job_id)
        if runtime is None:
            # ランタイムが消失 (再起動後等) → interrupted として返す
            return self._store.transition_status(
                job_id, JobStatus.INTERRUPTED,
                error_class="interrupted",
                last_step_summary="runtime missing",
            )

        runtime.cancel_mode = cancel_mode

        # cancelling 状態に遷移 (running/waiting/queued から許可されている)
        try:
            self._store.transition_status(
                job_id, JobStatus.CANCELLING,
                last_step_summary=f"cancel_mode={cancel_mode.value}",
            )
        except Exception:
            # 既に終端なら無視
            pass

        if cancel_mode is CancelMode.IMMEDIATE:
            runtime.task.cancel()

        # 終端まで待機
        try:
            await asyncio.wait_for(runtime.task, timeout=timeout_s)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        except Exception:
            pass

        return self.get(job_id)

    # ---------- internal ----------

    def _new_job_id(self) -> str:
        return f"job_{uuid.uuid4().hex[:12]}"

    def _record_immediate_failure(
        self,
        resource_name: str,
        recipe_name: str,
        parameters: dict[str, Any],
        *,
        error_class: str,
        summary: str,
    ) -> JobRecord:
        job_id = self._new_job_id()
        rec = self._store.create_job(
            job_id=job_id,
            owner="",
            resource_name=resource_name,
            recipe=recipe_name,
            parameters=parameters,
        )
        return self._store.transition_status(
            job_id, JobStatus.FAILED,
            error_class=error_class,
            last_step_summary=summary,
            result={"success": False, "error": error_class, "message": summary},
        )

    async def _run_job(
        self,
        rec: JobRecord,
        *,
        override_safety: bool,
        override_reason: str,
    ) -> None:
        """Job のバックグラウンド実行本体。"""
        job_id = rec.job_id
        runtime = self._runtimes[job_id]
        session = self._sessions.get_session(rec.resource_name)

        # session 検証 (start_recipe_job で確認済みだが double check)
        if session is None or session.definition is None:
            self._store.transition_status(
                job_id, JobStatus.FAILED,
                error_class="not_found",
                last_step_summary="session lost",
                result={"success": False, "error": "SessionNotFound"},
            )
            return

        recipe = session.definition.recipes.get(rec.recipe)
        if recipe is None:
            self._store.transition_status(
                job_id, JobStatus.FAILED,
                error_class="not_found",
                last_step_summary="recipe not found",
                result={"success": False, "error": "RecipeNotFound"},
            )
            return

        # デフォルト適用
        variables = dict(rec.parameters)
        for p in recipe.parameters:
            if p.name not in variables and p.default is not None:
                variables[p.name] = p.default

        # Recipe → IR Plan 変換
        try:
            plan: Plan = recipe_to_plan(recipe, variables)
        except Exception as e:
            self._store.transition_status(
                job_id, JobStatus.FAILED,
                error_class="validation",
                last_step_summary=f"plan build failed: {e}",
                result={"success": False, "error": "ExpressionError", "message": str(e)},
            )
            return

        # running へ
        self._store.transition_status(job_id, JobStatus.RUNNING, current_step_index=0)

        step_results: list[dict] = []
        last_terminal: JobStatus = JobStatus.COMPLETED

        try:
            for idx, step in enumerate(plan.steps):
                # cancel チェック
                if runtime.cancel_mode is not None:
                    last_terminal = await self._handle_cancel(
                        rec, session, runtime.cancel_mode, step_results,
                    )
                    return

                self._store.update_step(
                    job_id, idx,
                    last_step_summary=self._step_summary(step),
                )

                # WaitStep は専用パス (cancel に即応)
                if isinstance(step, WaitStep):
                    # waiting 状態へ
                    self._safe_transition(job_id, JobStatus.WAITING)
                    result = await self._run_wait_with_cancel_check(step, runtime)
                    self._safe_transition(job_id, JobStatus.RUNNING)
                elif isinstance(step, CommandStep):
                    result = await _execute_command_step(
                        self._visa, session, step,
                        override_safety=override_safety,
                        override_reason=override_reason,
                    )
                else:
                    result = {
                        "success": False,
                        "error": "UnsupportedStepType",
                        "step_type": getattr(step, "type", "?"),
                    }

                step_results.append({"step": idx, **result})

                if not result.get("success", False):
                    # cancel 要求による wait 中断は failed ではなく cancel 経路へ
                    if result.get("interrupted_by_cancel"):
                        last_terminal = await self._handle_cancel(
                            rec, session,
                            runtime.cancel_mode or CancelMode.AFTER_CURRENT_STEP,
                            step_results,
                        )
                        return
                    last_terminal = JobStatus.FAILED
                    err_class = result.get("error", "internal")
                    if result.get("blocked_by_safety"):
                        err_class = "safety"
                    self._store.transition_status(
                        job_id, JobStatus.FAILED,
                        current_step_index=idx,
                        error_class=err_class,
                        last_step_summary=f"step {idx} failed: {result.get('message', result.get('error', '?'))[:80]}",
                        result={
                            "success": False, "recipe": rec.recipe,
                            "steps_executed": step_results,
                            "halted_at_step": idx,
                        },
                    )
                    return

                # cancel チェック (各 step 完了後)
                if runtime.cancel_mode is not None:
                    # after_current_step ならここで停止可能
                    if runtime.cancel_mode in (
                        CancelMode.AFTER_CURRENT_STEP, CancelMode.SAFE_SHUTDOWN,
                    ):
                        last_terminal = await self._handle_cancel(
                            rec, session, runtime.cancel_mode, step_results,
                        )
                        return

            # 全 step 成功
            self._store.transition_status(
                job_id, JobStatus.COMPLETED,
                current_step_index=len(plan.steps) - 1,
                last_step_summary="completed",
                result={
                    "success": True, "recipe": rec.recipe,
                    "steps_executed": step_results,
                    "step_count": len(step_results),
                },
            )

        except asyncio.CancelledError:
            # immediate cancel
            self._store.transition_status(
                job_id, JobStatus.CANCELLED,
                error_class="cancelled",
                last_step_summary="cancelled (immediate)",
                result={
                    "success": False, "recipe": rec.recipe,
                    "steps_executed": step_results,
                    "cancelled": True, "cancel_mode": "immediate",
                },
            )
        except Exception as e:
            logger.exception("Job %s で予期しないエラー", job_id)
            self._store.transition_status(
                job_id, JobStatus.FAILED,
                error_class="internal",
                last_step_summary=f"unexpected: {e}",
                result={"success": False, "error": "InternalError", "message": str(e)},
            )

    async def _run_wait_with_cancel_check(
        self,
        step: WaitStep,
        runtime: _JobRuntime,
    ) -> dict:
        """wait を _WAIT_SLICE_S 刻みで sleep し、間に cancel チェックを挟む。"""
        remaining = float(step.seconds)
        while remaining > 0:
            if runtime.cancel_mode is CancelMode.IMMEDIATE:
                # asyncio.Task.cancel() で別途処理されるが、念のため
                raise asyncio.CancelledError("immediate cancel during wait")
            if runtime.cancel_mode in (
                CancelMode.AFTER_CURRENT_STEP, CancelMode.SAFE_SHUTDOWN,
            ):
                # wait は「現在 step」として扱い、即時中断する (ユーザー観点では妥当)
                return {
                    "step_type": "wait",
                    "seconds": float(step.seconds) - remaining,
                    "interrupted_by_cancel": True,
                    "success": False,
                    "error": "cancelled",
                    "message": "wait interrupted by cancel request",
                }
            chunk = min(remaining, _WAIT_SLICE_S)
            await asyncio.sleep(chunk)
            remaining -= chunk
        return {
            "step_type": "wait",
            "seconds": step.seconds,
            "success": True,
        }

    async def _handle_cancel(
        self,
        rec: JobRecord,
        session,
        mode: CancelMode,
        step_results: list[dict],
    ) -> JobStatus:
        """cancel 要求を実際に実行 (safe_shutdown なら shutdown シーケンス)"""
        job_id = rec.job_id

        if mode is CancelMode.SAFE_SHUTDOWN:
            # YAML の safe_shutdown (instrument_def の同名フィールドが将来追加される予定)
            # v0.5.0-rc2 では汎用的に "set_output OFF + set_voltage 0" を試みる
            shutdown_summary = await self._best_effort_safe_shutdown(session)
            step_results.append({
                "step": -1, "step_type": "safe_shutdown",
                "summary": shutdown_summary, "success": True,
            })

        # CANCELLED への遷移は CANCELLING 経由が必要。途中で cancel 検出された場合は
        # まず CANCELLING に遷移してから CANCELLED へ。
        current = self._store.get(job_id)
        if current and current.status not in (JobStatus.CANCELLING, JobStatus.CANCELLED):
            self._safe_transition(job_id, JobStatus.CANCELLING)

        self._store.transition_status(
            job_id, JobStatus.CANCELLED,
            error_class="cancelled",
            last_step_summary=f"cancelled ({mode.value})",
            result={
                "success": False, "recipe": rec.recipe,
                "steps_executed": step_results,
                "cancelled": True, "cancel_mode": mode.value,
            },
        )
        return JobStatus.CANCELLED

    async def _best_effort_safe_shutdown(self, session) -> str:
        """汎用的な安全停止: set_output(OFF) と set_voltage(0) を試みる。"""
        attempts: list[str] = []
        if session is None or session.definition is None:
            return "no session"
        for cmd_name, args in [
            ("set_output", {"state": "OFF"}),
            ("set_voltage", {"voltage": 0}),
        ]:
            cmd_def = session.definition.commands.get(cmd_name)
            if cmd_def is None:
                continue
            try:
                step = CommandStep(command=cmd_name, args=args)
                r = await _execute_command_step(
                    self._visa, session, step,
                    override_safety=True,
                    override_reason="safe_shutdown by cancel",
                )
                attempts.append(f"{cmd_name}:{'ok' if r.get('success') else 'fail'}")
            except Exception as e:
                attempts.append(f"{cmd_name}:err({type(e).__name__})")
        return ",".join(attempts) if attempts else "no shutdown commands available"

    def _safe_transition(self, job_id: str, to: JobStatus) -> None:
        """遷移ルール違反は黙って無視 (cancelling 中の状態変更等)"""
        try:
            self._store.transition_status(job_id, to)
        except Exception:
            pass

    @staticmethod
    def _step_summary(step) -> str:
        if isinstance(step, WaitStep):
            return f"wait {step.seconds}s"
        if isinstance(step, CommandStep):
            return f"command {step.command}"
        return f"step type={getattr(step, 'type', '?')}"
