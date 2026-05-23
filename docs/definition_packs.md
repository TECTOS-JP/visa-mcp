# Definition Packs (v1.2, experimental)

`definition pack` は **instrument definitions / registry entries /
benchmark tasks / experiment templates** などをまとめた
**非実行拡張パッケージ**。Python code は含まない。

`plugin` (実行コード拡張) とは異なる。v1.2 では plugin は未対応で、
**definition pack のみ**を拡張単位とする。

## `extension.yaml` (manifest) 仕様

```yaml
extension_id: tectos.mock.basic     # 一意の reverse-DNS 形式推奨
name: Basic Mock Instrument Pack
version: 0.1.0                       # SemVer
type: definition_pack                # v1.2 では definition_pack のみ
visa_mcp_compatibility: ">=1.2,<2.0" # SemVer 範囲指定 (PEP 440)
description: "Mock PSU / DMM definitions and 1 benchmark for CI use"
author: "your-name <you@example.com>"
homepage: "https://github.com/your/repo"
license: "MIT"

contents:
  instruments:
    - instruments/mock_psu.yaml
    - instruments/mock_dmm.yaml
  benchmarks:
    - benchmarks/task_001.yaml
  templates:
    - templates/voltage_sweep.json
  mock_scenarios:
    - fixtures/scenarios.yaml
  registry_entries:
    - registry_entries.yaml

stability:
  support_level: tested          # registry の support_level と同じ語彙
  executable_code: false         # 必ず false (true なら validate 拒否)
```

## 必須フィールド

| フィールド | 型 | 意味 |
|-----------|----|------|
| `extension_id` | str | 一意の ID (`vendor.scope.name` 推奨) |
| `name` | str | 表示名 |
| `version` | str | SemVer (例: `0.1.0`) |
| `type` | `"definition_pack"` | v1.2 では他値は拒否 |
| `visa_mcp_compatibility` | str | `>=1.2,<2.0` 等 |
| `contents` | dict | 中身のファイル参照 (5 sub-section、すべて optional だが少なくとも 1 つ非空) |
| `stability.support_level` | enum | `verified / tested / experimental / draft` |
| `stability.executable_code` | bool | **必ず `false`** (v1.2 制約) |

## CLI 検証

```bash
visa-mcp validate extension <path-to-extension.yaml> [--json]
```

検査内容:

- `executable_code: false` (true なら error)
- `type: definition_pack` (他は error)
- `visa_mcp_compatibility` の SemVer 文法 (簡易)
- 参照ファイル全てが extension.yaml 配下に存在
- 各 instrument YAML が `validate_instrument_file` を通る
- 各 benchmark YAML が `BenchmarkTask` schema を通る
- 各 template JSON が `ExperimentPlan` を通る
- 各 mock_scenario YAML が `MockVisaManager` の scenarios_from_dict を通る
- `stability.support_level` が 4 段階のいずれか

## 配布方法 (v1.2 informal)

v1.2 では definition pack の自動 install / discovery は未対応。
利用者は以下のどちらかで使う:

1. `git clone <pack repo>` → ローカル参照
2. `extension.yaml` を含む zip / tarball を手動展開

将来 (v1.3+) で `visa-mcp install extension <url>` のような CLI を検討。

## なぜ Python plugin にしないか

- v1.0 stable core 直後に任意コード実行 API を入れると security / lifecycle
  / version compatibility / sandbox 設計に大きく時間を取られる
- AI エージェント向け実験基盤として、外部 plugin が安全な Python code を
  提供する保証がない
- YAML/JSON 定義で表現できる拡張のほうが **AI エージェントが読みやすい**

v1.3+ で plugin entry_points を検討する場合も、まず definition pack が
普及してから判断する。

## 関連 docs

- [`extension_policy.md`](extension_policy.md) — v1.2 拡張ポリシー全体
- [`registry_contribution.md`](registry_contribution.md) — registry への
  contribute 手順
- [`v1_stability_policy.md`](v1_stability_policy.md) — experimental スコープ
