"""v0.7.0: Monitor MCP ツール (3 個)

- start_monitor: 定期測定 Job を起動
- stop_monitor:  既存 monitor を cancel (cancel_job alias)
- get_monitor_data: monitor_data テーブルから時系列データ取得
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
    async def start_monitor(
        instrument: str,
        command: str,
        interval_s: float = 5.0,
        duration_s: float = 600.0,
        stop_condition: str = "",
        value_path: str = "",
        args: dict | None = None,
        owner: str = "",
        queue_policy: str = "queue",
    ) -> dict:
        """機器を定期測定する Monitor Job を起動 (v0.7.0)

        instrument: VISA resource 名 / alias
        command: query 系 command 名 (polling_safe=True 推奨)
        interval_s: poll 間隔 (>=1.0)
        duration_s: 全体制限 (<=86400=24h)
        stop_condition: 条件式 ("value > 80" 等)。空なら duration まで継続
        value_path: parsed response の数値フィールド名 (任意)
        args: command への引数

        測定値は monitor_data テーブルに保存され、get_monitor_data で取得可能。
        cancel_job(job_id) で停止可能。
        """
        if queue_policy not in ("queue", "reject_if_busy"):
            return make_envelope(
                "error",
                errors=[make_error(
                    "validation",
                    f"queue_policy: {queue_policy}", recoverable=False,
                )],
            )
        try:
            rec = await job_mgr.start_monitor_job(
                instrument=instrument,
                command_name=command,
                interval_s=interval_s,
                duration_s=duration_s,
                stop_condition_expr=(stop_condition or None),
                value_path=(value_path or None),
                args=args or {},
                owner=owner,
                queue_policy=queue_policy,
            )
        except Exception as e:
            logger.exception("start_monitor 失敗")
            return make_envelope(
                "error",
                errors=[make_error("internal", str(e), recoverable=False)],
            )
        data = {
            "job_id": rec.job_id,
            "monitor_id": rec.job_id,    # monitor_data の monitor_id = job_id
            "status": rec.status.value,
            "instrument": instrument,
            "command": command,
            "created_at": rec.created_at,
        }
        try:
            sch = await job_mgr.scheduler.get_scheduling_info(rec.job_id)
            sch["queue_policy"] = queue_policy
            data["scheduling"] = sch
        except Exception:
            pass
        return make_envelope(
            "ok" if rec.status != JobStatus.FAILED else "error",
            data=data,
            errors=([make_error(
                rec.error_class or "validation",
                rec.last_step_summary or "failed",
                recoverable=False,
            )] if rec.status == JobStatus.FAILED else None),
            job_id=rec.job_id,
        )

    @mcp.tool()
    async def stop_monitor(
        monitor_id: str,
        timeout_s: float = 10.0,
    ) -> dict:
        """Monitor Job を停止 (cancel_job のエイリアス、after_current_step mode)"""
        try:
            rec = await job_mgr.cancel(
                monitor_id, CancelMode.AFTER_CURRENT_STEP, timeout_s=timeout_s,
            )
        except Exception as e:
            return make_envelope(
                "error",
                errors=[make_error("internal", str(e))],
            )
        return make_envelope(
            "ok",
            data={
                "monitor_id": rec.job_id,
                "status": rec.status.value,
                "is_terminal": is_terminal(rec.status),
                "samples_recorded": (rec.result or {}).get("samples_recorded"),
            },
            job_id=rec.job_id,
        )

    @mcp.tool()
    async def get_monitor_data(
        monitor_id: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        """Monitor Job の時系列測定データを取得 (新しい順ではなく時系列順)

        get_job_result は monitor_data を含めないため、大量データはこちらで取る。
        """
        try:
            total = job_mgr.store.count_monitor_data(monitor_id)
            data = job_mgr.store.list_monitor_data(monitor_id, limit=limit, offset=offset)
        except Exception as e:
            return make_envelope(
                "error",
                errors=[make_error("internal", str(e))],
            )
        return make_envelope("ok", data={
            "monitor_id": monitor_id,
            "total_samples": total,
            "returned": len(data),
            "offset": offset,
            "data": data,
        })
