"""v0.8.1: DSL examples 5 件を docs/dsl/examples/ に生成する。"""
from pathlib import Path
import json

BASE = Path(__file__).parent.parent / "docs" / "dsl" / "examples"


EXAMPLES = {
    "basic_voltage_set_and_measure": {
        "plan": {
            "dsl_version": "0.8",
            "name": "basic_voltage_set_and_measure",
            "description": "電源を 5V に設定し、その後測定値を取得する最小例",
            "bindings": {"psu": "psu001"},
            "steps": [
                {"type": "command", "instrument": "$psu", "command": "set_voltage",
                 "args": {"voltage": 5.0}},
                {"type": "query", "instrument": "$psu", "command": "measure_voltage"},
            ],
        },
        "expected_note": (
            "validate=True, step_count_dsl=2, has_safe_shutdown=False, has_parallel=False"
        ),
    },
    "voltage_sweep_with_wait": {
        "plan": {
            "dsl_version": "0.8",
            "name": "voltage_sweep_with_wait",
            "description": "電圧を 1.0/2.0/3.0 V に sweep し、各点で 1 秒 wait してから測定",
            "bindings": {"psu": "psu001", "dmm": "dmm001"},
            "steps": [
                {
                    "type": "sweep",
                    "parameter": "voltage",
                    "values": {"values": [1.0, 2.0, 3.0]},
                    "body": [
                        {"type": "command", "instrument": "$psu",
                         "command": "set_voltage", "args": {"voltage": "{voltage}"}},
                        {"type": "wait", "seconds": 1.0},
                        {"type": "query", "instrument": "$dmm",
                         "command": "measure_voltage"},
                    ],
                },
            ],
        },
        "expected_note": "sweep が 3 値展開で step_count_expanded ≈ 9",
    },
    "voltage_sweep_with_wait_for_stable": {
        "plan": {
            "dsl_version": "0.8",
            "name": "voltage_sweep_with_wait_for_stable",
            "description": "電圧 sweep + 温度が安定してから測定",
            "bindings": {"psu": "psu001", "dmm": "dmm001", "temp": "temp001"},
            "steps": [
                {
                    "type": "sweep",
                    "parameter": "voltage",
                    "values": {"start": 1.0, "stop": 3.0, "step": 1.0},
                    "body": [
                        {"type": "command", "instrument": "$psu",
                         "command": "set_voltage", "args": {"voltage": "{voltage}"}},
                        {"type": "wait_for_stable", "instrument": "$temp",
                         "command": "measure_temperature",
                         "tolerance": 0.2, "window_s": 30, "interval_s": 5,
                         "timeout_s": 300, "min_samples": 3,
                         "value_path": "temperature"},
                        {"type": "query", "instrument": "$dmm",
                         "command": "measure_voltage"},
                    ],
                },
            ],
        },
        "expected_note": "uses_polling=True, polling_safe_false warning が出る可能性",
    },
    "partial_failure_group_measurement": {
        "plan": {
            "dsl_version": "0.8",
            "name": "partial_failure_group_measurement",
            "description": "3 つの機器を parallel で測定 (一部失敗を許容する想定)",
            "bindings": {"dmm_a": "dmm001", "dmm_b": "dmm002", "dmm_c": "dmm003"},
            "steps": [
                {
                    "type": "parallel",
                    "concurrency": 3,
                    "branches": [
                        [{"type": "query", "instrument": "$dmm_a",
                          "command": "measure_voltage"}],
                        [{"type": "query", "instrument": "$dmm_b",
                          "command": "measure_voltage"}],
                        [{"type": "query", "instrument": "$dmm_c",
                          "command": "measure_voltage"}],
                    ],
                },
            ],
        },
        "expected_note": "has_parallel=True, parallel_group_count=1, branches 共有なし",
    },
    "safe_shutdown_explicit_targets": {
        "plan": {
            "dsl_version": "0.8",
            "name": "safe_shutdown_explicit_targets",
            "description": "psu_a を一定電圧設定後、psu_a だけを safe_shutdown",
            "bindings": {"psu_a": "psu001", "psu_b": "psu002"},
            "steps": [
                {"type": "command", "instrument": "$psu_a", "command": "set_voltage",
                 "args": {"voltage": 5.0}},
                {"type": "command", "instrument": "$psu_b", "command": "set_voltage",
                 "args": {"voltage": 3.0}},
                {"type": "safe_shutdown", "targets": ["$psu_a"]},
            ],
        },
        "expected_note": (
            "has_safe_shutdown=True, safe_shutdown_targets=['psu001'], "
            "psu002 は shutdown 対象外"
        ),
    },
}


READMES = {
    "basic_voltage_set_and_measure": """# basic_voltage_set_and_measure

電源を 5V に設定し、その後測定値を取得する最小例。

## Intended tool sequence
1. `validate_experiment_plan(plan)`
2. `dry_run_plan(plan)`
3. `start_experiment_job(plan, owner="agent")`
4. `get_job_result(job_id)`

## Required bindings
- `psu`: 電源の alias (例: psu001)

## Expected behaviour
- `VOLT 5.0` → `MEAS:VOLT?` の 2 行が rendered_scpi に並ぶ
- `step_count_dsl = 2`、`step_count_expanded = 2`
""",
    "voltage_sweep_with_wait": """# voltage_sweep_with_wait

電圧を `[1.0, 2.0, 3.0]` V で sweep し、各点で 1 秒待ってから DMM で測定。

## Intended tool sequence
1. `validate_experiment_plan(plan)`
2. `dry_run_plan(plan)` で 3 × 3 = 9 個の rendered_steps を確認
3. `start_experiment_job(plan)`

## Required bindings
- `psu`: 電源
- `dmm`: 電圧計

## Expected behaviour
- sweep が compile 時に展開され、IR Plan は 9 step (3 値 × 3 body)
- `summary.step_count_expanded = 9`

## Failure handling
- `set_voltage` が range 違反なら `parameter_invalid`
- `dmm` 未識別なら `not_identified`
""",
    "voltage_sweep_with_wait_for_stable": """# voltage_sweep_with_wait_for_stable

電圧を sweep しながら、各点で温度計が安定してから DMM で測定する。

## Intended tool sequence
1. `validate_experiment_plan(plan)`
2. `dry_run_plan(plan)` で polling_safe warning の有無を確認
3. `start_experiment_job(plan)`

## Required bindings
- `psu`: 電源
- `dmm`: 電圧計
- `temp`: 温度計

## Expected warnings
- `temp001.measure_temperature` が `polling_safe: True` を持たない場合、
  `polling_safe_false` warning が出る (実行は可能)

## Expected behaviour
- sweep が 3 値展開
- 各値で wait_for_stable が温度安定 (window 30s 内 max-min <= 0.2℃) まで polling
- `timeout_s=300` を超えると step failed
""",
    "partial_failure_group_measurement": """# partial_failure_group_measurement

3 つの DMM を parallel で同時に測定する。一部が failed しても他は記録される。

## Intended tool sequence
1. `validate_experiment_plan(plan)`
2. `dry_run_plan(plan)` で 3 branch が共有 resource を持たないことを確認
3. `start_experiment_job(plan)`
4. `get_job_result(job_id)` で `result.results` に target_id ごとの結果を取得

## Required bindings
- `dmm_a` / `dmm_b` / `dmm_c`: 3 台の電圧計 (異なる resource)

## Expected behaviour
- 3 branch が GroupExecutor で並列実行 (concurrency=3)
- 各 branch が独立 resource を使うため真の並列
- 1 branch が失敗しても `failure_policy.mode=continue` (デフォルト) で他は継続
- 結果は `status=partial_failure` または `ok`、`summary.success` で成功数を確認

## Failure handling
- LLM は `results` を見て失敗 target_id だけ retry する判断ができる
""",
    "safe_shutdown_explicit_targets": """# safe_shutdown_explicit_targets

複数機器を操作した後、特定の機器だけを safe_shutdown する例。

## Intended tool sequence
1. `validate_experiment_plan(plan)`
2. `dry_run_plan(plan)` で `safe_shutdown_targets` に psu001 だけが含まれることを確認
3. `start_experiment_job(plan)`

## Required bindings
- `psu_a` / `psu_b`: 2 台の電源

## Expected behaviour
- compile 時に `safe_shutdown.targets = ["$psu_a"]` が解決され、
  `CompiledPlan.safe_shutdown_targets = ["psu001"]` になる
- 実行時 (v0.8.0.1+) は psu001 にのみ safe_shutdown が走り、psu002 はそのまま

## Common errors
- `safe_shutdown.targets=[]` (空配列) は validation error (`safe_shutdown_targets_empty`)
- `targets` に未知の binding (例: `$unknown`) を指定すると `unknown_binding` error
""",
}


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    for name, content in EXAMPLES.items():
        d = BASE / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "plan.json").write_text(
            json.dumps(content["plan"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (d / "expected_dry_run.json").write_text(
            json.dumps({
                "expected_summary": content["expected_note"],
                "valid": True,
                "name": content["plan"]["name"],
                "dsl_version": content["plan"]["dsl_version"],
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (d / "README.md").write_text(READMES[name], encoding="utf-8")
        print(f"created: {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
