"""
v0.9.2: visa-mcp CLI (validate subcommands)

Usage:
  visa-mcp validate instrument <path>
  visa-mcp validate system <path>
  visa-mcp validate plan <path>
  visa-mcp validate benchmark <path>
  visa-mcp validate registry <path>
  visa-mcp validate schemas

各 subcommand は --json で機械可読出力を返す (CI / 自動化向け)。
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _fmt_human(rep: dict[str, Any]) -> str:
    lines = []
    icon = {"ok": "[OK]", "warning": "[WARN]", "error": "[ERR]"}.get(
        rep.get("status", ""), "[?]")
    lines.append(f"{icon} {rep.get('file', '?')}")
    if rep.get("schema"):
        lines.append(f"  schema: {rep['schema']}")
    for e in rep.get("errors") or []:
        lines.append(
            f"  ERROR  {e.get('error_class', 'error')}: {e.get('message', '')}"
        )
    for w in rep.get("warnings") or []:
        lines.append(
            f"  WARN   {w.get('warning_class', 'warning')}: {w.get('message', '')}"
        )
    return "\n".join(lines)


def _emit(reports: list[dict[str, Any]], as_json: bool) -> int:
    if as_json:
        print(json.dumps(
            {"reports": reports}, ensure_ascii=False, indent=2, default=str,
        ))
    else:
        for r in reports:
            print(_fmt_human(r))
    # 終了コード: error 1件でもあれば 1、warning のみは 0
    for r in reports:
        if r.get("status") == "error":
            return 1
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from visa_mcp import registry as reg

    target = args.target
    path = Path(args.path) if args.path else None

    if target == "instrument":
        rep = reg.validate_instrument_file(path).to_dict()
        return _emit([rep], args.json)
    if target == "system":
        rep = reg.validate_system_config_file(path).to_dict()
        return _emit([rep], args.json)
    if target == "plan":
        rep = reg.validate_plan_file(path).to_dict()
        return _emit([rep], args.json)
    if target == "benchmark":
        rep = reg.validate_benchmark_task_file(path).to_dict()
        return _emit([rep], args.json)
    if target == "registry":
        reps = [r.to_dict() for r in reg.validate_registry(path)]
        return _emit(reps, args.json)
    if target == "extension":
        # v1.2: extension manifest (definition pack) validation
        from visa_mcp.extension import validate_extension_file
        rep = validate_extension_file(path).to_dict()
        return _emit([rep], args.json)
    if target == "schemas":
        # schemas/*.schema.json がすべて pretty-printed + preview metadata を
        # 持っているか確認
        from visa_mcp.registry import ValidationReport
        schemas_dir = (Path(args.path) if args.path
                       else Path(__file__).parent.parent.parent / "schemas")
        reps: list[dict[str, Any]] = []
        for p in sorted(schemas_dir.glob("*.schema.json")):
            rep = ValidationReport(file=str(p), schema=p.name)
            try:
                text = p.read_text(encoding="utf-8")
                if "\r" in text:
                    rep.warnings.append({
                        "warning_class": "schema_has_cr",
                        "message": "CR characters found (expect LF-only)",
                    })
                if "\n" not in text:
                    rep.warnings.append({
                        "warning_class": "schema_single_line",
                        "message": (
                            "schema が 1 行に潰れています。pretty-print されて "
                            "いるか確認してください"
                        ),
                    })
                data = json.loads(text)
                if data.get("x-visa-mcp-status") not in (
                    "preview", "stable",
                ):
                    rep.warnings.append({
                        "warning_class": "missing_preview_metadata",
                        "message": (
                            "x-visa-mcp-status (preview/stable) が無い"
                        ),
                    })
            except Exception as e:
                rep.errors.append({
                    "error_class": "schema_invalid",
                    "message": str(e),
                })
                rep.status = "error"
            if rep.errors:
                rep.status = "error"
            elif rep.warnings:
                rep.status = "warning"
            reps.append(rep.to_dict())
        return _emit(reps, args.json)

    print(f"unknown target: {target}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visa-mcp",
        description="visa-mcp utility CLI (validate / lint)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    val = sub.add_parser("validate",
                          help="validate instrument / DSL plan / benchmark task / registry")
    val.add_argument(
        "target",
        choices=["instrument", "system", "plan", "benchmark", "registry",
                 "schemas", "extension"],
        help="検証対象",
    )
    val.add_argument(
        "path", nargs="?",
        help="ファイル / ディレクトリ path (schemas 時は省略可)",
    )
    val.add_argument(
        "--json", action="store_true", help="JSON 出力 (CI 向け)",
    )
    val.set_defaults(func=cmd_validate)

    serve = sub.add_parser("serve", help="MCP server を起動 (default)")
    serve.set_defaults(func=cmd_serve)

    return parser


def cmd_serve(args: argparse.Namespace) -> int:
    from visa_mcp.server import main as server_main
    server_main()
    return 0


def main() -> int:
    # 互換性: 引数なしで visa-mcp と呼ばれた場合は serve として扱う
    if len(sys.argv) == 1:
        from visa_mcp.server import main as server_main
        server_main()
        return 0
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
