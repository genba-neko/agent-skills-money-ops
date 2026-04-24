"""楽天証券 特定口座年間取引報告書（PDF + XML）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）

注意:
    ログイン・絵文字認証は人間が手動で行う。
    スクリプト起動後、ブラウザでログインしてください。ログイン完了を自動検出します。
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from money_ops.collector.base import BaseCollector

_SITE_JSON = Path(__file__).parent / "site.json"

from money_ops.utils import extract_filename, wait as _wait

class RakutenCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None, headless: bool | None = None, debug: bool | None = None):
        super().__init__(site_json_path, year, headless=headless, debug=debug)

    # ------------------------------------------------------------------
    # 手動ログイン待機
    # ------------------------------------------------------------------
    def _wait_for_login(self, page) -> None:
        page.goto(self.config["login_url"])
        # ログイン済み確認（URL で判定）
        if "rakuten-sec.co.jp" in page.url and "login" not in page.url.lower():
            btn = page.locator('button[aria-label*="マイメニュー"]')
            if btn.count() > 0:
                print(f"[{self.name}] ログイン済みを検出 → スキップ")
                return
        print(f"[{self.name}] ブラウザでログインしてください（絵文字認証・二段階認証含む）（最大10分）")
        # 2FA中間URLで誤発火しないよう、ダッシュボードのボタン出現を待つ
        page.wait_for_selector('button[aria-label*="マイメニュー"]', timeout=600_000)
        _wait()
        self.dlog(f"URL: {page.url}")
        self.save_html(page, "after_login")

    # ------------------------------------------------------------------
    # 電子書面一覧ページへ移動
    # ------------------------------------------------------------------
    def _navigate_to_report_list(self, page) -> None:
        year = self.config["target_year"]
        print(f"[{self.name}] 確定申告サポート → 取引報告書等(電子書面) へ移動")
        page.get_by_role("button", name="マイメニュー 口座管理・入出金など").click()
        _wait()
        page.get_by_role("link", name="確定申告サポート").click()
        _wait()
        page.get_by_role("link", name=f"{year}年").click()
        _wait()
        page.get_by_role("link", name="取引報告書等(電子書面)").first.click()
        _wait()
        self.dlog(f"URL: {page.url}")
        self.save_html(page, "report_list")

    # ------------------------------------------------------------------
    # 対象年度の行を特定してダウンロード
    # ------------------------------------------------------------------
    def _download_files(self, page) -> list[str]:
        self.prepare_directory()
        year = self.config["target_year"]
        downloaded: list[str] = []

        # 対象年度の行: <tr> の中に <span>{year}</span> を含む行
        year_row = page.locator(f"tr:has(td span:text-is('{year}'))")
        if year_row.count() == 0:
            print(f"[{self.name}] {year}年の行が見つかりません")
            return downloaded

        # ---- XML ダウンロード ----
        xml_button = year_row.get_by_role("button", name="XML保存")
        if xml_button.count() > 0:
            with page.expect_download() as dl_info:
                xml_button.click()
            dl = dl_info.value
            xml_path = self.output_dir / dl.suggested_filename
            dl.save_as(str(xml_path))
            downloaded.append(str(xml_path))
            print(f"[{self.name}] XML 保存: {xml_path}")
            _wait()
        else:
            print(f"[{self.name}] {year}年の XML保存ボタンが見つかりません")

        # ---- PDF ダウンロード ----
        # B0020.aspx が PDF を返すが Chrome の PDF ビューア拡張が先にインターセプト
        # するため response リスナーには HTML ラッパーが届く。
        # context.route() で拡張処理前に PDF バイトを捕捉する。
        pdf_link = year_row.get_by_role("link", name="PDF表示")
        if pdf_link.count() > 0:
            pdf_bytes_holder: list[bytes] = []

            def _route_pdf(route, request) -> None:
                # chrome-extension:// 等は fetch 不可なのでスキップ
                if not request.url.startswith(("http://", "https://")):
                    route.continue_()
                    return
                response = route.fetch()
                ct = response.headers.get("content-type", "")
                if "application/pdf" in ct and response.status == 200:
                    try:
                        # Content-Disposition からオリジナルファイル名を取得
                        cd = response.headers.get("content-disposition", "")
                        fn = extract_filename(cd)
                        if not fn:
                            fn = request.url.rstrip("/").split("/")[-1].split("?")[0]
                        if not fn.lower().endswith(".pdf"):
                            fn = f"{fn}.pdf" if fn else f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_nentori.pdf"
                        pdf_bytes_holder.append((fn, response.body()))
                    except Exception as e:
                        print(f"[{self.name}] PDF body取得失敗: {e}")
                route.fulfill(response=response)

            page.context.route("https://report.rakuten-sec.co.jp/**", _route_pdf)
            try:
                with page.expect_popup() as popup_info:
                    pdf_link.click()
                popup = popup_info.value
                popup.wait_for_load_state("networkidle")
                _wait()
                popup.close()
            finally:
                page.context.unroute("https://report.rakuten-sec.co.jp/**", _route_pdf)

            if pdf_bytes_holder:
                pdf_filename, pdf_bytes = pdf_bytes_holder[0]
                pdf_path = self.output_dir / pdf_filename
                pdf_path.write_bytes(pdf_bytes)
                downloaded.append(str(pdf_path))
                print(f"[{self.name}] PDF 保存: {pdf_path}")
            else:
                print(f"[{self.name}] PDF レスポンスを捕捉できませんでした")
            _wait()
        else:
            print(f"[{self.name}] {year}年の PDF表示リンクが見つかりません")

        return downloaded

    # ------------------------------------------------------------------
    # JSON 変換
    # ------------------------------------------------------------------
    # メイン収集フロー
    # ------------------------------------------------------------------
    def _collect_core(self, page) -> None:
        self._wait_for_login(page)
        self._save_session_state(page)
        self._navigate_to_report_list(page)

        year = self.config["target_year"]
        if page.locator(f"tr:has(td span:text-is('{year}'))").count() == 0:
            self.log_result("skip", [], f"{year}年の取引報告書が存在しません")
            return

        downloaded = self._download_files(page)

        if not downloaded:
            self.log_result("skip", [], "ダウンロード対象ファイルが見つかりませんでした")
            return

        self._convert_xml_to_json(downloaded)
        self.log_result("success", downloaded)

def main() -> None:
    parser = argparse.ArgumentParser(description="楽天証券 年間取引報告書収集")
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="対象年度（未指定時は site.json の target_year を使用）",
    )
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    collector = RakutenCollector(year=args.year, headless=args.headless, debug=args.debug)
    collector.run()

if __name__ == "__main__":
    main()
