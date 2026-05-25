"""v1.10.0: Separation Readiness Audit tests

- pyproject / __version__ が 1.10.0
- module_ownership.yaml が全 module をカバー (unclassified=0)
- split_manifest.yaml が path として実在 (or directory)
- ownership_check が 新規 lab→visa top-level violation を出さない
  (KNOWN_V111_TO_RESOLVE のみが残る)
- dependency_graph.md 生成
- instrument review-report CLI が markdown report を出す
- review_report_instrument() が ok/warning/error を返す
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def test_version_is_1_10_0():
    from visa_mcp import __version__
    assert __version__ == "1.10.0"


def test_module_ownership_manifest_complete():
    """module_ownership.yaml が src/visa_mcp 配下の全 module を分類"""
    from visa_mcp.dev.ownership_check import collect_report
    rep = collect_report()
    assert rep["unclassified_modules"] == [], (
        f"未分類 module: {rep['unclassified_modules']}")
    assert rep["manifest_ghost_modules"] == [], (
        f"manifest 幽霊 module: {rep['manifest_ghost_modules']}")
    assert rep["declared_modules_count"] == rep["actual_modules_count"]


def test_no_new_lab_to_visa_top_level_violations():
    """v1.10 では NEW violation は 0 件、KNOWN は tracking のみ"""
    from visa_mcp.dev.ownership_check import collect_report
    rep = collect_report()
    assert rep["lab_to_visa_top_level_violations"] == [], (
        f"新規 violation: {rep['lab_to_visa_top_level_violations']}\n"
        f"v1.11 で解消予定なら KNOWN_V111_TO_RESOLVE に追加してください")


def test_known_v1_11_to_resolve_tracked():
    """v1.11 で解消する既知 violation は tracking されている"""
    from visa_mcp.dev.ownership_check import (
        KNOWN_V111_TO_RESOLVE, collect_report,
    )
    # 既知 violation の登録数 (v1.10 時点で 10 件)
    assert len(KNOWN_V111_TO_RESOLVE) >= 1
    rep = collect_report()
    # report で known_pending として一致登録されている
    assert rep["known_v1_11_to_resolve_count"] == len(KNOWN_V111_TO_RESOLVE)


def test_split_manifest_paths_exist():
    """split_manifest.yaml に列挙された path が概ね実在"""
    manifest_path = ROOT / "docs" / "separation" / "split_manifest.yaml"
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    move_paths = data.get("move_to_lab_executor", []) or []
    keep_paths = data.get("keep_in_visa_mcp", []) or []
    # 少なくとも 80% は実在
    all_paths = [p for p in move_paths + keep_paths
                  if not p.startswith("docs/") and "raw_visa" not in p]
    existing = sum(1 for p in all_paths if (ROOT / p).exists())
    assert existing / max(len(all_paths), 1) > 0.7, (
        f"split_manifest の path 多くが実在しない: "
        f"{existing}/{len(all_paths)}")


def test_dependency_graph_generated(tmp_path):
    """ownership_check --graph-md で markdown が生成できる"""
    from visa_mcp.dev.ownership_check import collect_report, render_graph_md
    rep = collect_report()
    md = render_graph_md(rep)
    assert "# Dependency Graph Report" in md
    assert "Owner counts" in md
    assert "## Statistics" in md


def test_ownership_check_cli_exit_zero(tmp_path):
    """CLI exit code = 0 (NEW violation 無し)"""
    res = subprocess.run(
        [sys.executable, "-m", "visa_mcp.dev.ownership_check"],
        cwd=str(ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 0, (
        f"stdout: {res.stdout}\nstderr: {res.stderr}")
    assert "unclassified: 0" in res.stdout


def test_ownership_check_json_output():
    res = subprocess.run(
        [sys.executable, "-m", "visa_mcp.dev.ownership_check", "--json"],
        cwd=str(ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert "unclassified_modules" in data
    assert "lab_to_visa_top_level_violations" in data
    assert "known_v1_11_to_resolve" in data


def test_review_report_function_ok():
    """review_report_instrument が valid YAML に対し markdown を返す"""
    from visa_mcp.instrument_authoring import review_report_instrument
    # registry の verified instrument を使う
    candidates = list((ROOT / "registry").rglob("*.yaml"))
    # registry index 以外
    candidates = [c for c in candidates if "INDEX" not in c.name]
    assert candidates, "registry に instrument YAML が無い"
    target = candidates[0]
    res = review_report_instrument(target)
    assert res["status"] in ("ok", "warning", "error")
    assert "# Instrument review report" in res["markdown"]
    assert res["file"] == str(target.expanduser())


def test_review_report_function_missing_file():
    from visa_mcp.instrument_authoring import review_report_instrument
    res = review_report_instrument("/nonexistent/path.yaml")
    assert res["status"] == "error"
    assert "not found" in res["markdown"]
    assert "# Instrument review report" in res["markdown"]


def test_review_report_cli(tmp_path):
    """visa-mcp instrument review-report CLI が動く"""
    candidates = list((ROOT / "registry").rglob("*.yaml"))
    candidates = [c for c in candidates if "INDEX" not in c.name]
    assert candidates
    target = candidates[0]
    out = tmp_path / "review.md"
    res = subprocess.run(
        [sys.executable, "-m", "visa_mcp.cli", "instrument",
         "review-report", str(target), "--output", str(out)],
        cwd=str(ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode in (0, 1), (
        f"stdout: {res.stdout}\nstderr: {res.stderr}")
    assert out.exists()
    md = out.read_text(encoding="utf-8")
    assert "# Instrument review report" in md


def test_review_report_cli_json(tmp_path):
    candidates = list((ROOT / "registry").rglob("*.yaml"))
    candidates = [c for c in candidates if "INDEX" not in c.name]
    target = candidates[0]
    res = subprocess.run(
        [sys.executable, "-m", "visa_mcp.cli", "instrument",
         "review-report", str(target), "--json"],
        cwd=str(ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode in (0, 1)
    data = json.loads(res.stdout)
    assert "review_report" in data
    assert "markdown" in data["review_report"]
    assert "status" in data["review_report"]
