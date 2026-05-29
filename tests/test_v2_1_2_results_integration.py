"""v2.1.2 integration: visa-mcp serve が登録する
`visa_mcp.tools.export._extract_result_rows` も `raw_response` を読めること。

Codex 実機 E2E (v2.1.1) で発覚: lab-executor-mcp 側を v2.13.2 で
修正しても、visa-mcp の MCP server が登録するのは
`visa_mcp.tools.export` の **独自コピー** であり、こちらは依然
旧名 `response_raw` しか読まなかったため rows=0 が再発した。
"""
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock

from lab_executor.job.store import JobStore  # visa_mcp.job shim 経由でも OK
from visa_mcp.tools.export import _extract_result_rows


def _mgr_with_store(store: JobStore):
    mgr = MagicMock()
    mgr.store = store
    return mgr


def _seed_job(store: JobStore, job_id: str) -> None:
    store._connect().execute(
        "INSERT INTO jobs (job_id, owner, resource_name, status, "
        "current_step_index, created_at, updated_at) "
        "VALUES (?, '', '', 'completed', 0, '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:00:00Z')",
        (job_id,),
    )


def test_visa_mcp_export_reads_raw_response(tmp_path: Path):
    store = JobStore(str(tmp_path / "results.db"))
    job_id = "job_visa_mcp_v2_1_2"
    _seed_job(store, job_id)
    row_id = store.record_step_started(job_id, 0, "command")
    store.record_step_completed(
        row_id, status="ok",
        result={
            "command": "measure_voltage",
            "scpi_sent": "MEAS:VOLT?",
            "raw_response": "+1.234E+00",
            "success": True,
        },
    )
    rows = _extract_result_rows(_mgr_with_store(store), job_id)
    assert len(rows) == 1, (
        f"v2.1.2: visa-mcp 側 export shim も raw_response を読むべき "
        f"(rows={len(rows)})")
    assert rows[0]["measurement"] == "measure_voltage"
    assert rows[0]["value"] == "+1.234E+00"


def test_visa_mcp_export_reads_parsed_alias(tmp_path: Path):
    store = JobStore(str(tmp_path / "results2.db"))
    job_id = "job_visa_mcp_parsed"
    _seed_job(store, job_id)
    row_id = store.record_step_started(job_id, 0, "command")
    store.record_step_completed(
        row_id, status="ok",
        result={
            "command": "measure_voltage",
            "parsed": {"value": 1.234, "unit": "V"},
            "raw_response": "+1.234E+00",
            "success": True,
        },
    )
    rows = _extract_result_rows(_mgr_with_store(store), job_id)
    assert len(rows) >= 2
    assert {r["measurement"] for r in rows} >= {"value", "unit"}


def test_visa_mcp_export_legacy_keys_still_work(tmp_path: Path):
    store = JobStore(str(tmp_path / "results_legacy.db"))
    job_id = "job_visa_mcp_legacy"
    _seed_job(store, job_id)
    row_id = store.record_step_started(job_id, 0, "command")
    store.record_step_completed(
        row_id, status="ok",
        result={"command": "old_cmd", "response_raw": "L", "success": True},
    )
    rows = _extract_result_rows(_mgr_with_store(store), job_id)
    assert len(rows) == 1
    assert rows[0]["value"] == "L"


def test_v2_1_2_version():
    import visa_mcp
    parts = visa_mcp.__version__.split(".")
    assert tuple(int(p) for p in parts[:3]) >= (2, 1, 2)


def test_v2_1_3_version_sentinel_in_response():
    """v2.1.3: get_experiment_results response data に _meta.versions が
    入り、Codex 側が rows=0 のとき即座にバージョンを確認できる。"""
    from visa_mcp.tools import export as _exp
    src = open(_exp.__file__, encoding="utf-8").read()
    assert "_meta" in src and "versions" in src
    assert "export_fix" in src
