import json
import os
from datetime import datetime
from pathlib import Path


def _load_site_config(site_json_path: str | Path) -> dict:
    with open(site_json_path, encoding="utf-8") as f:
        return json.load(f)


def _is_headless() -> bool:
    return os.environ.get("HEADLESS", "false").lower() == "true"


class BaseCollector:
    def __init__(self, site_json_path: str | Path):
        self.config = _load_site_config(site_json_path)
        self.code: str = self.config["code"]
        self.name: str = self.config["name"]
        self.output_dir = Path(self.config["output_dir"])
        self.headless: bool = _is_headless()

    def prepare_directory(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def launch_browser(self):
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page()
        return self._page

    def close_browser(self) -> None:
        if hasattr(self, "_browser"):
            self._browser.close()
        if hasattr(self, "_playwright"):
            self._playwright.stop()

    def log_result(self, status: str, files: list[str], message: str = "") -> None:
        log_dir = Path("output") / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_path = log_dir / f"{self.code}.json"
        entry = {
            "code": self.code,
            "name": self.name,
            "status": status,
            "files": files,
            "message": message,
            "collected_at": datetime.now().isoformat(),
        }

        history = []
        if log_path.exists():
            with open(log_path, encoding="utf-8") as f:
                history = json.load(f)

        history.append(entry)

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        print(f"[{self.name}] {status}: {message or ', '.join(files)}")

    def collect(self) -> None:
        raise NotImplementedError("collect() をサブクラスで実装してください")
