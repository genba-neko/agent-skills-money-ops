"""tax-collect run.py の is_collected 単体テスト

PR #46 で data/income → data/incomes リネーム時、Path 連結形式の
path 修正が漏れて収集済み判定が常に False になる不具合があった。
回帰検出のため is_collected の動作と path 構造を検証する。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_RUN_PY = Path(__file__).resolve().parents[2] / "skills" / "tax-collect" / "run.py"
_spec = importlib.util.spec_from_file_location("tax_collect_run", _RUN_PY)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "_PROJECT_ROOT", tmp_path)
    return tmp_path


def _put_json(root: Path, category: str, code: str, year: int, content: str) -> Path:
    p = root / "data" / "incomes" / category / code / str(year) / "nenkantorihikihokokusho.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_is_collected_true_when_json_exists_with_size(isolated_root):
    _put_json(isolated_root, "securities", "sbi", 2025, '{"x":1}')
    assert _mod.is_collected("securities", "sbi", 2025) is True


def test_is_collected_false_when_json_empty(isolated_root):
    _put_json(isolated_root, "securities", "sbi", 2025, "")
    assert _mod.is_collected("securities", "sbi", 2025) is False


def test_is_collected_false_when_json_missing(isolated_root):
    assert _mod.is_collected("securities", "sbi", 2025) is False


def test_is_collected_false_when_category_differs(isolated_root):
    _put_json(isolated_root, "securities", "sbi", 2025, '{"x":1}')
    assert _mod.is_collected("crowdfunding", "sbi", 2025) is False


def test_is_collected_false_when_year_differs(isolated_root):
    _put_json(isolated_root, "securities", "sbi", 2025, '{"x":1}')
    assert _mod.is_collected("securities", "sbi", 2024) is False


def test_is_collected_path_structure(isolated_root):
    """data/incomes/<category>/<code>/<year>/nenkantorihikihokokusho.json
    でなければ True にならない（リネーム時の回帰検出）"""
    # わざと旧 path (data/income) に配置しても True にならない
    old = isolated_root / "data" / "income" / "securities" / "sbi" / "2025" / "nenkantorihikihokokusho.json"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text('{"x":1}', encoding="utf-8")
    assert _mod.is_collected("securities", "sbi", 2025) is False
    # 新 path に置けば True
    _put_json(isolated_root, "securities", "sbi", 2025, '{"x":1}')
    assert _mod.is_collected("securities", "sbi", 2025) is True
