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
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from money_ops.converter.pdf_to_json import convert_pdf_to_json

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


class WebullCollector:
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None):
        with open(site_json_path, encoding="utf-8") as f:
            self.config = json.load(f)
        self.name: str = self.config["name"]
        self.code: str = self.config["code"]
        if year is not None:
            self.config["target_year"] = year
            self.config["output_dir"] = f"data/income/securities/webull/{year}/raw/"
        self.output_dir = _PROJECT_ROOT / self.config["output_dir"]

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

        # 帳票タブが見つからない場合は認証が必要 → 手動ログイン待ち
        hyohyo_tab = d(resourceId=f"{_PACKAGE}:id/tabTitle", text="帳票")
        if not hyohyo_tab.exists:
            print(f"[{self.name}] 認証が必要です。アプリでログインして帳票タブが表示されたら Enter を押してください")
            input("Enter: ")
            _wait(1.0)
            hyohyo_tab = d(resourceId=f"{_PACKAGE}:id/tabTitle", text="帳票")
            if not hyohyo_tab.exists:
                raise RuntimeError(f"[{self.name}] 帳票タブが見つかりません")

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

    def _find_adb_serial(self) -> str:
        """adb devices から接続済みデバイスのシリアルを返す。見つからなければ例外。"""
        out = _adb("devices")
        for line in out.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) == 2 and parts[1] == "device":
                return parts[0]
        raise RuntimeError(
            "ADB デバイスが見つかりません。\n"
            "先に以下を実行してください（ポートはワイヤレスデバッグ画面で確認）:\n"
            "  adb connect <AndroidのIP>:<ポート番号>"
        )

    def collect(self, serial: str | None = None) -> None:
        try:
            import uiautomator2 as u2
        except ImportError:
            print(f"[{self.name}] uiautomator2 未インストール: pip install uiautomator2")
            sys.exit(1)

        target_year = self.config.get("target_year")
        if target_year is None:
            raise ValueError("target_year が設定されていません")

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
                print(f"[{self.name}] {_TARGET_DOC} ({target_year}) が見つかりません")
                return

            # WebView 読み込み待ち
            _wait(3.0)
            webview = d(resourceId=f"{_PACKAGE}:id/webview")
            if not webview.wait(timeout=15):
                print(f"[{self.name}] WebView タイムアウト")
                return
            _wait(2.0)

            # ダウンロードボタン（r2_menu_icon）
            dl_btn = d(resourceId=f"{_PACKAGE}:id/r2_menu_icon")
            if not dl_btn.exists:
                print(f"[{self.name}] ダウンロードボタンが見つかりません")
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
                print(f"[{self.name}] ダウンロードファイルが見つかりません")
                return
            if len(new_files) > 1:
                print(f"[{self.name}] 警告: 複数の新規ファイル: {new_files}")

            remote_path = next(iter(new_files))

            self.output_dir.mkdir(parents=True, exist_ok=True)
            local_path = self.output_dir / f"{target_year}_webull_nentori.pdf"

            print(f"[{self.name}] adb pull: {remote_path} → {local_path}")
            _adb("pull", remote_path, str(local_path))

            if not local_path.exists() or local_path.stat().st_size == 0:
                print(f"[{self.name}] pull 失敗")
                return

            if local_path.read_bytes()[:4] != b"%PDF":
                print(f"[{self.name}] PDF 検証失敗")
                local_path.unlink(missing_ok=True)
                return

            print(f"[{self.name}] PDF 保存: {local_path}")

            try:
                data = convert_pdf_to_json(
                    pdf_path=str(local_path),
                    company=self.name,
                    code=self.code,
                    year=target_year,
                    raw_files=[local_path.name],
                )
                json_path = self.output_dir.parent / "nenkantorihikihokokusho.json"
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"[{self.name}] JSON 保存: {json_path}")
            except Exception as e:
                print(f"[{self.name}] JSON 変換スキップ: {e}")

            print(f"[{self.name}] 完了")

        finally:
            _adb("shell", "am", "force-stop", _PACKAGE)
            print(f"[{self.name}] アプリ終了")


def main() -> None:
    parser = argparse.ArgumentParser(description="ウィブル証券 特定口座年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None, help="対象年度（例: 2025）")
    parser.add_argument("--serial", default=None, help="ADB デバイスシリアル（省略時: adb devices から自動取得）")
    args = parser.parse_args()
    collector = WebullCollector(year=args.year)
    collector.collect(serial=args.serial)


if __name__ == "__main__":
    main()
