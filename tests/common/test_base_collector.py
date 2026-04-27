import json
import os
from pathlib import Path

import pytest

from money_ops.collector.base import BaseCollector


SITE_JSON = Path(__file__).resolve().parents[2] / "skills" / "tax-collect" / "sites" / "rakuten" / "site.json"


def test_load_config():
    collector = BaseCollector(SITE_JSON)
    assert collector.code == "rakuten"
    assert collector.name == "楽天証券"


def test_headless_default():
    os.environ.pop("HEADLESS", None)
    collector = BaseCollector(SITE_JSON)
    assert collector.headless is False


def test_headless_env_true():
    os.environ["HEADLESS"] = "true"
    collector = BaseCollector(SITE_JSON)
    assert collector.headless is True
    os.environ.pop("HEADLESS")


def test_prepare_directory(tmp_path, monkeypatch):
    config = json.loads(SITE_JSON.read_text(encoding="utf-8"))
    config["output_dir"] = str(tmp_path / "raw")

    tmp_site = tmp_path / "site.json"
    tmp_site.write_text(json.dumps(config), encoding="utf-8")

    collector = BaseCollector(tmp_site)
    collector.prepare_directory()
    assert collector.output_dir.exists()


def test_collect_core_not_implemented():
    collector = BaseCollector(SITE_JSON)
    with pytest.raises(NotImplementedError):
        collector._collect_core(None)


def _make_site(tmp_path, output_dir_template: str, target_year: int = 2025) -> Path:
    config = json.loads(SITE_JSON.read_text(encoding="utf-8"))
    config["output_dir"] = output_dir_template
    config["target_year"] = target_year
    site = tmp_path / "site.json"
    site.write_text(json.dumps(config), encoding="utf-8")
    return site


def test_output_dir_year_placeholder_with_target_year(tmp_path):
    """site.json target_year で {year} が展開される"""
    site = _make_site(tmp_path, "data/incomes/x/{year}/raw/", target_year=2024)
    collector = BaseCollector(site)
    assert str(collector.output_dir) == str(Path("data/incomes/x/2024/raw"))


def test_output_dir_year_placeholder_with_year_arg(tmp_path):
    """year 引数が target_year を上書きして {year} を展開"""
    site = _make_site(tmp_path, "data/incomes/x/{year}/raw/", target_year=2024)
    collector = BaseCollector(site, year=2026)
    assert collector.config["target_year"] == 2026
    assert str(collector.output_dir) == str(Path("data/incomes/x/2026/raw"))


def test_output_dir_no_placeholder(tmp_path):
    """{year} 含まない output_dir は format 後も同じ"""
    site = _make_site(tmp_path, "data/fixed/path/raw/", target_year=2025)
    collector = BaseCollector(site)
    assert str(collector.output_dir) == str(Path("data/fixed/path/raw"))
