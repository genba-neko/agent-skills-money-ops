"""e-shishobako（電子私書箱）共通PDF取得ヘルパー

DPAW010501020 エンドポイントから PDF を route-capture する。
SBI・GMOクリック・野村・ひふみ投信で共通利用。
"""

from __future__ import annotations

import re
from pathlib import Path

from money_ops.utils import extract_filename, wait as _wait

_DPAW_URL_PATTERN = "**/DPAW010501020"


def capture_dpaw_pdf(
    popup,
    output_dir: Path,
    fallback_name: str,
    *,
    label: str = "eshishobako",
    button_name_pattern: re.Pattern[str] | str | None = None,
) -> str | None:
    """指定ボタンをクリックし DPAW010501020 レスポンスを捕捉して保存する。

    Args:
        popup: e-shishobako SPA の Playwright Page オブジェクト
        output_dir: 保存先ディレクトリ（既に存在すること）
        fallback_name: Content-Disposition が取得できない場合のファイル名
        label: ログ出力用プレフィックス（呼び出し元の self.name を渡す）
        button_name_pattern: クリック対象ボタンの role-name パターン。
            None の場合は has_text="PDFファイル" でフィルタ（SBI/GMO/野村互換）。
            同画面に複数 PDF ボタンが並ぶサイト（hifumi 等）は厳密パターン指定必須。

    Returns:
        保存したファイルパス（str）。失敗時は None。
    """
    if button_name_pattern is not None:
        pdf_btn = popup.get_by_role("button", name=button_name_pattern)
    else:
        pdf_btn = popup.locator("button, a").filter(has_text="PDFファイル")
    if pdf_btn.count() == 0:
        print(f"[{label}] PDF ボタンが見つかりません")
        return None

    pdf_bytes_holder: list[tuple[str, bytes]] = []

    def _capture(route, _request) -> None:
        response = route.fetch()
        body = response.body()
        if body[:4] == b"%PDF":
            cd = response.headers.get("content-disposition", "")
            filename = extract_filename(cd, fallback_name)
            pdf_bytes_holder.append((filename, body))
        route.fulfill(response=response)

    popup.context.route(_DPAW_URL_PATTERN, _capture)
    try:
        pdf_btn.first.scroll_into_view_if_needed()
        with popup.expect_popup() as pdf_popup_info:
            pdf_btn.first.click()
        pdf_popup = pdf_popup_info.value
        pdf_popup.wait_for_load_state("domcontentloaded")
        _wait()
        pdf_popup.close()
    finally:
        popup.context.unroute(_DPAW_URL_PATTERN, _capture)

    if not pdf_bytes_holder:
        print(f"[{label}] PDF レスポンスを捕捉できませんでした")
        return None

    filename, pdf_bytes = pdf_bytes_holder[0]
    pdf_path = output_dir / filename
    pdf_path.write_bytes(pdf_bytes)
    print(f"[{label}] PDF 保存: {pdf_path}")
    return str(pdf_path)
