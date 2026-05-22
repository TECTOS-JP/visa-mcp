"""v0.8.1: Pydantic モデルから JSON Schema preview を生成。

出力: schemas/dsl.schema.json / schemas/instrument.schema.json /
      schemas/system_config.schema.json

各 schema には preview status を示すメタフィールドを付与:
  - "$id": preview URL
  - "x-visa-mcp-status": "preview"
  - "x-compatibility": "subject-to-change-before-v1.0"
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).parent.parent
SCHEMAS_DIR = ROOT / "schemas"
SRC = ROOT / "src"


def _ensure_path() -> None:
    p = str(SRC)
    if p not in sys.path:
        sys.path.insert(0, p)


def _add_preview_metadata(schema: dict, schema_id: str, title: str) -> dict:
    schema["$id"] = (
        f"https://tectos-jp.github.io/visa-mcp/schemas/{schema_id}.schema.preview.json"
    )
    schema["title"] = title
    schema["x-visa-mcp-status"] = "preview"
    schema["x-compatibility"] = "subject-to-change-before-v1.0"
    schema["description"] = (
        schema.get("description", "")
        + " (PREVIEW: v1.0 で正式公開予定。外部利用は VS Code 補完等の参考用途のみ。)"
    )
    return schema


def main() -> int:
    _ensure_path()
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)

    from visa_mcp.dsl.schema import ExperimentPlan
    dsl_schema = ExperimentPlan.model_json_schema()
    _add_preview_metadata(
        dsl_schema, "dsl", "Experiment DSL ExperimentPlan (v0.8 preview)",
    )
    (SCHEMAS_DIR / "dsl.schema.json").write_text(
        json.dumps(dsl_schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("generated: schemas/dsl.schema.json")

    from visa_mcp.models.instrument_def import InstrumentDefinition
    inst_schema = InstrumentDefinition.model_json_schema()
    _add_preview_metadata(
        inst_schema, "instrument", "Instrument YAML Definition (v0.8 preview)",
    )
    (SCHEMAS_DIR / "instrument.schema.json").write_text(
        json.dumps(inst_schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("generated: schemas/instrument.schema.json")

    # v0.9.2: BenchmarkTask schema を追加 (Ecosystem 準備)
    from visa_mcp.testing.benchmark_task import BenchmarkTask
    bench_schema = BenchmarkTask.model_json_schema()
    _add_preview_metadata(
        bench_schema, "benchmark_task",
        "Benchmark Task (incl. repair tasks) (v0.9.2 preview)",
    )
    (SCHEMAS_DIR / "benchmark_task.schema.json").write_text(
        json.dumps(bench_schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("generated: schemas/benchmark_task.schema.json")

    from visa_mcp.system_config import SystemConfig
    sysconf_schema = SystemConfig.model_json_schema()
    _add_preview_metadata(
        sysconf_schema, "system_config",
        "System Configuration (_system.yaml) (v0.8 preview)",
    )
    (SCHEMAS_DIR / "system_config.schema.json").write_text(
        json.dumps(sysconf_schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("generated: schemas/system_config.schema.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
