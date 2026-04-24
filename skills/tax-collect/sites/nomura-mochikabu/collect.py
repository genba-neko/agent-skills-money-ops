"""野村證券持株会 配当金等支払通知書（PDF）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）
    DEBUG       true/false（デフォルト: false）

注意:
    ログイン・2FA・ポップアップ処理は人間が手動で行う。
    スクリプト起動後、ブラウザでログインしてトップ画面到達後 Enter を押すこと。

収集対象:
    配当金等支払通知書（Web交付）
    chohyoType=3 で絞り込み。発行日が {target_year}/12 または {target_year+1}/01 の書類を対象とする。

PDF取得方式（T-13方式: context.request 直接フェッチ）:
    ポップアップを経由しない。
    1. report_link の href から weachouhyou.jsp?index=X の URL を取得
    2. page.context.request.get(jsp_url) で HTML を直接フェッチ（セッション cookie 自動付与）
    3. HTML の hidden input から POST パラメータを取得
    4. page.context.request.post(ChouhyouDisplayPost.do, form=params) で PDF を直接フェッチ

    Chrome 内蔵 PDF ビューアは CDP ネットワーク層をバイパスするため、
    route() / iframe / expect_download() はいずれも機能しない（T-13 根本原因）。
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path

from money_ops.collector.base import BaseCollector

_SITE_JSON = Path(__file__).parent / "site.json"
_LOGIN_URL = "https://www.e-plan.nomura.co.jp/login/index.html"
_WEB_KOFU_URL = "https://www.e-plan.nomura.co.jp/mocikabu/script/WEAW1200.jsp"
_PDF_POST_URL = "https://www.e-plan.nomura.co.jp/cms/ChouhyouDisplayPost.do"

from money_ops.utils import extract_filename, wait as _wait

def _year_month_patterns(target_year: int) -> list[str]:
    """発行年月の候補: 対象年12月 or 翌年1月"""
    return [f"{target_year}年12月", f"{target_year + 1}年01月"]

class NomuraMochikabuCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None):
        super().__init__(site_json_path, year)

    def _wait_for_login(self, page) -> None:
        page.goto(_LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")
        print(f"[{self.name}] ブラウザでログインしてください（2FA・ポップアップ処理含む）")
        input("トップ画面で操作可能になったら Enter を押してください: ")
        _wait()
        self.dlog(f"login done, URL: {page.url}")
        self.save_html(page, "after_login")

    def _navigate_to_list(self, page):
        """Web交付ページへ移動し、配当金等支払通知書フィルタを適用した書類一覧を返す"""
        print(f"[{self.name}] Web交付ページへ移動")
        page.goto(_WEB_KOFU_URL)
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        self.save_html(page, "weaw1200_before_filter")

        # chohyoType=3（配当金等支払通知書）を選択 → onchange で自動フォームサブミット
        page.locator("#chohyoType").select_option("3")
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        self.save_html(page, "weaw1200_after_filter")

    def _find_report_link(self, page, target_year: int):
        """発行年月で対象書類リンクを返す。見つからなければ None。

        書類一覧の構造:
          <dl class="e_info_list">
            <dt class="e_info_date">2025年12月26日</dt>
            <dd>
              <a href="/mocikabu/script/weachouhyou.jsp?index=X">配当金等支払通知書</a>
            </dd>
          </dl>
        発行日が {target_year}年12月 または {target_year+1}年01月 の行を選ぶ。
        """
        for ym in _year_month_patterns(target_year):
            # dt テキストが ym を含む dl の中の a タグ
            link = page.locator(
                f"dl.e_info_list:has(dt.e_info_date:has-text('{ym}')) a"
            )
            if link.count() > 0:
                self.dlog(f"対象書類リンク発見: ym={ym}, count={link.count()}")
                return link.first
        return None

    def _parse_hidden_inputs(self, html: str) -> dict[str, str]:
        """HTML から <input type="hidden"> の name/value を抽出する"""
        params: dict[str, str] = {}

        class _Parser(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag == "input":
                    d = dict(attrs)
                    if d.get("type") == "hidden" and "name" in d:
                        params[d["name"]] = d.get("value", "")

        _Parser().feed(html)
        return params

    def _download_pdf(self, page, report_link) -> str | None:
        """T-13方式: ポップアップを経由せず context.request で直接フェッチ。
        Chrome 内蔵 PDF ビューアは CDP をバイパスするため route/iframe は使えない。
        1. report_link.href → weachouhyou.jsp URL を取得
        2. context.request.get(jsp_url) → HTML をフェッチ（cookie 自動付与）
        3. HTML の hidden input から POST パラメータを取得
        4. context.request.post(ChouhyouDisplayPost.do) → PDF バイト取得
        """
        self.prepare_directory()
        year = self.config["target_year"]

        # href から weachouhyou.jsp の絶対 URL を構築（ポップアップを開かない）
        href = report_link.get_attribute("href")
        if not href:
            print(f"[{self.name}] リンクの href が取得できません")
            return None
        jsp_url = f"https://www.e-plan.nomura.co.jp{href}" if href.startswith("/") else href
        self.dlog(f"weachouhyou.jsp URL: {jsp_url}")

        # weachouhyou.jsp を直接フェッチ（Shift-JIS）
        print(f"[{self.name}] weachouhyou.jsp をフェッチ")
        resp = page.context.request.get(jsp_url)
        html = resp.body().decode("shift_jis", errors="replace")
        self.dlog(f"weachouhyou.jsp HTML length: {len(html)}")

        params = self._parse_hidden_inputs(html)
        self.dlog(f"POSTパラメータ: kjnYmd={params.get('kjnYmd')}, chohyoSyurui={params.get('chohyoSyurui')}")

        if not params.get("enterpriseId"):
            print(f"[{self.name}] hidden input のパースに失敗しました")
            self.save_response_html(html.encode("utf-8"), "weachouhyou_parse_fail")
            return None

        # ChouhyouDisplayPost.do へ POST で PDF を直接フェッチ
        print(f"[{self.name}] PDF を直接フェッチ（ChouhyouDisplayPost.do）")
        pdf_resp = page.context.request.post(_PDF_POST_URL, form=params)
        body = pdf_resp.body()

        if body[:4] != b"%PDF":
            print(f"[{self.name}] エラー: PDF ではありません（先頭: {body[:20]}）")
            self.save_response_html(body, "chouhyou_non_pdf")
            return None

        cd = pdf_resp.headers.get("content-disposition", "")
        filename = extract_filename(cd, f"{year}_nomura_mochikabu_haito.pdf")
        pdf_path = self.output_dir / filename
        pdf_path.write_bytes(body)
        print(f"[{self.name}] PDF 保存: {pdf_path}")
        return str(pdf_path)

    def _collect_core(self, page) -> None:
        self._wait_for_login(page)
        year = self.config["target_year"]

        self._navigate_to_list(page)

        report_link = self._find_report_link(page, year)
        if report_link is None:
            self.log_result("skip", [], f"{year}年度の配当金等支払通知書が見つかりません")
            return

        pdf_path = self._download_pdf(page, report_link)
        if pdf_path is None:
            self.log_result("error", [], "PDF ダウンロードに失敗しました")
            return

        self.log_result("success", [pdf_path])

def main() -> None:
    parser = argparse.ArgumentParser(description="野村證券持株会 配当金等支払通知書収集")
    parser.add_argument("--year", type=int, default=None, help="対象年度（例: 2025）")
    args = parser.parse_args()
    collector = NomuraMochikabuCollector(year=args.year)
    collector.run()

if __name__ == "__main__":
    main()
