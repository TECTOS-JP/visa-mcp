from __future__ import annotations
from fastmcp import FastMCP
from visa_mcp.session_manager import SessionManager
from visa_mcp.visa_manager import VisaError
from visa_mcp.utils.param_validator import validate_and_build_scpi, ParameterValidationError


def register_tools(mcp: FastMCP, session_mgr: SessionManager) -> None:

    @mcp.tool()
    async def query_instrument(
        resource_name: str,
        command: str,
        timeout_ms: int = 5000,
    ) -> dict:
        """
        任意の SCPI クエリコマンドを送信し応答を返す（汎用パススルー）。
        resource_name: VISA リソース文字列（例: "GPIB0::1::INSTR"）
        command: SCPI コマンド文字列（例: "*IDN?", "MEASure:VOLTage?"）
        timeout_ms: タイムアウト（ミリ秒）
        """
        session = session_mgr.get_session(resource_name)
        conn = session.definition.connection if (session and session.definition) else None

        try:
            response = await session_mgr._visa.query(
                resource_name,
                command,
                timeout_ms=timeout_ms,
                read_termination=conn.read_termination if conn else "\n",
                write_termination=conn.write_termination if conn else "\n",
            )
            return {"success": True, "data": {"response": response, "command": command}}
        except VisaError as e:
            return {"success": False, "error": type(e).__name__, "message": str(e), "resource_name": resource_name}

    @mcp.tool()
    async def send_command(
        resource_name: str,
        command: str,
        timeout_ms: int = 5000,
    ) -> dict:
        """
        応答を必要としない SCPI コマンドを送信する（汎用パススルー）。
        resource_name: VISA リソース文字列
        command: SCPI コマンド文字列（例: "*RST", "AUTOSet EXECute"）
        timeout_ms: タイムアウト（ミリ秒）
        """
        session = session_mgr.get_session(resource_name)
        conn = session.definition.connection if (session and session.definition) else None

        try:
            await session_mgr._visa.write(
                resource_name,
                command,
                timeout_ms=timeout_ms,
                read_termination=conn.read_termination if conn else "\n",
                write_termination=conn.write_termination if conn else "\n",
            )
            return {"success": True, "data": {"command": command, "resource_name": resource_name}}
        except VisaError as e:
            return {"success": False, "error": type(e).__name__, "message": str(e), "resource_name": resource_name}

    @mcp.tool()
    async def execute_named_command(
        resource_name: str,
        command_name: str,
        parameters: dict = {},
    ) -> dict:
        """
        YAML 定義に登録された名前付きコマンドを実行する。
        パラメータを型・範囲検証してから SCPI 文字列を組み立てて送信する。
        resource_name: VISA リソース文字列
        command_name: YAML 定義のコマンドキー（例: "measure_voltage"）
        parameters: コマンドパラメータ辞書（例: {"channel": 1}）
        """
        session = session_mgr.get_session(resource_name)
        if session is None:
            return {
                "success": False,
                "error": "SessionNotFound",
                "message": f"{resource_name} はまだ識別されていません。identify_instrument を先に実行してください。",
            }
        if session.definition is None:
            return {
                "success": False,
                "error": "NoDefinitionFound",
                "message": f"{resource_name} の YAML 定義が見つかりません。query_instrument で直接コマンドを送信してください。",
            }

        cmd_def = session.definition.commands.get(command_name)
        if cmd_def is None:
            available = list(session.definition.commands.keys())
            return {
                "success": False,
                "error": "CommandNotFound",
                "message": f"コマンド '{command_name}' は定義されていません。利用可能: {available}",
            }

        try:
            scpi = validate_and_build_scpi(cmd_def, parameters)
        except ParameterValidationError as e:
            return {"success": False, "error": "ParameterValidationError", "message": str(e)}

        conn = session.definition.connection
        timeout_ms = cmd_def.timeout_ms or conn.default_timeout_ms

        try:
            if cmd_def.type == "query":
                raw = await session_mgr._visa.query(
                    resource_name, scpi, timeout_ms=timeout_ms,
                    read_termination=conn.read_termination,
                    write_termination=conn.write_termination,
                )
                result = _cast_response(raw, cmd_def.returns.type)
                return {
                    "success": True,
                    "data": {
                        "command_name": command_name,
                        "scpi_sent": scpi,
                        "raw_response": raw,
                        "value": result,
                        "unit": cmd_def.returns.unit,
                    },
                }
            else:
                await session_mgr._visa.write(
                    resource_name, scpi, timeout_ms=timeout_ms,
                    read_termination=conn.read_termination,
                    write_termination=conn.write_termination,
                )
                return {
                    "success": True,
                    "data": {"command_name": command_name, "scpi_sent": scpi},
                }
        except VisaError as e:
            return {"success": False, "error": type(e).__name__, "message": str(e), "resource_name": resource_name}


def _cast_response(raw: str, return_type: str) -> object:
    raw = raw.strip()
    try:
        if return_type == "integer":
            return int(float(raw))
        elif return_type == "float":
            return float(raw)
        elif return_type == "boolean":
            return raw not in ("0", "OFF", "false", "FALSE")
    except (ValueError, TypeError):
        pass
    return raw
