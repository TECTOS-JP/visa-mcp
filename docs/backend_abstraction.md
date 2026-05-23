# Backend abstraction (v1.1 spike, experimental)

合言葉: **「導入ではなく、抽出可能性の確認」**

v1.1 では `InstrumentBackend` Protocol を `src/visa_mcp/backends/base.py`
に **型ヒントとして** 追加する。既存 `VisaManager` / `MockVisaManager` の
動作は **変更しない**。

## 現状の責務 (v1.x で `visa-mcp` が所有)

| layer | 内容 |
|-------|------|
| MCP tool layer | `validate_experiment_plan` / `start_experiment_job` / `get_job_*` / ... |
| DSL validation / dry-run | `validate_and_compile` |
| Job execution | `JobManager` / `RecipeStep` 経路 / state machine |
| Observation / export / bundle | `get_experiment_timeline` / `export_experiment_results` / `export_experiment_bundle` |
| VISA / SCPI 通信 | `VisaManager` / `MockVisaManager` |

## 将来の backend 境界候補 (Protocol)

```python
class InstrumentBackend(Protocol):
    backend_id: str
    async def list_resources(self) -> list[str]: ...
    async def query(self, resource: str, command: str, ...) -> str: ...
    async def write(self, resource: str, command: str, ...) -> None: ...
```

実装候補 (v1.x 期間中は **不実装**、v1.2+ 検討):

| backend | 用途 |
|---------|------|
| `pyvisa` | 既存 `VisaManager` を adapter 化 |
| `mock` | 既存 `MockVisaManager` (benchmark / CI) |
| `replay` | bundle の過去応答を deterministic に再生 |
| `rest` | REST-controlled device adapter |
| `simulator` | 数学モデル backend |

⚠ **LabVIEW backend は候補に含めない** (これまでの方針通り、外部
GUI runtime の影響を `visa-mcp` に持ち込まない)。

## v1.1 spike のスコープ

| 項目 | v1.1 で実装 |
|------|-----------|
| `InstrumentBackend` Protocol 公開 | ✅ |
| `runtime_checkable` 化 | ✅ |
| 既存 `VisaManager` / `MockVisaManager` を Protocol 明示継承 | ❌ (動作変更を避ける) |
| MCP tool 層に backend を注入する API | ❌ |
| backend plugin loader | ❌ (v1.2+) |
| remote backend | ❌ (v1.x 非対応) |
| 非 VISA production support | ❌ (v1.x 非対応) |
| runtime repository 分割 | ❌ ([`docs/naming_and_repository_strategy.md`](naming_and_repository_strategy.md)) |
| Human intent / approval 層 | ❌ (v1.3+、backend と無関係) |

## なぜ Protocol を「導入しない」のか

- v1.0 で API を凍結したばかりで、内部経路を一度に置換すると stable core を
  揺らすリスクがある
- `VisaManager` と `MockVisaManager` は **既に duck-typed に互換**
  (同じ `query` / `write` async API)。実需が確認できた時点で adapter 化すれば
  十分
- 抽象化を先に作ると、後から実装で噛み合わずに **抽象が間違っていた**
  ことに気付くケースが多い

## 将来 backend 切り出しの判断基準

`docs/naming_and_repository_strategy.md` と同じ条件:

- 非 VISA backend の外部需要が複数件
- Protocol が 3 以上の実 backend で動く
- runtime と backend の coupling が import / 内部 API ゼロ
- 利用者向け移行計画 1 リリース以上で予告

これらが揃えば v1.2+ で本格抽象化、v2.x で repo 分割を検討する。

## 関連 docs

- [`docs/naming_and_repository_strategy.md`](naming_and_repository_strategy.md)
- [`docs/v1_stability_policy.md`](v1_stability_policy.md)
