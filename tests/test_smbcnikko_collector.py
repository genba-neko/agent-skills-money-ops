"""SMBC日興証券 収集スクリプトのユニットテスト（Playwright モック）"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FIXTURE_XML, build_collector, load_site_module

_CODE = "smbcnikko"
_mod = load_site_module(_CODE)
SMBCNikkoCollector = _mod.SMBCNikkoCollector


def _make(tmp_path, year=2025):
    return build_collector(tmp_path, _CODE, SMBCNikkoCollector, year)


def test_init(tmp_path):
    c = _make(tmp_path)
    assert c.code == _CODE
    assert c.name == "SMBC日興証券"


def test_year_month_patterns_instance(tmp_path):
    # smbcnikko は _year_month_patterns がインスタンスメソッド
    c = _make(tmp_path)
    patterns = c._year_month_patterns(2025)
    assert "2025/12" in patterns
    assert "2026/01" in patterns


def test_wait_for_login(tmp_path):
    c = _make(tmp_path)
    page = MagicMock()
    with patch.object(_mod, "_wait"), patch("builtins.input", return_value=""):
        c._wait_for_login(page)
    page.goto.assert_called_once_with(_mod._LOGIN_URL)


def test_wait_for_login_skips_when_logged_in(tmp_path):
    c = _make(tmp_path)
    page = MagicMock()
    page.url = "https://trade.smbcnikko.co.jp/Trade/0/top/"
    with patch("builtins.input") as mock_input:
        c._wait_for_login(page)
    mock_input.assert_not_called()
    assert c._session is page


def test_find_xml_link_found(tmp_path):
    c = _make(tmp_path, year=2025)
    session = MagicMock()
    row = MagicMock()
    row.count.return_value = 1
    # locator("tr").filter(...).filter(...) → row
    session.locator.return_value.filter.return_value.filter.return_value = row
    result = c._find_xml_link(session, 2025)
    assert result is row.first.locator.return_value.first


def test_find_xml_link_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    session = MagicMock()
    session.locator.return_value.filter.return_value.filter.return_value.count.return_value = 0
    result = c._find_xml_link(session, 2025)
    assert result is None


def test_convert_to_json_skips_without_xml(tmp_path, capsys):
    c = _make(tmp_path)
    c._convert_to_json(["data/foo.pdf"])
    assert "スキップ" in capsys.readouterr().out


def test_convert_to_json_with_xml(tmp_path):
    if not FIXTURE_XML.exists():
        pytest.skip("teg204_sample.xml が存在しない")
    c = _make(tmp_path)
    c.output_dir.mkdir(parents=True, exist_ok=True)
    c._convert_to_json([str(FIXTURE_XML)])
    json_path = c.output_dir.parent / "nenkantorihikihokokusho.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["code"] == _CODE


def test_collect_skip_when_xml_link_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()
    c._session = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_wait_for_login"), \
         patch.object(c, "_save_session_state"), \
         patch.object(c, "_navigate_to_report_list"), \
         patch.object(c, "_find_xml_link", return_value=None), \
         patch.object(c, "log_result") as mock_log, \
         patch.object(_mod, "_wait"):
        c.collect()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "skip"
