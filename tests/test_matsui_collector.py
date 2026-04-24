"""松井証券 収集スクリプトのユニットテスト（Playwright モック）"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FIXTURE_XML, build_collector, load_site_module

_CODE = "matsui"
_mod = load_site_module(_CODE)
MatsuiCollector = _mod.MatsuiCollector


def _make(tmp_path, year=2025):
    return build_collector(tmp_path, _CODE, MatsuiCollector, year)


def test_init(tmp_path):
    c = _make(tmp_path)
    assert c.code == _CODE
    assert c.name == "松井証券"


def test_year_month_patterns():
    patterns = _mod._year_month_patterns(2025)
    assert "2025年12月" in patterns
    assert "2026年01月" in patterns


def test_wait_for_login(tmp_path):
    c = _make(tmp_path)
    page = MagicMock()
    with patch.object(_mod, "_wait"), patch("builtins.input", return_value=""):
        c._wait_for_login(page)
    page.goto.assert_called_once_with(_mod._LOGIN_URL)


def test_find_xml_link_found(tmp_path):
    c = _make(tmp_path, year=2025)
    frame = MagicMock()
    link = MagicMock()
    link.count.return_value = 1
    frame.get_by_role.return_value = link
    result = c._find_xml_link(frame, 2025)
    assert result is link.first


def test_find_xml_link_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    frame = MagicMock()
    frame.get_by_role.return_value.count.return_value = 0
    result = c._find_xml_link(frame, 2025)
    assert result is None


def test_convert_to_json_skips_without_xml(tmp_path, capsys):
    c = _make(tmp_path)
    c._convert_xml_to_json(["data/foo.pdf"])
    assert "スキップ" in capsys.readouterr().out


def test_convert_to_json_with_xml(tmp_path):
    if not FIXTURE_XML.exists():
        pytest.skip("teg204_sample.xml が存在しない")
    c = _make(tmp_path)
    c.output_dir.mkdir(parents=True, exist_ok=True)
    c._convert_xml_to_json([str(FIXTURE_XML)])
    json_path = c.output_dir.parent / "nenkantorihikihokokusho.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["code"] == _CODE


def test_collect_skip_when_download_empty(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()
    popup = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_wait_for_login"), \
         patch.object(c, "_navigate_to_report_popup", return_value=popup), \
         patch.object(c, "_download_files", return_value=[]), \
         patch.object(c, "log_result") as mock_log, \
         patch.object(_mod, "_wait"):
        c.run()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "skip"
