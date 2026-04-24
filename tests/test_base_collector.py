import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

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


def test_prompt_tty_uses_input():
    collector = BaseCollector(SITE_JSON)
    with patch("sys.stdin") as mock_stdin, patch("builtins.input", return_value="ok") as mock_input:
        mock_stdin.isatty.return_value = True
        result = collector.prompt("test: ")
    mock_input.assert_called_once_with("test: ")
    assert result == "ok"


def test_prompt_non_tty_uses_signal_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    collector = BaseCollector(SITE_JSON)

    def _create_signal():
        time.sleep(0.3)
        (tmp_path / f".signal_{collector.code}").write_text("", encoding="utf-8")

    t = threading.Thread(target=_create_signal)
    t.start()

    with patch("sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = False
        result = collector.prompt("ログイン完了後Enter: ")

    t.join()
    assert result == ""
    assert not (tmp_path / f".waiting_{collector.code}").exists()
    assert not (tmp_path / f".signal_{collector.code}").exists()
