# Separation Notes (v1.9, draft for v2.0 split)

合言葉: **「v2.0 でリポジトリを分けるための、v1.9 から積む下準備
メモ」**

ロードマップ v6 の Phase A (v1.9〜v1.11) で固める情報を、まず軽い
形でここに集約する。v1.10 で `module_ownership.yaml` と
`split_manifest.yaml` の機械可読版に昇格する予定。

## 分離の最終ゴール (v2.0)

- `lab-executor-mcp` (新規 repo): runtime + DSL + Job + Observation
  + Benchmark + Export + Audit + **definition pack ecosystem 全部** +
  instrument 定義 schema / response_format parser
- `visa-mcp` (現 repo): PyVISA backend 実装 (`VisaManager` /
  `PyVisaBackend` adapter) + raw VISA + PDF extractor 残置検討

詳細はロードマップ v6 「v2.0 分離計画」section 参照。

## v1.9 で固定した境界 (boundary CI)

### Runtime 候補 module (PyVISA / visa_manager 非依存)

```
visa_mcp.dsl
visa_mcp.extension
visa_mcp.extension_packaging
visa_mcp.extension_install
visa_mcp.extension_catalog
visa_mcp.extension_authoring
visa_mcp.extension_integrity
visa_mcp.instrument_authoring
visa_mcp.observation
visa_mcp.testing
```

これらの **module top-level** で:
- `import pyvisa` / `from pyvisa import ...` → **禁止**
- `from visa_mcp.visa_manager import ...` / `import visa_mcp.visa_manager`
  → **禁止**

関数 / メソッド内の lazy import は許容 (例: `testing/mock_instruments.py`
は VISA timeout 互換 error を投げるために遅延 import している)。

CI で確認: `tests/test_separation_boundary.py` +
`python -m visa_mcp.dev.dependency_report` + GitHub Actions の
`pyvisa-not-installed` job。

### Backend layer (現状)

```
visa_mcp.visa_manager       ← PyVISA 透過 (将来 PyVisaBackend adapter)
visa_mcp.tools.discovery    ← PyVISA resource 列挙
visa_mcp.tools.pdf_extractor ← v6 では再分類検討 (authoring 寄り)
```

## v1.10 で詰める項目

- `docs/separation/module_ownership.yaml` を生成
- import dependency graph (`docs/separation/dependency_graph.md`)
- `split_manifest.yaml` (v2.0 で `git filter-repo` する path のリスト)
- `step_executor.py` / `tools/commands.py` の layer 内分割案
  (YAML 解釈側 vs PyVISA 透過側)

## v1.11 で詰める項目

- import violation を 0 件に
- `InstrumentBackend` Protocol 実体化 (`PyVisaBackend` /
  `MockBackend`)
- `src/lab_executor_candidate/` 仮 namespace で split rehearsal

## v2.0 への TODO メモ (v1.9 時点で書き留めておく)

- **PDF extractor**: 重い PDF 依存 (pypdf 等) は **optional extra** に
  する。`pip install lab-executor-mcp` ではなく
  `pip install lab-executor-mcp[pdf]` のような extras 設計を検討
- **tool registration boundary**:
  - `lab-executor-mcp`: MCP tool 定義 / schema / response envelope を所有
  - `visa-mcp`: `PyVisaBackend` を注入して従来互換 MCP server を起動
- **install path 段階移行**:
  - v2.0: `~/.visa-mcp/extensions/` を互換のため継続
  - v2.1: `~/.lab-executor/extensions/` 並走 / migration 案
  - v2.2: default 切替判断
- **`~/.visa-mcp/` 配下の audit / job DB** も同様の段階移行が必要
  (Phase C で別途検討)

## 参考

- ロードマップ v6: `~/.claude/plans/gpib-mcp-pure-ullman.md`
- `docs/naming_and_repository_strategy.md`
- `docs/backend_abstraction.md`
- `docs/v1_stability_policy.md`
