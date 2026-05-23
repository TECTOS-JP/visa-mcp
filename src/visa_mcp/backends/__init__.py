"""v1.1 (experimental, spike): backend abstraction skeleton.

`docs/backend_abstraction.md` 参照。v1.1 では Protocol のみ公開し、既存
`VisaManager` / `MockVisaManager` 経路は変更しない。
"""
from visa_mcp.backends.base import InstrumentBackend

__all__ = ["InstrumentBackend"]
