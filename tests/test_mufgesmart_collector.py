"""三菱UFJ eスマート証券 収集スクリプトのユニットテスト（Playwright モック）"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import build_collector, load_site_module

_CODE = "mufg-esmart"
_mod = load_site_module(_CODE)
MufgEsmartCollector = _mod.MufgEsmartCollector


def _make(tmp_path, year=2025):
    return build_collector(tmp_path, _CODE, MufgEsmartCollector, year)


def test_init(tmp_path):
    c = _make(tmp_path)
    assert c.code == _CODE
    assert c.name == "MUFG eスマート証券"


def test_save_session_skips_empty_cookies(tmp_path):
    c = _make(tmp_path)
    fake_profile = tmp_path / "browser_profile"
    page = MagicMock()
    page.context.storage_state.return_value = {"cookies": []}
    with patch.object(c, "_browser_profile_dir", return_value=fake_profile):
        c._save_session(page)
    state_path = fake_profile / "storage_state.json"
    assert not state_path.exists()


def test_save_session_saves_when_cookies_exist(tmp_path):
    c = _make(tmp_path)
    fake_profile = tmp_path / "browser_profile"
    fake_profile.mkdir(parents=True, exist_ok=True)
    page = MagicMock()
    page.context.storage_state.return_value = {"cookies": [{"name": "s", "value": "v"}]}
    with patch.object(c, "_browser_profile_dir", return_value=fake_profile):
        c._save_session(page)
    state_path = fake_profile / "storage_state.json"
    assert state_path.exists()


def test_collect_error_when_pdf_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()
    page1 = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_open_trade_page", return_value=page1), \
         patch.object(c, "_navigate_to_pdf_report"), \
         patch.object(c, "_download_pdf", return_value=None), \
         patch.object(c, "log_result") as mock_log:
        c.collect()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "error"


def test_collect_success_flow(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()
    page1 = MagicMock()
    pdf_path = str(tmp_path / "raw" / "report.pdf")

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_open_trade_page", return_value=page1), \
         patch.object(c, "_navigate_to_pdf_report"), \
         patch.object(c, "_download_pdf", return_value=pdf_path), \
         patch.object(_mod, "convert_pdf_to_json", return_value={"code": _CODE}), \
         patch.object(c, "log_result") as mock_log:
        c.collect()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "success"
