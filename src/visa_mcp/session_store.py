"""v2.3.0: bindings / identified state の永続化 (process 再起動耐性).

長時間運用 / クラッシュ復旧 / 複数エージェント運用で
`bind_definition` / `identify_instrument` の結果を毎回やり直す
コストが問題になっていた。特に *IDN? 非対応機器
(例: Yokogawa 7563) は手動 bind がほぼ毎回必要だった。

このモジュールは:
- JSON ファイル (`~/.visa-mcp/sessions.json` または
  `$VISA_MCP_SESSION_STORE`) に bindings を保存
- SessionManager 起動時に auto-restore (definition を YAML registry
  から再 lookup; 見つからなければ warning して skip)
- bind / identify / clear のたびに persist

JSON schema (v1):

    {
      "version": 1,
      "bindings": {
        "GPIB0::2::INSTR": {
          "manufacturer": "Yokogawa",
          "model": "7563",
          "bind_method": "manual",         // "manual" | "identify"
          "idn_response": "",              // identify 時のみ
          "bound_at": "2026-05-29T12:34:56+00:00",
          "last_seen_at": "2026-05-29T12:34:56+00:00"
        }
      }
    }

API 設計指針:
- store=None でも SessionManager は従来通り動く (in-memory)
- 復元時に definition 解決失敗しても record 自体は残し、後で
  registry が更新されたら正常に解決できるようにする
- file 書き込み失敗は warn して落ちない (運用継続性優先)
"""
from __future__ import annotations
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_PATH_REL = ".visa-mcp/sessions.json"


def default_session_store_path() -> Path:
    """env override or ~/.visa-mcp/sessions.json"""
    raw = os.environ.get("VISA_MCP_SESSION_STORE", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / DEFAULT_PATH_REL


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    """JSON file に bindings を永続化するシンプルな key-value store.

    Thread/process safety: 単一 process 内で SessionManager から
    sequential に使われる前提。multi-process 排他は将来課題
    (lockfile or SQLite に置き換え)。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_session_store_path()
        self._bindings: dict[str, dict[str, Any]] = {}

    # ---------- file I/O ----------

    def load(self) -> dict[str, dict[str, Any]]:
        """Load from disk. 不正・欠損ファイルは空辞書扱い (warning)."""
        if not self.path.is_file():
            self._bindings = {}
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(
                "session store の読み込み失敗 (path=%s): %s。"
                "空の bindings として継続します", self.path, e)
            self._bindings = {}
            return {}
        if not isinstance(data, dict):
            logger.warning(
                "session store の形式が不正 (path=%s, 型=%s)。"
                "空扱いで継続", self.path, type(data).__name__)
            self._bindings = {}
            return {}
        version = data.get("version")
        if version != SCHEMA_VERSION:
            logger.warning(
                "session store の schema version=%r (期待 %d)。"
                "互換 best-effort で読み込みます", version, SCHEMA_VERSION)
        bindings = data.get("bindings") or {}
        if not isinstance(bindings, dict):
            logger.warning(
                "session store の bindings が dict でない: %r。"
                "空扱いで継続", type(bindings).__name__)
            self._bindings = {}
            return {}
        # 値の型を最低限 sanity check (str-key, dict-value)
        cleaned: dict[str, dict[str, Any]] = {}
        for k, v in bindings.items():
            if not isinstance(k, str) or not isinstance(v, dict):
                continue
            cleaned[k] = v
        self._bindings = cleaned
        return dict(self._bindings)

    def save(self) -> None:
        """Atomic write (tmpfile + replace)。失敗は warning."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": SCHEMA_VERSION,
                "bindings": self._bindings,
            }
            # tmpfile + rename for atomicity (Windows でも replace は atomic)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8",
                dir=str(self.path.parent),
                prefix=".sessions_", suffix=".tmp", delete=False,
            ) as tf:
                json.dump(payload, tf, ensure_ascii=False, indent=2)
                tmp_path = Path(tf.name)
            os.replace(tmp_path, self.path)
        except Exception as e:
            logger.warning(
                "session store の保存失敗 (path=%s): %s。"
                "in-memory のみで継続", self.path, e)

    # ---------- mutating ops ----------

    def upsert(
        self, resource: str, *,
        manufacturer: str, model: str,
        bind_method: str,
        idn_response: str = "",
        bound_at: str | None = None,
    ) -> None:
        """add or update. 既存 record があれば bound_at は保持。"""
        existing = self._bindings.get(resource) or {}
        rec = {
            "manufacturer": manufacturer,
            "model": model,
            "bind_method": bind_method,
            "idn_response": idn_response,
            "bound_at": existing.get("bound_at") or bound_at or _now_iso(),
            "last_seen_at": _now_iso(),
        }
        self._bindings[resource] = rec
        self.save()

    def touch(self, resource: str) -> None:
        """last_seen_at を現在時刻に更新 (binding 内容は変更しない)。"""
        if resource not in self._bindings:
            return
        self._bindings[resource]["last_seen_at"] = _now_iso()
        self.save()

    def remove(self, resource: str) -> bool:
        if resource in self._bindings:
            del self._bindings[resource]
            self.save()
            return True
        return False

    def clear_all(self) -> None:
        self._bindings = {}
        self.save()

    # ---------- read ops ----------

    def get(self, resource: str) -> dict[str, Any] | None:
        rec = self._bindings.get(resource)
        return dict(rec) if rec else None

    def list_all(self) -> dict[str, dict[str, Any]]:
        return {k: dict(v) for k, v in self._bindings.items()}
