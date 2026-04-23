import json
import os
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass


def _load_site_config(site_json_path: str | Path) -> dict:
    with open(site_json_path, encoding="utf-8") as f:
        return json.load(f)


def _is_headless() -> bool:
    return os.environ.get("HEADLESS", "false").lower() == "true"


def _is_debug() -> bool:
    return os.environ.get("DEBUG", "false").lower() == "true"


class BaseCollector:
    def __init__(self, site_json_path: str | Path):
        self.config = _load_site_config(site_json_path)
        self.code: str = self.config["code"]
        self.name: str = self.config["name"]
        self.output_dir = Path(self.config["output_dir"])
        self.headless: bool = _is_headless()
        self.debug: bool = _is_debug()
        self._debug_seq: int = 0  # HTML採取連番

    def _debug_dir(self) -> Path:
        d = Path("output") / "debug" / self.code
        d.mkdir(parents=True, exist_ok=True)
        return d

    def dlog(self, message: str) -> None:
        """DEBUG=true のときだけ出力する詳細ログ"""
        if self.debug:
            print(f"[{self.name}][DEBUG] {message}")

    def save_html(self, page_or_frame, label: str) -> None:
        """DEBUG=true のとき page/frame の HTML を output/debug/<code>/<seq>_<label>.html に保存
        page_or_frame: Playwright の Page または Frame オブジェクト"""
        if not self.debug:
            return
        self._debug_seq += 1
        filename = f"{self._debug_seq:02d}_{label}.html"
        path = self._debug_dir() / filename
        try:
            html = page_or_frame.content()
            path.write_text(html, encoding="utf-8")
            print(f"[{self.name}][DEBUG] HTML保存: {path}")
        except Exception as e:
            print(f"[{self.name}][DEBUG] HTML保存失敗({label}): {e}")

    def save_response_html(self, body: bytes, label: str) -> None:
        """DEBUG=true のとき レスポンスボディ（bytes）を HTML として保存"""
        if not self.debug:
            return
        self._debug_seq += 1
        filename = f"{self._debug_seq:02d}_{label}.html"
        path = self._debug_dir() / filename
        try:
            path.write_bytes(body)
            print(f"[{self.name}][DEBUG] レスポンス保存: {path}")
        except Exception as e:
            print(f"[{self.name}][DEBUG] レスポンス保存失敗({label}): {e}")

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

    def verify_pdf(self, pdf_path: str | Path) -> bool:
        """PDF ファイルの存在・非空・マジックバイト（%PDF）を検証する。"""
        path = Path(pdf_path)
        if not path.exists():
            print(f"[{self.name}] PDF が存在しません: {path}")
            return False
        if path.stat().st_size == 0:
            print(f"[{self.name}] PDF が空ファイルです: {path}")
            return False
        with open(path, "rb") as f:
            header = f.read(4)
        if header != b"%PDF":
            print(f"[{self.name}] PDF マジックバイト不正: {header!r} ({path})")
            return False
        return True

    def collect(self) -> None:
        raise NotImplementedError("collect() をサブクラスで実装してください")
