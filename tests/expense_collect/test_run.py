"""expense-collect run.py の is_collected 単体テスト

path リネーム時の回帰検出のため
data/expenses/<category>/<code>/<year>/raw/*.csv 構造で動作確認。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_RUN_PY = Path(__file__).resolve().parents[2] / "skills" / "expense-collect" / "run.py"
_spec = importlib.util.spec_from_file_location("expense_collect_run", _RUN_PY)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "_PROJECT_ROOT", tmp_path)
    return tmp_path


def _make_raw(root: Path, category: str, code: str, year: int) -> Path:
    p = root / "data" / "expenses" / category / code / str(year) / "raw"
    p.mkdir(parents=True, exist_ok=True)
    return p


def test_is_collected_true_when_csv_exists(isolated_root):
    raw = _make_raw(isolated_root, "securities", "sbi", 2025)
    (raw / "DetailInquiry_20260101.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    assert _mod.is_collected("securities", "sbi", 2025) is True


def test_is_collected_false_when_no_csv(isolated_root):
    raw = _make_raw(isolated_root, "securities", "sbi", 2025)
    (raw / "memo.txt").write_text("nope", encoding="utf-8")
    assert _mod.is_collected("securities", "sbi", 2025) is False


def test_is_collected_false_when_raw_dir_missing(isolated_root):
    assert _mod.is_collected("securities", "sbi", 2025) is False


def test_is_collected_false_when_category_differs(isolated_root):
    raw = _make_raw(isolated_root, "securities", "sbi", 2025)
    (raw / "x.csv").write_text("a", encoding="utf-8")
    assert _mod.is_collected("cards", "sbi", 2025) is False


def test_is_collected_path_structure(isolated_root):
    """data/expenses/<category>/<code>/<year>/raw/*.csv
    構造でなければ True にならない（リネーム時の回帰検出）"""
    # 旧 path (data/expense) に置いても True にならない
    old = isolated_root / "data" / "expense" / "sbi" / "2025" / "raw"
    old.mkdir(parents=True, exist_ok=True)
    (old / "x.csv").write_text("a", encoding="utf-8")
    assert _mod.is_collected("securities", "sbi", 2025) is False
    # 新 path に置けば True
    raw = _make_raw(isolated_root, "securities", "sbi", 2025)
    (raw / "x.csv").write_text("a", encoding="utf-8")
    assert _mod.is_collected("securities", "sbi", 2025) is True
