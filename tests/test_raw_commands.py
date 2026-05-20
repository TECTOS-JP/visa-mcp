"""v0.4.0 raw command 安全対策のテスト"""
from visa_mcp.tools.commands import _detect_dangerous_keywords


def test_query_form_is_safe():
    """? を含む query 形式は危険キーワード扱いされない"""
    assert _detect_dangerous_keywords("*IDN?") == []
    assert _detect_dangerous_keywords("MEAS:VOLT?") == []
    assert _detect_dangerous_keywords("SYST:ERR?") == []


def test_dangerous_write_detected():
    """状態変更コマンドは検出される"""
    assert "VOLT" in _detect_dangerous_keywords("VOLT 5.0")
    assert "*RST" in _detect_dangerous_keywords("*RST")
    assert "OUTP" in _detect_dangerous_keywords("OUTP ON")
    assert "CURR" in _detect_dangerous_keywords("CURR 1.5")


def test_multiple_keywords_detected():
    hits = _detect_dangerous_keywords("VOLT 5; OUTP ON")
    assert "VOLT" in hits
    assert "OUTP" in hits


def test_benign_commands_not_detected():
    """無害なコマンドは検出されない"""
    assert _detect_dangerous_keywords("") == []
    assert _detect_dangerous_keywords("SYST:VERS?") == []


def test_dangerous_keywords_module_import():
    """モジュールが import できる (環境変数で raw 機能の有効/無効が切り替わる)"""
    from visa_mcp.tools import commands
    assert hasattr(commands, "RAW_COMMANDS_ENABLED")
    assert hasattr(commands, "_DANGEROUS_KEYWORDS")
    assert "VOLT" in commands._DANGEROUS_KEYWORDS
    assert "*RST" in commands._DANGEROUS_KEYWORDS
