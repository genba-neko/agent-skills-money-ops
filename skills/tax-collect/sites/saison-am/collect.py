"""セゾン投信 特定口座年間取引報告書（PDF）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）
    DEBUG       true/false（デフォルト: false）

注意:
    ログイン・取引パスワード入力は人間が手動で行う。
    スクリプト起動後、ブラウザで mypage 到達まで操作してください。

実測済みポップアップ構造（recorder 確認）:
    page:        セゾン投信 トップ（www.saison-am.co.jp）
    mypage:      会員ページ（app.saison-am.co.jp/mypage）— popup
    trade_page:  取引画面（trade.saison-am.co.jp/webbroker3/Web3App）— popup（中継）
    denshibato:  電子バト 報告書一覧（w37.denshi-bato.webbroker.jp/seciss/denshibato）— popup

PDF 取得方式:
    1. mypage の「報告書閲覧」div クリック → 連鎖 popup（trade → denshibato）
    2. denshibato の <a href="javascript:subPdf('YYYY/12/31','0')"> クリック
    3. download イベント捕捉 → 保存
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from money_ops.collector.base import BaseCollector
from money_ops.utils import wait as _wait

_SITE_JSON = Path(__file__).parent / "site.json"


class SaisonAmCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None, headless: bool | None = None, debug: bool | None = None):
        super().__init__(site_json_path, year, headless=headless, debug=debug)

    def _wait_for_login(self, page) -> object:
        """top → 「ログイン」link クリック → popup app.saison-am.co.jp → ホーム描画完了待ち
        → 「マイページ」ナビクリック → /mypage 遷移。

        recorder + 実機確認:
          - top の「ログイン」link は target="_blank" で popup 開く
          - popup は OAuth 経由で app.saison-am.co.jp/?tab=0（ホーム）に着地
          - ホーム下部ナビに「マイページ」link あり → クリックで /mypage
          - /mypage に「報告書閲覧」div あり
        """
        page.goto(self.config["login_url"])
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)

        with page.expect_popup() as popup_info:
            page.get_by_role("link", name="ログイン").first.click()
        home = popup_info.value
        home.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        self.dlog(f"popup URL (初期): {home.url}")

        print(f"[{self.name}] popup でログインしてください（最大5分）")
        # ログイン完了 = 下部ナビの「マイページ」link が visible
        # （URL 待機ではセッション cookie 残存時に早期通過する可能性あり）
        mypage_nav = home.get_by_role("link", name="マイページ")
        mypage_nav.first.wait_for(state="visible", timeout=300_000)
        _wait(2.0, 3.0)
        self.dlog(f"home URL: {home.url}")
        self.save_html(home, "home")

        # 「マイページ」ナビをクリックして /mypage へ
        print(f"[{self.name}] マイページへ移動")
        mypage_nav.first.click()
        home.wait_for_url("**/mypage**", timeout=30_000)
        _wait(1.5, 2.5)
        # /mypage の「報告書閲覧」描画完了待機
        home.locator("div.bg-white.pointer", has_text="報告書閲覧").first.wait_for(
            state="visible", timeout=30_000
        )
        self.dlog(f"mypage URL: {home.url}")
        self.save_html(home, "mypage")

        self._save_session_state(page)

        return home

    def _open_denshibato_menu(self, mypage) -> object:
        """mypage の「報告書閲覧」div クリック → popup → trade.saison-am 経由で
        denshi-bato/secdoc/newdenshibato（電子交付サービスメニュー）まで到達。

        recorder 確認済み popup 遷移:
          trade.saison-am.co.jp/Web3SZApp（中継・即座に閉じる可能性）
          → trade.saison-am.co.jp/Web3App
          → w37.denshi-bato.webbroker.jp/secdoc/newdenshibato（メニュー画面）

        中継 popup が target 消失で expect_popup/wait_for_url が "Target closed" を投げる
        ため、context.pages を polling して denshi-bato URL の page を探す方式に変更。
        """
        print(f"[{self.name}] 報告書閲覧 → 電子交付メニュー（trade.saison-am 中継のため最大 10分）")
        # trace 解析確定: click → popup 作成（trade.saison-am）→ ~5分後に denshi-bato 遷移
        # Playwright 公式 API（expect_event + wait_for_url）で清書
        with mypage.context.expect_event("page", timeout=60_000) as page_info:
            mypage.locator("div.bg-white.pointer", has_text="報告書閲覧").first.click()
        menu_page = page_info.value
        self.dlog(f"popup 作成 URL: {menu_page.url}")
        # denshi-bato に遷移するまで待機（trade.saison-am 中継 処理時間考慮で 10分）
        menu_page.wait_for_url(lambda u: "denshi-bato.webbroker.jp" in u, timeout=600_000)
        self.dlog(f"denshi-bato 到達: {menu_page.url}")

        menu_page.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        self.dlog(f"denshi-bato メニュー URL (描画完了): {menu_page.url}")
        self.save_html(menu_page, "denshibato_menu")
        return menu_page

    def _open_report_list(self, menu_page) -> object:
        """電子交付メニュー → 「取引残高報告書・年間取引報告書...」link →
        検索条件画面（報告書種類 + 対象年月種別 + 検索）→ list 画面。

        実機 HTML 確認:
          - select[0] 報告書種類: value="3" = 年間取引報告書
          - select[1] 対象年月種別: value="3" = 5年前からの取引（過去分も含む範囲）
            （年間取引報告書の作成日は target_year/12/31 or target_year+1/01/xx の
            どちらかでパターン不定 + 過去年度の報告書も検索可能にするため 5年範囲）
          - 検索 link click → 結果一覧画面
        """
        print(f"[{self.name}] 「年間取引報告書」メニューへ")
        report_link = menu_page.locator("a", has_text="年間取引報告書")
        if report_link.count() == 0:
            self.dlog("「年間取引報告書」link が見つかりません")
            return None
        report_link.first.click()
        menu_page.wait_for_url(lambda u: "seciss/denshibato" in u, timeout=30_000)
        menu_page.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        self.save_html(menu_page, "denshibato_search")

        # 検索条件: 年間取引報告書 + 5年前からの取引（過去分カバー）
        print(f"[{self.name}] 検索条件: 年間取引報告書 / 5年前から")
        selects = menu_page.locator("select")
        selects.nth(0).select_option(value="3")  # 報告書種類: 年間取引報告書
        _wait(0.3, 0.7)
        selects.nth(1).select_option(value="3")  # 対象年月種別: 5年前からの取引
        _wait(0.3, 0.7)

        # 検索 link click（onclick="subInputForm()"）
        menu_page.get_by_role("link", name="検索").click()
        menu_page.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)

        # 結果一覧: subPdf link が描画されるまで待機
        menu_page.locator("a[href*='subPdf']").first.wait_for(state="visible", timeout=15_000)
        self.dlog(f"報告書一覧 URL: {menu_page.url}")
        self.save_html(menu_page, "denshibato_list")
        return menu_page

    def _download_pdf(self, list_page) -> str | None:
        """seciss/denshibato で subPdf JavaScript link クリック → 新 popup B から
        download イベント発火 → context.on("download") で全 page 対象に捕捉。

        recorder 確認済み:
          - <a href="javascript:subPdf('YYYY/12/31','0')"> でリンク
          - クリック → 新規 popup B が開く → popup B が download トリガー
          - suggested_filename = NNNNNNNNNNNNN_YYYYMMDDHHMMSS.pdf

        実装:
          context.expect_event("download") は document されておらず動作不確実。
          確実な context.on("download", handler) で事前登録 → click → polling で待つ。
        """
        # 年間取引報告書の作成日は target_year/12/31 or target_year+1/01/xx
        # （hifumi と同じく 2 パターン試行）
        target_year = self.config["target_year"]
        date_patterns = [f"{target_year}/12", f"{target_year + 1}/01"]
        link = None
        for pat in date_patterns:
            candidate = list_page.locator(f"a[href*=\"subPdf('{pat}\"]")
            if candidate.count() > 0:
                self.dlog(f"subPdf link 発見: pattern={pat}")
                link = candidate
                break
        if link is None:
            self.dlog(f"subPdf link が見つかりません（パターン: {date_patterns}）")
            return None

        # subPdf click → popup B（PDF viewer）開く → URL 取得 → close
        # （Chromium 内蔵 PDF viewer は download イベント発火しないため
        #   popup URL を取得して page.request.get で直接 fetch する paypay 方式）
        with list_page.expect_popup(timeout=30_000) as popup_info:
            link.first.click()
        pdf_popup = popup_info.value
        try:
            pdf_popup.wait_for_load_state("domcontentloaded", timeout=30_000)
        except Exception as e:
            self.dlog(f"PDF popup load 待機失敗（URL は取れる可能性あり）: {e}")
        pdf_url = pdf_popup.url
        self.dlog(f"PDF URL: {pdf_url}")
        try:
            pdf_popup.close()
        except Exception:
            pass

        if "denshibato" not in pdf_url or "SERCHPDF" not in pdf_url:
            self.dlog(f"PDF URL が想定外: {pdf_url}")
            return None

        # request.get で PDF bytes 直接取得（context cookie 共有）
        response = list_page.request.get(pdf_url)
        pdf_bytes = response.body()
        if not pdf_bytes or pdf_bytes[:4] != b"%PDF":
            self.dlog(f"PDF でないレスポンス: {len(pdf_bytes)} bytes, "
                      f"CT={response.headers.get('content-type', '?')}")
            return None

        self.prepare_directory()
        filename = f"{target_year}_saison-am_nentori.pdf"
        pdf_path = self.output_dir / filename
        pdf_path.write_bytes(pdf_bytes)
        if not self.verify_pdf(pdf_path):
            return None
        print(f"[{self.name}] PDF 保存: {pdf_path}")
        return str(pdf_path)

    def _collect_core(self, page) -> None:
        mypage = self._wait_for_login(page)
        menu_page = self._open_denshibato_menu(mypage)
        list_page = self._open_report_list(menu_page)
        if list_page is None:
            self.log_result("error", [], "報告書一覧画面への遷移失敗")
            return

        pdf_path = self._download_pdf(list_page)
        if pdf_path is None:
            self.log_result("error", [], "PDF 取得失敗")
            return

        self._queue_pdf_to_json(pdf_path, [str(Path(pdf_path).name)])
        self.log_result("success", [pdf_path])


def main() -> None:
    parser = argparse.ArgumentParser(description="セゾン投信 特定口座年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None, help="対象年度（例: 2025）")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    collector = SaisonAmCollector(year=args.year, headless=args.headless, debug=args.debug)
    sys.exit(collector.run())


if __name__ == "__main__":
    main()
