"""ウィブル証券 収集スクリプトのユニットテスト（ADB モック）"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import build_collector, load_site_module

_CODE = "webull"
_mod = load_site_module(_CODE)
WebullCollector = _mod.WebullCollector


def _make(tmp_path, year=2025):
    return build_collector(tmp_path, _CODE, WebullCollector, year)


def test_init(tmp_path):
    c = _make(tmp_path)
    assert c.code == _CODE
    assert c.name == "ウィブル証券"


def test_find_adb_serial_found(tmp_path):
    c = _make(tmp_path)
    adb_output = "List of devices attached\n192.168.1.10:5555\tdevice\n"
    with patch.object(_mod, "_adb", return_value=adb_output):
        serial = c._find_adb_serial()
    assert serial == "192.168.1.10:5555"


def test_find_adb_serial_not_found(tmp_path):
    c = _make(tmp_path)
    adb_output = "List of devices attached\n"
    with patch.object(_mod, "_adb", return_value=adb_output), patch.object(_mod.time, "sleep"):
        with pytest.raises(RuntimeError, match="タイムアウト"):
            c._find_adb_serial(max_wait_sec=0)


def test_find_adb_serial_unauthorized(tmp_path):
    c = _make(tmp_path)
    adb_output = "List of devices attached\nabc123\tunauthorized\n"
    with patch.object(_mod, "_adb", return_value=adb_output), patch.object(_mod.time, "sleep"):
        with pytest.raises(RuntimeError, match="タイムアウト"):
            c._find_adb_serial(max_wait_sec=0)


def test_snapshot_combines_dirs(tmp_path):
    c = _make(tmp_path)

    def adb_ls_side(*args):
        if "/sdcard/Documents" in args:
            return "file1.pdf\nfile2.pdf"
        if "/sdcard/Download" in args:
            return "file3.pdf"
        return ""

    with patch.object(_mod, "_adb", side_effect=adb_ls_side):
        result = c._snapshot()

    assert any("file1.pdf" in p for p in result)
    assert any("file3.pdf" in p for p in result)


def test_collect_raises_without_uiautomator2(tmp_path):
    c = _make(tmp_path, year=2025)
    with patch.object(_mod, "_adb", return_value="List of devices attached\nabc\tdevice"), \
         patch.dict("sys.modules", {"uiautomator2": None}):
        with pytest.raises(SystemExit):
            c.collect()
