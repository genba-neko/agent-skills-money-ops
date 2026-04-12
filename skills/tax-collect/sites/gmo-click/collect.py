"""GMOクリック証券 特定口座年間取引報告書（PDF + XML）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）

注意:
    ログインは人間が手動で行う。
    スクリプト起動後、ブラウザでトップ画面まで到達してから Enter を押すこと。
    電子書類閲覧へのアクセス時にアプリ2FA が発生する。
    2FAコードを入力したら Enter を押すこと（認証ボタンはスクリプトが押す）。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

_RE_FILENAME = re.compile(r'filename[^;=\n]*=([^;\n]*)')

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from money_ops.collector.base import BaseCollector
from money_ops.converter.xml_to_json import convert_teg204_xml

_SITE_JSON = Path(__file__).parent / "site.json"
_LOGIN_URL = "https://kabu.click-sec.com/sec2/mypage/top.do"


def _wait(lo: float = 1.0, hi: float = 3.0) -> None:
    time.sleep(random.uniform(lo, hi))


def _year_month_patterns(target_year: int) -> list[str]:
    """発行年月の候補: 対象年12月 or 翌年1月"""
    return [f"{target_year}/12", f"{target_year + 1}/01"]


class GMOClickCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None):
        super().__init__(site_json_path)
        if year is not None:
            self.config["target_year"] = year
            self.config["output_dir"] = f"data/income/securities/gmo-click/{year}/raw/"
            self.output_dir = Path(self.config["output_dir"])

    def _wait_for_login(self, page) -> None:
        page.goto(_LOGIN_URL)
        print(f"[{self.name}] ブラウザでログインしてください")
        input("ログイン完了後 Enter を押してください: ")
        _wait()
        self._session = page
        # セッション状態（cookie含む）を保存
        page.context.storage_state(path=str(self._browser_profile_dir() / "storage_state.json"))
        print(f"[{self.name}] セッション状態を保存しました")

    def _navigate_to_report_popup(self) -> object:
        """電子書類閲覧ポップアップを開いて返す"""
        session = self._session
        # ログイン直後の通知を閉じる（表示される場合のみ）
        close_btn = session.get_by_role("link", name="閉じる")
        if close_btn.count() > 0:
            close_btn.click()
            _wait()
        print(f"[{self.name}] 精算表 → 電子書類閲覧 → 書類閲覧リンク へ移動")
        session.locator("a").filter(has_text="精算表").first.click()
        _wait()
        session.get_by_role("link", name="電子書類閲覧").click()
        _wait()
        with session.expect_popup() as popup_info:
            session.locator("#stockReportLink").click()
            _wait(2.0, 3.0)
            # 2FAモーダルが表示された場合のみ処理（セッション状態によって有無が変わる）
            if session.locator("#appTwoStepVerificationCode").is_visible():
                print(f"[{self.name}] アプリ2FAコードを入力してください（認証ボタンはスクリプトが押します）")
                input("コード入力後 Enter を押してください: ")
                session.locator("#btnConfirm").click()
        popup = popup_info.value
        popup.wait_for_load_state("domcontentloaded")
        # e-shishobako Angular SPA: SSO後のルーティング完了を待つ（SBIと同方式）
        popup.wait_for_url("**/dp_apl/usr/**", timeout=30000)
        popup.wait_for_selector("input, button", timeout=30000)
        _wait(2.0, 3.0)
        return popup

    def _find_report_row_button(self, popup, target_year: int):
        """target_year に対応する年月ボタンを返す（なければ None）
        get_by_role("button") で role="button" の div 要素も対象にする（SBIと同方式）"""
        for ym in _year_month_patterns(target_year):
            btn = popup.get_by_role("button").filter(has_text=ym)
            if btn.count() > 0:
                return btn.first
        return None

    def _download_pdf_via_route(self, popup, output_dir: Path, fallback_name: str) -> str | None:
        """context.route() で DPAW010501020 の PDF レスポンスを捕捉して保存
        PDF ボタンクリック → blob URL ポップアップが開く → 閉じてから unroute（SBIと同方式）"""
        pdf_btn = popup.locator("button, a").filter(has_text="PDFファイル")
        if pdf_btn.count() == 0:
            print(f"[{self.name}] PDF ボタンが見つかりません")
            return None

        pdf_bytes_holder: list[tuple[str, bytes]] = []

        def _capture_pdf(route, _request) -> None:
            response = route.fetch()
            body = response.body()
            if body[:4] == b"%PDF":
                cd = response.headers.get("content-disposition", "")
                m = _RE_FILENAME.search(cd)
                filename = m.group(1).strip().strip('"\'') if m else fallback_name
                pdf_bytes_holder.append((filename, body))
            route.fulfill(response=response)

        popup.context.route("**/DPAW010501020", _capture_pdf)
        try:
            with popup.expect_popup() as pdf_popup_info:
                pdf_btn.first.click()
            pdf_popup = pdf_popup_info.value
            pdf_popup.wait_for_load_state("domcontentloaded")
            _wait()
            pdf_popup.close()
        finally:
            popup.context.unroute("**/DPAW010501020", _capture_pdf)

        if not pdf_bytes_holder:
            print(f"[{self.name}] PDF レスポンスを捕捉できませんでした")
            return None

        filename, pdf_bytes = pdf_bytes_holder[0]
        pdf_path = output_dir / filename
        pdf_path.write_bytes(pdf_bytes)
        print(f"[{self.name}] PDF 保存: {pdf_path}")
        return str(pdf_path)

    def _download_files(self, popup) -> list[str]:
        self.prepare_directory()
        year = self.config["target_year"]
        downloaded: list[str] = []

        # キーワード絞り込み（Angular SPA なのでクライアントサイドフィルタ）
        search_box = popup.get_by_role("textbox", name="キーワードで件名検索")
        search_box.fill("特定口座年間取引報告書")
        search_box.press("Enter")
        _wait(2.0, 3.0)

        row_btn = self._find_report_row_button(popup, year)
        if row_btn is None:
            print(f"[{self.name}] {year}年度の報告書が見つかりません")
            return downloaded
        print(f"[{self.name}] 報告書行をクリック（詳細を開く）")
        row_btn.scroll_into_view_if_needed()
        row_btn.click()
        # PDF ダウンロードボタンが visible になるまで待機（SBIと同方式）
        popup.locator("button, a").filter(has_text="PDFファイル").first.wait_for(
            state="visible", timeout=15000
        )
        _wait()

        # XML（button または a 要素）
        xml_btn = popup.locator("button, a").filter(has_text="xmlデータ")
        if xml_btn.count() == 0:
            xml_btn = popup.locator("button, a").filter(has_text="XMLデータ")
        if xml_btn.count() > 0:
            with popup.expect_download() as dl_info:
                xml_btn.click()
            dl = dl_info.value
            xml_path = self.output_dir / dl.suggested_filename
            dl.save_as(str(xml_path))
            downloaded.append(str(xml_path))
            print(f"[{self.name}] XML 保存: {xml_path}")
            _wait()
        else:
            print(f"[{self.name}] XML ボタンが見つかりません")

        # PDF（e-shishobako DPAW010501020 ルート捕捉。SBIと完全同方式）
        pdf_path = self._download_pdf_via_route(
            popup, self.output_dir, f"{year}_nentori.pdf"
        )
        if pdf_path:
            downloaded.append(pdf_path)
            _wait()

        return downloaded

    def _convert_to_json(self, downloaded_files: list[str]) -> None:
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
        json_path = self.output_dir.parent / "nenkantorihikihokokusho.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[{self.name}] JSON 保存: {json_path}")

    def collect(self) -> None:
        page = self.launch_browser()
        try:
            self._wait_for_login(page)
            popup = self._navigate_to_report_popup()

            downloaded = self._download_files(popup)
            if not downloaded:
                self.log_result("skip", [], "ダウンロード対象ファイルが見つかりませんでした")
                return

            self._convert_to_json(downloaded)
            self.log_result("success", downloaded)

        except KeyboardInterrupt:
            print(f"\n[{self.name}] ユーザーによる中断")
            self.log_result("interrupted", [], "ユーザーによる中断")
        except Exception as e:
            print(f"[{self.name}] エラー: {e}")
            self.log_result("error", [], str(e))
            raise
        finally:
            self.close_browser()


def main() -> None:
    parser = argparse.ArgumentParser(description="GMOクリック証券 年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()
    collector = GMOClickCollector(year=args.year)
    collector.collect()


if __name__ == "__main__":
    main()
