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
    def __init__(
        self,
        site_json_path: str | Path,
        year: int | None = None,
        headless: bool | None = None,
        debug: bool | None = None,
    ):
        self.config = _load_site_config(site_json_path)
        self.code: str = self.config["code"]
        self.name: str = self.config["name"]
        self.output_dir = Path(self.config["output_dir"])
        self.headless: bool = headless if headless is not None else _is_headless()
        self.debug: bool = debug if debug is not None else _is_debug()
        self._debug_seq: int = 0  # HTML採取連番
        if year is not None:
            self.config["target_year"] = year
            self.config["output_dir"] = f"data/income/securities/{self.code}/{year}/raw/"
            self.output_dir = Path(self.config["output_dir"])

    def _debug_dir(self) -> Path:
        d = Path("output") / "debug" / self.code
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _log_access(self, url: str) -> None:
        """debug モード時のみ全ナビゲーションを output/debug/<code>/access.log に追記"""
        if not self.debug:
            return
        try:
            log_path = self._debug_dir() / "access.log"
            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{ts} {url}\n")
        except Exception:
            pass

    def prompt(self, message: str) -> str:
        """ユーザーへの入力要求。将来的に並列収集用 EnvPrompt で差し替え可能。"""
        return input(message)

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
        # 全ページのナビゲーションをアクセスログに記録
        self._context.on("page", self._attach_access_logger)
        self._attach_access_logger(self._page)
        return self._page

    def _attach_access_logger(self, page) -> None:
        page.on("framenavigated", lambda frame: (
            self._log_access(frame.url) if frame == frame.page.main_frame else None
        ))

    def _restore_session_cookies(self) -> None:
        """前回ログイン時に保存した storage_state.json から全 cookie を注入する。
        persistent cookie は Chromium profile DB から復元されるが、
        session cookie（expires=-1）はDBに保存されないため明示的に注入する必要がある。
        両方まとめて add_cookies() することで漏れを防ぐ。"""
        state_path = self._browser_profile_dir() / "storage_state.json"
        if not state_path.exists():
            return
        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[{self.name}] storage_state.json が破損しています（スキップ）: {e}")
            return
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

    def _save_session_state(self, page) -> None:
        """cookie が存在する場合のみ storage_state.json を保存（空書き込みで既存 cookie 喪失を防ぐ）。
        atomic write で書き込み中断時の JSON 破損を防ぐ。"""
        state = page.context.storage_state()
        if not state.get("cookies"):
            self.dlog("storage_state が空のため保存スキップ")
            return
        profile_dir = self._browser_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)
        state_path = profile_dir / "storage_state.json"
        tmp_path = state_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, state_path)
        print(f"[{self.name}] セッション保存: {state_path} ({len(state['cookies'])} cookies)")

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

    def _write_report_json(self, data: dict) -> None:
        """年間取引報告書 JSON を output_dir.parent/nenkantorihikihokokusho.json に保存する。"""
        json_path = self.output_dir.parent / "nenkantorihikihokokusho.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[{self.name}] JSON 保存: {json_path}")

    def _convert_xml_to_json(self, downloaded_files: list[str]) -> None:
        """XML ファイルを TEG204 形式として JSON に変換して保存する（XML配布サイト用）。"""
        from money_ops.converter.xml_to_json import convert_teg204_xml

        year = self.config["target_year"]
        xml_files = [f for f in downloaded_files if f.endswith(".xml")]
        if not xml_files:
            print(f"[{self.name}] XML が見つからないため JSON 変換をスキップします")
            return
        raw_files = [str(Path(f).name) for f in downloaded_files]
        data = convert_teg204_xml(
            xml_path=xml_files[0],
            company=self.name,
            code=self.code,
            year=year,
            raw_files=raw_files,
        )
        self._write_report_json(data)

    def _collect_core(self, page) -> None:
        raise NotImplementedError("_collect_core() をサブクラスで実装してください")

    def run(self) -> None:
        page = self.launch_browser()
        try:
            self._collect_core(page)
        except KeyboardInterrupt:
            print(f"\n[{self.name}] ユーザーによる中断")
            self.log_result("interrupted", [], "ユーザーによる中断")
        except Exception as e:
            print(f"[{self.name}] エラー: {e}")
            self.log_result("error", [], str(e))
            raise
        finally:
            self.close_browser()
