import pytest
import os
from unittest.mock import patch
from app import presentation

def test_safe_channel_name():
    """Verify channel names are sanitized for Discord (lowercase, alphanum, dashes)."""
    # Happy path
    assert presentation.safe_channel_name("General-Chat") == "general-chat"
    assert presentation.safe_channel_name("Game 123") == "game123"
    
    # Weird characters
    assert presentation.safe_channel_name("User's & Channel!") == "userschannel"
    
    # Empty or None
    assert presentation.safe_channel_name("") == presentation.CHANNEL_UNKNOWN
    assert presentation.safe_channel_name(None) == presentation.CHANNEL_UNKNOWN

def test_format_version_response():
    """Verify the version command output format."""
    response = presentation.format_version_response("v1.0.0-sha123")
    assert "**Active Node:** `v1.0.0-sha123`" in response

def test_format_announcement_with_env():
    """Verify announcement picks up the K_REVISION env var."""
    with patch.dict(os.environ, {"K_REVISION": "cloud-run-v2"}):
        msg = presentation.format_announcement("System Update")
        assert "System Update" in msg
        assert "`cloud-run-v2`" in msg

def test_format_announcement_default():
    """Verify announcement falls back to Local-Dev if env var missing."""
    # Ensure env var is absent for this test
    with patch.dict(os.environ, {}, clear=True):
        msg = presentation.format_announcement("Test")
        assert "`Local-Dev`" in msg

def test_build_cost_report():
    """Verify the math for the cost report (Gemini 2.5 Flash pricing)."""
    # 1M Input ($0.30), 1M Output ($2.50)
    report = presentation.build_cost_report("game_1", 1_000_000, 1_000_000)
    
    # Total should be $2.80
    assert "$0.3000" in report
    assert "$2.5000" in report
    assert "**TOTAL: $2.8000**" in report

def test_build_cost_report_zero():
    """Verify zero usage results in zero cost."""
    report = presentation.build_cost_report("game_0", 0, 0)
    assert "**TOTAL: $0.0000**" in report