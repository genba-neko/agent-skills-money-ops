"""PDF（特定口座年間取引報告書）→ nenkantorihikihokokusho.json 変換モジュール

Claude API（claude-sonnet-4-6）を使用して PDF を解析し、
プラン定義の JSON スキーマに変換する。
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path

import anthropic

_MODEL = "claude-sonnet-4-6"

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


def convert_pdf_to_json(
    pdf_path: str | Path,
    company: str,
    code: str,
    year: int,
    raw_files: list[str] | None = None,
    collected_at: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> dict:
    """PDF を nenkantorihikihokokusho.json の dict に変換する。

    Parameters
    ----------
    pdf_path:
        特定口座年間取引報告書 PDF のパス
    company:
        証券会社名（registry.json の name）
    code:
        証券会社コード（registry.json の code）
    year:
        対象年度（例: 2025）
    raw_files:
        収集した原本ファイルのパスリスト
    collected_at:
        収集日時（ISO 8601 形式）。None の場合は現在日時を使用
    client:
        anthropic.Anthropic インスタンス。None の場合は自動生成（ANTHROPIC_API_KEY 環境変数が必要）
    """
    pdf_path = Path(pdf_path)
    if client is None:
        client = anthropic.Anthropic()

    pdf_b64 = _encode_pdf(pdf_path)

    message = client.messages.create(
        model=_MODEL,
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
                    {
                        "type": "text",
                        "text": _EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )

    extracted = json.loads(message.content[0].text)

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
