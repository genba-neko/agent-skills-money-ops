"""共通テストヘルパー"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITES_DIR = PROJECT_ROOT / "skills" / "tax-collect" / "sites"
FIXTURE_XML = PROJECT_ROOT / "tests" / "fixtures" / "teg204_sample.xml"


def load_site_module(site_code: str):
    """site_code の collect.py を importlib でロードして返す"""
    collect_py = SITES_DIR / site_code / "collect.py"
    mod_name = site_code.replace("-", "_") + "_collect"
    spec = importlib.util.spec_from_file_location(mod_name, collect_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_collector(tmp_path: Path, site_code: str, collector_cls, year: int = 2025):
    """tmp_path に一時 site.json を作り collector インスタンスを返す"""
    orig = SITES_DIR / site_code / "site.json"
    config = json.loads(orig.read_text(encoding="utf-8"))
    config["output_dir"] = str(tmp_path / "raw")
    config["target_year"] = year
    tmp_site = tmp_path / "site.json"
    tmp_site.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return collector_cls(site_json_path=tmp_site)
