"""Job 系 MCP ツール (v0.5.0-rc2)

5 個の高レベル Job 操作ツール:
  - start_recipe_job
  - get_job_status
  - get_job_result
  - list_jobs
  - cancel_job

全て v0.5.0+ の標準レスポンス形式 (response_envelope) で返す。
"""
from __future__ import annotations
import logging

from fastmcp import FastMCP

from visa_mcp.job import CancelMode, JobManager
from visa_mcp.job.state_machine import JobStatus, is_terminal
from visa_mcp.response_envelope import make_envelope, make_error

logger = logging.getLogger(__name__)


def register_tools(mcp: FastMCP, job_mgr: JobManager) -> None:

    @mcp.tool()
    async def start_recipe_job(
        resource_name: str,
        recipe_name: str,
        parameters: dict = {},
        owner: str = "",
        override_safety: bool = False,
        override_reason: str = "",
    ) -> dict:
        """
        Recipe をバックグラウンド Job として登録し、即座に job_id を返す。
        LLM のツール呼び出しはブロックされない。進捗は get_job_status で確認する。

        resource_name: VISA リソース文字列
        recipe_name: YAML 定義された recipe のキー
        parameters: recipe パラメータ (例: {"target_v": 5.0})
        owner: 所有者識別子 (将来のマルチエージェント用、任意)
        override_safety: 安全制約警告を override (advisory モード時のみ有効)
        override_reason: override 理由 (override_safety=True 時必須)
        """
        try:
            rec = await job_mgr.start_recipe_job(
                resource_name, recipe_name, parameters,
                owner=owner,
                override_safety=override_safety,
                override_reason=override_reason,
            )
        except Exception as e:
            logger.exception("start_recipe_job 失敗")
            return make_envelope(
                "error",
                errors=[make_error("internal", str(e), recoverable=False)],
            )

        return make_envelope(
            "ok" if rec.status != JobStatus.FAILED else "error",
            data={
                "job_id": rec.job_id,
                "status": rec.status.value,
                "resource_name": rec.resource_name,
                "recipe": rec.recipe,
                "created_at": rec.created_at,
            },
            errors=([make_error(
                rec.error_class or "validation",
                rec.last_step_summary or "failed",
                recoverable=False,
            )] if rec.status == JobStatus.FAILED else None),
            job_id=rec.job_id,
        )

    @mcp.tool()
    async def get_job_status(job_id: str) -> dict:
        """
        Job の現在状態を取得。短いレスポンス。

        返却フィールド (data):
          status / current_step_index / last_step_summary /
          error_class / created_at / updated_at / is_terminal
        """
        try:
            rec = job_mgr.get(job_id)
        except Exception:
            return make_envelope(
                "error",
                errors=[make_error("not_found", f"job not found: {job_id}", recoverable=False)],
            )
        return make_envelope(
            "ok",
            data={
                "job_id": rec.job_id,
                "status": rec.status.value,
                "is_terminal": is_terminal(rec.status),
                "current_step_index": rec.current_step_index,
                "last_step_summary": rec.last_step_summary,
                "error_class": rec.error_class,
                "owner": rec.owner,
                "resource_name": rec.resource_name,
                "recipe": rec.recipe,
                "created_at": rec.created_at,
                "updated_at": rec.updated_at,
            },
            job_id=rec.job_id,
        )

    @mcp.tool()
    async def get_job_result(job_id: str) -> dict:
        """
        終端 Job の完全な結果を取得 (steps_executed を含む)。
        まだ実行中の場合は status が "running" として返る。
        """
        try:
            rec = job_mgr.get(job_id)
        except Exception:
            return make_envelope(
                "error",
                errors=[make_error("not_found", f"job not found: {job_id}", recoverable=False)],
            )

        if not is_terminal(rec.status):
            return make_envelope(
                "running",
                data={
                    "job_id": rec.job_id,
                    "status": rec.status.value,
                    "current_step_index": rec.current_step_index,
                    "last_step_summary": rec.last_step_summary,
                },
                job_id=rec.job_id,
            )

        status_map = {
            JobStatus.COMPLETED: "ok",
            JobStatus.FAILED: "error",
            JobStatus.CANCELLED: "error",
            JobStatus.TIMEOUT: "error",
            JobStatus.INTERRUPTED: "error",
        }
        envelope_status = status_map.get(rec.status, "error")
        return make_envelope(
            envelope_status,
            data={
                "job_id": rec.job_id,
                "status": rec.status.value,
                "resource_name": rec.resource_name,
                "recipe": rec.recipe,
                "result": rec.result or {},
                "created_at": rec.created_at,
                "updated_at": rec.updated_at,
            },
            errors=([make_error(
                rec.error_class or "internal",
                rec.last_step_summary or rec.status.value,
                recoverable=(rec.status != JobStatus.FAILED),
            )] if envelope_status == "error" else None),
            job_id=rec.job_id,
        )

    @mcp.tool()
    async def list_jobs(
        status_filter: list = None,
        owner: str = "",
        limit: int = 50,
    ) -> dict:
        """
        Job 一覧を取得 (新しい順)。

        status_filter: ["running", "completed"] など。空 None なら全件
        owner: 所有者で絞り込み (空文字列は無視)
        limit: 最大件数
        """
        sf = list(status_filter) if status_filter else None
        owner_filter = owner if owner else None
        recs = job_mgr.list_jobs(status_filter=sf, limit=limit, owner=owner_filter)
        return make_envelope(
            "ok",
            data={
                "count": len(recs),
                "jobs": [
                    {
                        "job_id": r.job_id,
                        "status": r.status.value,
                        "is_terminal": is_terminal(r.status),
                        "resource_name": r.resource_name,
                        "recipe": r.recipe,
                        "owner": r.owner,
                        "current_step_index": r.current_step_index,
                        "error_class": r.error_class,
                        "created_at": r.created_at,
                        "updated_at": r.updated_at,
                    }
                    for r in recs
                ],
            },
        )

    @mcp.tool()
    async def cancel_job(
        job_id: str,
        cancel_mode: str = "after_current_step",
        timeout_s: float = 30.0,
    ) -> dict:
        """
        Job のキャンセルを要求し、終端まで待機する。

        cancel_mode:
          - "immediate"           : asyncio.Task を直ちにキャンセル
          - "after_current_step"  : 現在の step 完了後に停止
          - "safe_shutdown"       : OUTP OFF / VOLT 0 を試みてから停止
        timeout_s: 終端遷移を待つ最大秒数
        """
        try:
            mode = CancelMode(cancel_mode)
        except ValueError:
            return make_envelope(
                "error",
                errors=[make_error(
                    "validation",
                    f"不正な cancel_mode: {cancel_mode}",
                    details={"valid": [m.value for m in CancelMode]},
                    recoverable=False,
                )],
            )
        try:
            rec = await job_mgr.cancel(job_id, mode, timeout_s=timeout_s)
        except Exception as e:
            return make_envelope(
                "error",
                errors=[make_error("internal", str(e))],
            )
        return make_envelope(
            "ok",
            data={
                "job_id": rec.job_id,
                "status": rec.status.value,
                "is_terminal": is_terminal(rec.status),
                "cancel_mode": cancel_mode,
                "last_step_summary": rec.last_step_summary,
            },
            job_id=rec.job_id,
        )
