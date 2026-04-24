"""野村證券持株会 収集スクリプトのユニットテスト（Playwright モック）"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import build_collector, load_site_module

_CODE = "nomura-mochikabu"
_mod = load_site_module(_CODE)
NomuraMochikabuCollector = _mod.NomuraMochikabuCollector


def _make(tmp_path, year=2025):
    return build_collector(tmp_path, _CODE, NomuraMochikabuCollector, year)


def test_init(tmp_path):
    c = _make(tmp_path)
    assert c.code == _CODE
    assert c.name == "野村證券持株会"


def test_year_month_patterns():
    patterns = _mod._year_month_patterns(2025)
    assert "2025年12月" in patterns
    assert "2026年01月" in patterns


def test_wait_for_login(tmp_path):
    c = _make(tmp_path)
    page = MagicMock()
    with patch.object(_mod, "_wait"), patch("builtins.input", return_value=""):
        c._wait_for_login(page)
    page.goto.assert_called_once_with(c.config["login_url"])


def test_parse_hidden_inputs_basic(tmp_path):
    c = _make(tmp_path)
    html = '''
    <form>
      <input type="hidden" name="token" value="abc123">
      <input type="hidden" name="year" value="2025">
      <input type="text" name="visible" value="ignore">
    </form>
    '''
    result = c._parse_hidden_inputs(html)
    assert result["token"] == "abc123"
    assert result["year"] == "2025"
    assert "visible" not in result


def test_parse_hidden_inputs_empty(tmp_path):
    c = _make(tmp_path)
    result = c._parse_hidden_inputs("<html><body></body></html>")
    assert result == {}


def test_find_report_link_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()
    page.locator.return_value.count.return_value = 0
    result = c._find_report_link(page, 2025)
    assert result is None


def test_collect_skip_when_report_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_wait_for_login"), \
         patch.object(c, "_navigate_to_list"), \
         patch.object(c, "_find_report_link", return_value=None), \
         patch.object(c, "log_result") as mock_log, \
         patch.object(_mod, "_wait"):
        c.run()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "skip"
