"""
v1.1 (spike, experimental): InstrumentBackend Protocol

将来 REST / simulator / replay backend を扱えるかの **抽出可能性の確認**。
v1.1 では既存 `VisaManager` / `MockVisaManager` の経路を変更せず、Protocol
の型ヒントだけを公開する。

⚠ `VisaManager` / `MockVisaManager` は **意図的に** `InstrumentBackend` を
明示継承していない (動作変更を避けるため)。両者は duck-typed に compatible
である、という存在証明としてのみ使う。

詳細: `docs/backend_abstraction.md`
"""
from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class InstrumentBackend(Protocol):
    """機器との通信を抽象化する backend (v1.1 experimental, NOT yet wired)

    実装候補:
      - pyvisa: 既存 ``VisaManager`` (PyVISA wrapper)
      - mock:   ``visa_mcp.testing.MockVisaManager``
      - replay: bundle の過去応答を deterministic に返す (v1.2+ 候補)
      - rest:   REST device adapter (v1.2+ 候補)
      - simulator: 数学モデルベース backend (v1.2+ 候補)
    """

    backend_id: str

    async def list_resources(self) -> list[str]: ...

    async def query(
        self,
        resource_name: str,
        command: str,
        timeout_ms: int = 5000,
        read_termination: str = "\n",
        write_termination: str = "\n",
    ) -> str: ...

    async def write(
        self,
        resource_name: str,
        command: str,
        timeout_ms: int = 5000,
        read_termination: str = "\n",
        write_termination: str = "\n",
    ) -> None: ...
