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

    def _browser_profile_dir(self) -> Path:
        """ブラウザプロファイル保存先（~/.money-ops-browser/<code>/）OneDrive外に置く"""
        return Path.home() / ".money-ops-browser" / self.code

    def launch_browser(self):
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()

        profile_dir = self._browser_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)
        if any(profile_dir.iterdir()):
            print(f"[{self.name}] ブラウザプロファイル復元: {profile_dir}")

        # persistent context でブラウザ全状態（cookies・IndexedDB・端末登録等）を永続化
        # --use-angle=d3d11 で実機 GPU（DirectX11）を使い Canvas/WebGL フィンガープリントを実機 Chrome と一致させる
        # （デフォルトの SwiftShader はソフトウェアレンダラーのためフィンガープリントが毎回異なり
        #   金融サイトのデバイス認識が通らない）
        self._context = self._playwright.chromium.launch_persistent_context(
            str(profile_dir),
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--use-angle=d3d11",
            ],
            ignore_default_args=["--enable-automation"],
        )
        self._page = self._context.new_page()
        self._restore_session_cookies()
        return self._page

    def _restore_session_cookies(self) -> None:
        """前回ログイン時に保存した storage_state.json から全 cookie を注入する。
        persistent cookie は Chromium profile DB から復元されるが、
        session cookie（expires=-1）はDBに保存されないため明示的に注入する必要がある。
        両方まとめて add_cookies() することで漏れを防ぐ。"""
        state_path = self._browser_profile_dir() / "storage_state.json"
        if not state_path.exists():
            return
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
        cookies = state.get("cookies", [])
        if not cookies:
            return
        self._context.add_cookies(cookies)
        print(f"[{self.name}] cookie {len(cookies)}件を復元しました")

    def close_browser(self) -> None:
        if hasattr(self, "_context"):
            self._context.close()
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
