from __future__ import annotations
import logging
import sys
from pathlib import Path

from fastmcp import FastMCP

from visa_mcp.instrument_registry import InstrumentRegistry
from visa_mcp.visa_manager import VisaManager
from visa_mcp.session_manager import SessionManager
from visa_mcp.tools import discovery, commands, pdf_extractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)

INSTRUMENTS_DIR = Path(__file__).parent.parent.parent / "instruments"

mcp = FastMCP(
    name="visa-instrument-controller",
    instructions=(
        "PyVISA 経由で GPIB / シリアル計測器を制御する MCP サーバーです。\n"
        "使い方:\n"
        "1. list_resources で接続機器を列挙する\n"
        "2. identify_instrument または identify_all_instruments で機器を識別する\n"
        "   *IDN? 非対応の古い機器は bind_definition で手動バインドする\n"
        "3. list_commands で利用可能なコマンドを確認する\n"
        "4. execute_named_command で型安全にコマンドを実行する\n"
        "   または query_instrument / send_command で任意のコマンドを直接送信する\n"
        "5. 新しい機器の場合は extract_pdf_commands でマニュアル PDF から YAML 草案を生成する"
    ),
)

visa_mgr = VisaManager()
registry = InstrumentRegistry(INSTRUMENTS_DIR)
session_mgr = SessionManager(visa_mgr, registry)

discovery.register_tools(mcp, session_mgr)
commands.register_tools(mcp, session_mgr)
pdf_extractor.register_tools(mcp)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
