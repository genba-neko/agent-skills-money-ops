import json
import os
from pathlib import Path

import pytest

from money_ops.collector.base import BaseCollector


SITE_JSON = Path(__file__).parent.parent / "skills" / "tax-collect" / "sites" / "rakuten" / "site.json"


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
