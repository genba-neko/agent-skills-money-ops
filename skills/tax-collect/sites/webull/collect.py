"""ウィブル証券 特定口座年間取引報告書 uiautomator2 収集スクリプト

使い方:
    python collect.py [--year YYYY]

前提:
    - ADB でデバイスが接続済み（adb devices で確認）
    - ウィブルアプリがログイン済み
    - uiautomator2 インストール済み: pip install uiautomator2

収集フロー:
    1. アプリ起動
    2. 取引画面 → 履歴タブ
    3. 「特定口座年間取引報告書」（対象年）の行をタップ → WebView で PDF 表示
    4. r2_menu_icon タップ → /sdcard/Documents/ に PDF 保存
    5. adb pull でローカルへ転送

UI 構造（uiautomator dump 確認済み）:
    帳票タブ（TabTitle="帳票"）に最近の書類のみ表示。
    履歴タブ（TabTitle="履歴"）に全書類が時系列で表示される。
    各行: tv_name（書類名）+ tv_date（日付。年間報告書は "2025" のみ）
    行タップ → WebView（resource-id=webview）で PDF 表示。
    r2_menu_icon タップ → /sdcard/Documents/{date}.pdf に保存。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from money_ops.collector.base import BaseCollector

_SITE_JSON = Path(__file__).parent / "site.json"
_PACKAGE = "org.dayup.stocks.jp"
_DOCS_DIR = "/sdcard/Documents"
_TARGET_DOC = "特定口座年間取引報告書"

_ADB_FALLBACK = Path(os.environ["ADB_PATH"]) if os.environ.get("ADB_PATH") else None

def _adb(*args: str) -> str:
    cmd = ["adb", *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError:
        if _ADB_FALLBACK is not None and _ADB_FALLBACK.exists():
            cmd[0] = str(_ADB_FALLBACK)
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
        else:
            raise RuntimeError("adb が見つかりません。PATH に追加するか ADB_PATH 環境変数を設定してください")
    return result.stdout.strip()

def _wait(t: float = 1.5) -> None:
    time.sleep(t)

class WebullCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None, headless: bool | None = None, debug: bool | None = None):
        super().__init__(site_json_path, year, headless=headless, debug=debug)

    def _list_dir(self, remote_dir: str) -> set[str]:
        out = _adb("shell", "ls", remote_dir)
        return {f"{remote_dir}/{f.strip()}" for f in out.splitlines() if f.strip()}

    def _snapshot(self) -> set[str]:
        """ダウンロード先候補ディレクトリの全ファイルパスを返す。"""
        result: set[str] = set()
        for d in [_DOCS_DIR, "/sdcard/Download"]:
            result |= self._list_dir(d)
        return result

    def _launch_app(self, d) -> None:
        _adb(
            "shell", "monkey",
            "-p", _PACKAGE,
            "-c", "android.intent.category.LAUNCHER",
            "1",
        )
        _wait(3.0)

    def _navigate_to_history(self, d) -> None:
        # 取引ボタン（ボトムバー中央: view_bottom_item）
        trade_btn = d(resourceId=f"{_PACKAGE}:id/view_bottom_item")
        if trade_btn.exists:
            trade_btn.click()
            _wait(2.0)

        # 帳票タブが見つからない場合は認証が必要 → 出現を最大10分待機
        hyohyo_tab = d(resourceId=f"{_PACKAGE}:id/tabTitle", text="帳票")
        if not hyohyo_tab.exists:
            print(f"[{self.name}] 認証が必要です。アプリでログインしてください（帳票タブ出現まで最大10分待機）")
            if not hyohyo_tab.wait(timeout=600):
                raise RuntimeError(f"[{self.name}] 帳票タブが見つかりません（10分タイムアウト）")

        # 帳票タブ（タブバーの「履歴」ではなく「帳票」）
        hyohyo_tab.click()
        _wait(2.0)

        # 帳票画面内の「履歴記録」行（全書類一覧へ）
        rekishi = d(resourceId=f"{_PACKAGE}:id/tv_date", text="履歴記録")
        if not rekishi.exists:
            raise RuntimeError(f"[{self.name}] 履歴記録が見つかりません")
        rekishi.click()
        _wait(2.0)

    def _find_and_tap_doc(self, d, target_year: int) -> bool:
        """スクロールしながら対象ドキュメント行を探してタップ。見つかったら True。

        tv_date が年度のみ（例: "2025"）の書類は特定口座年間取引報告書だけなので、
        following-sibling で year_str との完全一致で絞り込む。
        """
        year_str = str(target_year)
        xpath = (
            f'//*[@resource-id="{_PACKAGE}:id/tv_name" and @text="{_TARGET_DOC}"]'
            f'[following-sibling::*[@resource-id="{_PACKAGE}:id/tv_date"'
            f' and @text="{year_str}"]]'
        )
        for attempt in range(15):
            els = d.xpath(xpath).all()
            if els:
                els[0].click()
                return True
            print(f"[{self.name}] スクロール中... ({attempt + 1}/15)")
            d.swipe(540, 1500, 540, 600, duration=0.4)
            _wait(1.0)
        return False

    def _find_adb_serial(self, max_wait_sec: int = 30) -> str:
        """adb server 起動 → USB接続デバイス検出をリトライ。
        `device`(ready) を検出したら serial 返却。
        `unauthorized`(USBデバッグ承認待ち) / `offline` 中は進捗ログ出してリトライ。
        max_wait_sec 経過で例外。
        """
        _adb("start-server")
        deadline = time.time() + max_wait_sec
        last_log = ""
        while time.time() < deadline:
            out = _adb("devices")
            states: dict[str, str] = {}
            for line in out.splitlines()[1:]:
                parts = line.strip().split()
                if len(parts) == 2:
                    states[parts[0]] = parts[1]
            for serial, state in states.items():
                if state == "device":
                    print(f"[{self.name}] ADB デバイス検出: {serial}")
                    return serial
            if any(s == "unauthorized" for s in states.values()):
                msg = "USBデバッグ承認待ち（端末で許可ダイアログをタップ）"
            elif any(s == "offline" for s in states.values()):
                msg = "adb offline → 再接続待ち"
            else:
                msg = "ADB デバイス未検出 → USB接続待ち"
            if msg != last_log:
                print(f"[{self.name}] {msg}")
                last_log = msg
            time.sleep(2.0)
        raise RuntimeError(
            f"[{self.name}] ADB デバイス検出タイムアウト（{max_wait_sec}秒）。\n"
            "確認: USBケーブル接続 / 端末で USBデバッグ 有効 / 端末ロック解除"
        )

    def collect(self, serial: str | None = None) -> None:
        try:
            import uiautomator2 as u2
        except ImportError:
            self.log_result("error", [], "uiautomator2 未インストール: pip install uiautomator2")
            sys.exit(1)

        target_year = self.config.get("target_year")
        if target_year is None:
            self.log_result("error", [], "target_year が設定されていません")
            raise ValueError("target_year が設定されていません")

        try:
            if serial is None:
                serial = self._find_adb_serial()

            d = u2.connect(serial)
            print(f"[{self.name}] デバイス接続: {d.serial}")

            try:
                self._launch_app(d)
                self._navigate_to_history(d)

                files_before = self._snapshot()

                print(f"[{self.name}] {_TARGET_DOC} ({target_year}) を検索中...")
                if not self._find_and_tap_doc(d, target_year):
                    self.log_result("skip", [], f"{_TARGET_DOC} ({target_year}) が見つかりません")
                    return

                # WebView 読み込み待ち
                _wait(3.0)
                webview = d(resourceId=f"{_PACKAGE}:id/webview")
                if not webview.wait(timeout=15):
                    self.log_result("skip", [], "WebView タイムアウト")
                    return
                _wait(2.0)

                # ダウンロードボタン（r2_menu_icon）
                dl_btn = d(resourceId=f"{_PACKAGE}:id/r2_menu_icon")
                if not dl_btn.exists:
                    self.log_result("skip", [], "ダウンロードボタンが見つかりません")
                    return
                dl_btn.click()

                # フォルダ権限ダイアログ（初回のみ・2段階）: 最大10秒待ちながら検出→タップ
                for _ in range(10):
                    _wait(1.0)
                    for btn_text in ["このフォルダを使用", "許可", "ALLOW", "Allow"]:
                        btn = d(text=btn_text)
                        if btn.exists:
                            print(f"[{self.name}] 権限ダイアログ「{btn_text}」→ タップ")
                            btn.click()
                            _wait(0.5)

                _wait(4.0)

                # 新規ファイル特定（Documents と Download 両方チェック）
                new_files = self._snapshot() - files_before
                print(f"[{self.name}] 新規ファイル: {new_files or '(なし)'}")

                if not new_files:
                    self.log_result("skip", [], "ダウンロードファイルが見つかりません")
                    return
                if len(new_files) > 1:
                    print(f"[{self.name}] 警告: 複数の新規ファイル: {new_files}")

                remote_path = next(iter(new_files))

                self.output_dir.mkdir(parents=True, exist_ok=True)
                local_path = self.output_dir / f"{target_year}_webull_nentori.pdf"

                print(f"[{self.name}] adb pull: {remote_path} → {local_path}")
                _adb("pull", remote_path, str(local_path))

                if not local_path.exists() or local_path.stat().st_size == 0:
                    self.log_result("error", [], "adb pull 失敗")
                    return

                if local_path.read_bytes()[:4] != b"%PDF":
                    self.log_result("error", [], "PDF 検証失敗")
                    local_path.unlink(missing_ok=True)
                    return

                print(f"[{self.name}] PDF 保存: {local_path}")

                self._queue_pdf_to_json(str(local_path), [local_path.name])
                self.log_result("success", [str(local_path)])

            finally:
                _adb("shell", "am", "force-stop", _PACKAGE)
                print(f"[{self.name}] アプリ終了")

        except Exception as e:
            print(f"[{self.name}] エラー: {e}")
            self.log_result("error", [], str(e))
            raise

def main() -> None:
    parser = argparse.ArgumentParser(description="ウィブル証券 特定口座年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None, help="対象年度（例: 2025）")
    parser.add_argument("--serial", default=None, help="ADB デバイスシリアル（省略時: adb devices から自動取得）")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    collector = WebullCollector(year=args.year, headless=args.headless, debug=args.debug)
    collector.collect(serial=args.serial)

if __name__ == "__main__":
    main()
