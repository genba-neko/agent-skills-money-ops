"""PDF（特定口座年間取引報告書）→ nenkantorihikihokokusho.json 変換モジュール

優先順位:
  1. ANTHROPIC_API_KEY が設定されていれば claude-sonnet-4-6 を使用
  2. GEMINI_API_KEY（または GOOGLE_API_KEY）が設定されていれば gemini-2.0-flash を使用（PDF マルチモーダル）
  3. Docling（ローカル PDF テキスト抽出）+ Gemini text API
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from pathlib import Path

_ANTHROPIC_MODEL = "claude-sonnet-4-6"
_GEMINI_MODEL = "gemini-2.0-flash-lite"

_EXTRACTION_PROMPT = """\
添付の PDF は日本の証券会社が発行した「特定口座年間取引報告書」です。
以下の JSON スキーマに従って、PDF に記載されている数値・情報をすべて抽出してください。

**ルール**
- 記載がない項目は 0（数値）または ""（文字列）を使用する
- 金額はすべて整数（円単位）で出力する
- true/false は boolean 型で出力する
- 口座種別は「源泉徴収あり特定口座」または「源泉徴収なし特定口座」のいずれかを記載する
- 開設日は YYYY-MM-DD 形式で出力する（不明な場合は ""）
- 法人番号が記載されていない場合は ""
- 出力は JSON のみ。説明文・コードブロック記号は不要

**JSON スキーマ**
{
  "account": {
    "口座種別": "",
    "譲渡所得源泉徴収": true,
    "配当所得源泉徴収": true,
    "開設日": ""
  },
  "譲渡": {
    "取引件数_上場株式等": 0,
    "取引件数_信用等": 0,
    "取引件数_一般株式等": 0,
    "上場株式等": {
      "譲渡の対価の額": 0,
      "取得費及び譲渡に要した費用の額等": 0,
      "差引金額_譲渡損益": 0
    },
    "一般株式等": {
      "譲渡の対価の額": 0,
      "取得費及び譲渡に要した費用の額等": 0,
      "差引金額_譲渡損益": 0
    },
    "損益通算後": {
      "所得控除の額の合計額": 0,
      "差引所得税額": 0,
      "翌年繰越損失額": 0
    },
    "合計": {
      "課税標準": 0,
      "取得費等": 0,
      "差引損益": 0
    }
  },
  "配当等": {
    "上場株式の配当等": {
      "配当等の額": 0,
      "所得税": 0,
      "復興特別所得税": 0,
      "地方税": 0
    },
    "特定株式投資信託の収益の分配等": {
      "配当等の額": 0,
      "所得税": 0,
      "復興特別所得税": 0,
      "地方税": 0
    },
    "一般株式等の配当等": {
      "配当等の額": 0,
      "所得税": 0,
      "復興特別所得税": 0,
      "地方税": 0
    },
    "投資信託等の収益の分配等": {
      "配当等の額": 0,
      "所得税": 0,
      "復興特別所得税": 0,
      "地方税": 0
    },
    "非居住者等への配当等": {
      "配当等の額": 0,
      "所得税": 0,
      "復興特別所得税": 0,
      "地方税": 0
    },
    "外国株式等の配当等": {
      "配当等の額": 0,
      "外国所得税": 0
    },
    "NISA口座内の配当等": {
      "配当等の額": 0
    },
    "合計": {
      "配当等の額": 0,
      "所得税_源泉徴収税額": 0,
      "復興特別所得税": 0,
      "地方税": 0,
      "納付税額": 0
    }
  },
  "NISA": {
    "譲渡等": {
      "譲渡の対価の額": 0,
      "取得費等": 0
    }
  },
  "源泉徴収税額合計": {
    "所得税": 0,
    "復興特別所得税": 0
  },
  "証券会社": {
    "名称": "",
    "法人番号": ""
  }
}
"""


def _encode_pdf(pdf_path: Path) -> str:
    return base64.standard_b64encode(pdf_path.read_bytes()).decode("utf-8")


def _extract_with_anthropic(pdf_path: Path, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    pdf_b64 = _encode_pdf(pdf_path)
    message = client.messages.create(
        model=_ANTHROPIC_MODEL,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": _EXTRACTION_PROMPT},
                ],
            }
        ],
    )
    return message.content[0].text


def _extract_with_gemini(pdf_path: Path, api_key: str) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    pdf_bytes = pdf_path.read_bytes()
    response = client.models.generate_content(
        model=_GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            _EXTRACTION_PROMPT,
        ],
    )
    return response.text


def _extract_with_docling_cli(pdf_path: Path) -> str:
    """Docling でローカル PDF テキスト抽出 → gemini CLI（OAuth）で JSON 構築。
    API キー不要。gemini CLI のインストールと認証が前提。
    """
    import logging
    import subprocess
    import time

    logging.getLogger("docling").setLevel(logging.ERROR)
    logging.getLogger("rapidocr").setLevel(logging.ERROR)

    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    def _convert(do_ocr: bool) -> str:
        opts = PdfPipelineOptions()
        opts.do_ocr = do_ocr
        conv = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
        return conv.convert(str(pdf_path)).document.export_to_markdown()

    t0 = time.time()
    print("[pdf_to_json] Docling テキスト抽出中...")
    pdf_text = _convert(do_ocr=False)
    if len(pdf_text.strip()) < 100:
        print("[pdf_to_json] テキスト少 → OCR 有効で再試行")
        pdf_text = _convert(do_ocr=True)
    print(f"[pdf_to_json] Docling 完了: {time.time()-t0:.1f}s ({len(pdf_text)}chars)")

    schema_part = _EXTRACTION_PROMPT.split("**JSON スキーマ**")[1].strip()
    stdin_text = (
        "以下は「特定口座年間取引報告書」から抽出したテキストです。\n\n"
        f"{pdf_text}\n\n"
        f"**JSON スキーマ**\n{schema_part}"
    )
    prompt = (
        "上記テキストから指定スキーマに従い数値・情報を抽出してJSONのみ出力。"
        "説明文・コードブロック記号不要。記載なし項目は0または\"\"。金額は整数。"
    )

    import shutil
    gemini_bin = shutil.which("gemini") or shutil.which("gemini.cmd")
    if not gemini_bin:
        raise RuntimeError("gemini CLI が見つかりません。npm install -g @google/generative-ai-cli 等でインストールしてください。")

    t1 = time.time()
    print("[pdf_to_json] gemini CLI JSON変換中...")
    proc = subprocess.run(
        [gemini_bin, "--output-format", "text", "-p", prompt],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    print(f"[pdf_to_json] gemini CLI 完了: {time.time()-t1:.1f}s")
    if proc.returncode != 0:
        raise RuntimeError(f"gemini CLI エラー: {proc.stderr[:500]}")
    return proc.stdout.strip()


def convert_pdf_to_json(
    pdf_path: str | Path,
    company: str,
    code: str,
    year: int,
    raw_files: list[str] | None = None,
    collected_at: str | None = None,
    client=None,
) -> dict:
    """PDF を nenkantorihikihokokusho.json の dict に変換する。

    優先順位:
      1. ANTHROPIC_API_KEY → Claude (PDF マルチモーダル)
      2. gemini CLI (Docling テキスト抽出 + OAuth)
      3. GEMINI_API_KEY → Gemini API (PDF マルチモーダル、フォールバック)
    """
    pdf_path = Path(pdf_path)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if anthropic_key:
        raw_text = _extract_with_anthropic(pdf_path, anthropic_key)
    else:
        try:
            raw_text = _extract_with_docling_cli(pdf_path)
        except Exception as e:
            if not gemini_key:
                raise RuntimeError(
                    "gemini CLI 失敗かつ API キー未設定。"
                    "gemini CLI をインストールするか GEMINI_API_KEY を設定してください。"
                ) from e
            print(f"[pdf_to_json] gemini CLI 失敗 ({type(e).__name__})、Gemini API フォールバック試行")
            raw_text = _extract_with_gemini(pdf_path, gemini_key)

    extracted = json.loads(raw_text)

    return {
        "company": company,
        "code": code,
        "year": year,
        "document_type": "特定口座年間取引報告書",
        "source": "pdf_ocr",
        **extracted,
        "raw_files": raw_files or [],
        "collected_at": collected_at or datetime.now().isoformat(),
    }
