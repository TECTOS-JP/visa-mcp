from __future__ import annotations
import asyncio
import logging
from functools import partial

logger = logging.getLogger(__name__)

# pyvisa はオプション扱い（テスト時はモック可能）
try:
    import pyvisa
    import pyvisa.errors
    _PYVISA_AVAILABLE = True
except ImportError:
    _PYVISA_AVAILABLE = False


class VisaError(RuntimeError):
    pass

class VisaConnectionError(VisaError):
    pass

class VisaTimeoutError(VisaError):
    pass


class VisaManager:
    """
    pyvisa.ResourceManager のシングルトンラッパー。
    PyVISA のブロッキング呼び出しを asyncio.run_in_executor でラップして提供する。
    NI-VISA バックエンドのみ使用（フォールバックなし）。
    """

    def __init__(self) -> None:
        if not _PYVISA_AVAILABLE:
            raise VisaError(
                "pyvisa がインストールされていません。`pip install pyvisa` を実行してください。"
            )
        self._rm: pyvisa.ResourceManager | None = None
        # v0.4.0: リソース単位の排他ロック (同一機器への同時アクセスを直列化)
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, resource_name: str) -> asyncio.Lock:
        """resource_name ごとの asyncio.Lock を返す (なければ生成)。
        異なる機器への並列アクセスは妨げず、同一機器のみ逐次保証する。
        """
        lock = self._locks.get(resource_name)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[resource_name] = lock
        return lock

    def _get_rm(self) -> "pyvisa.ResourceManager":
        if self._rm is None:
            try:
                self._rm = pyvisa.ResourceManager()  # NI-VISA（Windowsデフォルト）
                logger.info("NI-VISA ResourceManager を初期化しました。")
            except Exception as e:
                raise VisaConnectionError(f"NI-VISA の初期化に失敗しました: {e}") from e
        return self._rm

    async def _run(self, func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def list_resources(self, query: str = "?*::INSTR") -> list[str]:
        def _list():
            rm = self._get_rm()
            try:
                return list(rm.list_resources(query))
            except Exception as e:
                raise VisaError(f"リソース列挙に失敗しました: {e}") from e

        return await self._run(_list)

    async def query(
        self,
        resource_name: str,
        command: str,
        timeout_ms: int = 5000,
        read_termination: str = "\n",
        write_termination: str = "\n",
    ) -> str:
        def _query():
            rm = self._get_rm()
            try:
                res = rm.open_resource(resource_name)
                res.timeout = timeout_ms
                res.read_termination = read_termination
                res.write_termination = write_termination
                try:
                    return res.query(command)
                finally:
                    res.close()
            except pyvisa.errors.VisaIOError as e:
                if "timeout" in str(e).lower():
                    raise VisaTimeoutError(
                        f"{resource_name} がタイムアウトしました（{timeout_ms}ms）: {e}"
                    ) from e
                raise VisaConnectionError(
                    f"{resource_name} への接続に失敗しました: {e}"
                ) from e
            except Exception as e:
                raise VisaError(f"クエリ中にエラーが発生しました: {e}") from e

        async with self._get_lock(resource_name):
            return await self._run(_query)

    async def write(
        self,
        resource_name: str,
        command: str,
        timeout_ms: int = 5000,
        read_termination: str = "\n",
        write_termination: str = "\n",
    ) -> None:
        def _write():
            rm = self._get_rm()
            try:
                res = rm.open_resource(resource_name)
                res.timeout = timeout_ms
                res.read_termination = read_termination
                res.write_termination = write_termination
                try:
                    res.write(command)
                finally:
                    res.close()
            except pyvisa.errors.VisaIOError as e:
                if "timeout" in str(e).lower():
                    raise VisaTimeoutError(
                        f"{resource_name} がタイムアウトしました（{timeout_ms}ms）: {e}"
                    ) from e
                raise VisaConnectionError(
                    f"{resource_name} への接続に失敗しました: {e}"
                ) from e
            except Exception as e:
                raise VisaError(f"コマンド送信中にエラーが発生しました: {e}") from e

        async with self._get_lock(resource_name):
            await self._run(_write)

    def close(self) -> None:
        if self._rm is not None:
            try:
                self._rm.close()
            except Exception:
                pass
            self._rm = None
