# Operational integrity (audit + locks, v0.9.3 experimental)

合言葉:「実験を実行できるだけでなく、誰が・いつ・何を・どの resource に
対して行い、なぜ失敗 / 拒否されたかを後から追えるようにする」

## auditテーブルの位置づけ

| テーブル | 役割 | 例 |
|----------|------|---|
| `job_events` | Job 内部の進行記録 | step_started / step_completed / barrier / polling_progress |
| `audit` | **外部から見た操作 / 安全拒否 / 運用記録** (新規 v0.9.3) | tool_called / lock_blocked / safety_blocked / export_created / server_started |

**両者を同じイベントで重複させない**。`step_started` は audit に不要、
`safety_blocked` は job_events だけでなく audit にも残す。

## 記録される event_type (v0.9.3 MVP)

P0 (実装済):

- `server_started` (server 起動時、stale lock 解放数を metadata に記録)
- `job_started` / `job_failed` (`start_experiment_job`)
- `job_cancelled` (`cancel_job`)
- `resume_started` (`resume_job` で新 Job 作成成功時)

P1 (v0.9.3.x 以降):

- `tool_called` / `tool_completed` / `tool_failed` (全 MCP tool 一律 hook)
- `safety_blocked`
- `resource_lock_acquired` / `_blocked` / `_released`
- `export_created`
- `validate_plan_failed` / `dry_run_warning`

## redaction (sensitive keys + 大量データ)

`summarize_for_audit(payload)` が以下を自動適用:

| 入力 | 変換 |
|------|------|
| `len > 200` の文字列 | `{"_truncated": True, "len": N, "head": "..."}` |
| `len > 5` の list | `{"_truncated_list": True, "len": N, "head": [...]}` |
| key に `token` / `api_key` / `password` / `secret` / `authorization` / `credentials` を含む | `[REDACTED]` |
| 深さ 6 超 | `"<deep>"` |

raw SCPI 応答全文 / 大量測定値 / file 内容 / credentials などは保存されない。

## `query_audit` (MCP tool)

```text
query_audit(
  job_id="", resource="", owner="",
  event_type="", severity="",
  since="", until="",
  limit=200, cursor=None,
  include_details=False,
)
```

- limit 上限 5000
- cursor は **`{timestamp, audit_id}` 複合** で同一 timestamp 取りこぼし対策
  (timeline cursor と同設計、v0.8.2.1 のレビュー指摘準拠)
- `include_details=true` で `request_summary` / `response_summary` /
  `metadata` も同梱 (default false で応答軽量)

返却:

```json
{
  "data": {
    "events": [{ "audit_id": "aud_...", "timestamp": "...",
                 "event_type": "job_started", "severity": "info",
                 "owner": "agent_a", "job_id": "...", ... }],
    "pagination": {
      "limit": 200, "returned": N, "has_more": false,
      "next_cursor": {"timestamp": "...", "audit_id": "aud_..."} | null
    },
    "include_details": false
  }
}
```

## locks テーブル

```sql
CREATE TABLE locks (
  resource TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  job_id TEXT,
  client_id TEXT,
  acquired_at TEXT NOT NULL,
  lease_until TEXT,      -- NULL 可 (lease 無し)
  lock_reason TEXT,
  metadata_json TEXT
);
```

- **lease_until** で stale 検出 (lease 過ぎは `stale=True`)
- server 起動時に自動で stale lock を解放 (`server_started` event の
  `metadata.stale_locks_released` に件数を記録)
- AuditStore に `acquire_lock` / `release_lock` / `list_locks` /
  `release_stale_locks` の helper を実装

v0.9.3 MVP では既存 `ResourceScheduler` (in-memory) と並行存在。永続 lock
への完全統合は v1.0 で検討。

## `list_locks` (MCP tool)

```text
list_locks(resource="", owner="", include_stale=True)
```

各 lock の `stale` フィールドで lease 切れを判定。AI エージェントは
blocked response の `blocked_by` 情報と組み合わせて `cancel_job` /
`wait_and_retry` を判断する。

## owner / client_id / job_id

| 識別子 | 範囲 |
|--------|------|
| `owner` | ユーザー / エージェントが指定する論理所有者 (free string) |
| `client_id` | MCP 接続元 / セッションを識別する ID (v0.9.3 では未取得、reserved) |
| `job_id` | Job 単位の実行 ID |

`audit` テーブルの各 row にこれら 3 つを記録 (空可)。複数エージェント運用時
の追跡に必須。

## 新規 `error_class`

| クラス | 意味 | 既存 `blocked` との関係 |
|--------|------|----------------------|
| `lock_conflict` | resource lock が他 owner に保持されている | `blocked` の詳細種別。v0.9.3 では reserved (実際の MCP response には引き続き `blocked` が出る) |
| `lock_stale` | 自 lock の lease が切れていた | 再取得が必要 |
| `audit_query_failed` | query_audit の内部 error | 通常は `internal` |

v1.0 で `error_class=blocked` + `details.reason=lock_conflict` に統一するか、
独立 class とするかを決定する。

## retention

v0.9.3 では **自動削除なし**。将来検討:

```yaml
audit:
  retention_days: 30     # 未実装
  max_rows: 100000       # 未実装
```

`query_audit` を運用者が定期呼び出しして必要分だけエクスポートし、SQLite を
`VACUUM` する運用を推奨 (v0.9.x 期間)。

## 関連 docs

- [`docs/jobs.md`](jobs.md) — Job model
- [`docs/error_taxonomy.md`](error_taxonomy.md) — `error_class` 一覧
- [`docs/compatibility.md`](compatibility.md) — audit / locks は v1.x 内
  **experimental** スコープ
