"""tsumiki証券 収集スクリプトのユニットテスト（Playwright モック）"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import build_collector, load_site_module

_CODE = "tsumiki"
_mod = load_site_module(_CODE)
TsumikiCollector = _mod.TsumikiCollector


def _make(tmp_path, year=2025):
    return build_collector(tmp_path, _CODE, TsumikiCollector, year)


def test_init(tmp_path):
    c = _make(tmp_path)
    assert c.code == _CODE
    assert c.name == "tsumiki証券"


def test_handle_otp_skips_when_no_field(tmp_path):
    c = _make(tmp_path)
    page1 = MagicMock()
    page1.get_by_role.return_value.count.return_value = 0
    result = c._handle_otp(page1)
    assert result is True


def test_handle_otp_returns_false_on_empty_input(tmp_path):
    c = _make(tmp_path)
    page1 = MagicMock()
    otp_field = MagicMock()
    otp_field.count.return_value = 1
    page1.get_by_role.return_value = otp_field
    with patch.object(c, "prompt", return_value=""):
        result = c._handle_otp(page1)
    assert result is False


def test_handle_otp_submits_code(tmp_path):
    c = _make(tmp_path)
    page1 = MagicMock()
    otp_field = MagicMock()
    otp_field.count.return_value = 1
    page1.get_by_role.return_value = otp_field
    with patch.object(c, "prompt", return_value="123456"), patch.object(_mod, "_wait"):
        result = c._handle_otp(page1)
    assert result is True
    otp_field.fill.assert_called_once_with("123456")


def test_collect_skip_when_otp_cancelled(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()
    page1 = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_login", return_value=page1), \
         patch.object(c, "_navigate_to_reports"), \
         patch.object(c, "_handle_otp", return_value=False), \
         patch.object(c, "log_result") as mock_log:
        c.run()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "skip"


def test_collect_error_when_pdf_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()
    page1 = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_login", return_value=page1), \
         patch.object(c, "_navigate_to_reports"), \
         patch.object(c, "_handle_otp", return_value=True), \
         patch.object(c, "_download_pdf_via_route", return_value=None), \
         patch.object(c, "log_result") as mock_log:
        c.run()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "error"
