"""証券会社入出金/配当金 CSV を共通スキーマに正規化するための core モジュール。

各社 parser は `list[Transaction]` を返す。NormalizedReport にまとめて JSON 出力。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCHEMA_VERSION = "1.0"


@dataclass
class Transaction:
    date: str             # ISO 8601 "YYYY-MM-DD"
    amount_in: int        # 入金 (none=0)。currency に依存（円 = 整数円、USドル等 = 小数桁切捨）
    amount_out: int       # 出金 (none=0)
    description: str      # 摘要 + 銘柄名等の結合
    category_raw: str     # 元 CSV の取引区分そのまま
    category: str         # 正規化: dividend/sale/purchase/deposit/withdrawal/tax/other
    currency: str = "JPY"  # ISO 通貨コード（"JPY", "USD" 等）。amount_in/out の単位
    security_code: str | None = None
    security_name: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class NormalizedReport:
    broker: str
    year: int
    source_file: str
    transactions: list[Transaction]
    summary: dict = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def write(self, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(self.to_json(), encoding="utf-8")


# カテゴリ正規化ルール: 優先順位順に評価
_CATEGORY_PATTERNS = [
    ("dividend", ("配当", "分配")),
    ("tax", ("源泉徴収", "税還付")),
    ("sale", ("売却", "現物売却")),
    ("purchase", ("買付", "お買付")),
    ("deposit", ("入金", "入庫")),
    ("withdrawal", ("出金", "出庫", "振替出金", "振込", "スイープ")),
]


def classify(text: str) -> str:
    """テキスト（取引区分 + 摘要を結合した文字列等）からカテゴリを判定。

    優先順位: dividend > tax > sale > purchase > deposit > withdrawal > other
    """
    if not text:
        return "other"
    for category, keywords in _CATEGORY_PATTERNS:
        if any(kw in text for kw in keywords):
            return category
    return "other"


def to_iso_date(s: str) -> str:
    """各社の日付表記を ISO 8601 (YYYY-MM-DD) に変換。

    対応形式: "2025/12/30", "2025年12月30日"
    """
    if not s:
        return ""
    s = s.strip().strip('"').strip("'")
    if "年" in s and "月" in s:
        s = s.replace("年", "/").replace("月", "/").replace("日", "")
    return s.replace("/", "-")


def to_int(s: str) -> int:
    """カンマ区切り整数文字列 → int。空/'-' は 0。"""
    if not s:
        return 0
    s = str(s).strip().strip('"').replace(",", "")
    if not s or s == "-":
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def build_summary(transactions: list[Transaction]) -> dict:
    """通貨混在を考慮した集計。total_in/out は通貨別 dict。

    外貨は cent 単位（×100 整数）で保存しているため、合算は同通貨同士のみ。
    """
    by_cur_in: dict[str, int] = {}
    by_cur_out: dict[str, int] = {}
    for t in transactions:
        cur = t.currency
        by_cur_in[cur] = by_cur_in.get(cur, 0) + t.amount_in
        by_cur_out[cur] = by_cur_out.get(cur, 0) + t.amount_out
    return {
        "total_in_by_currency": by_cur_in,
        "total_out_by_currency": by_cur_out,
        "count": len(transactions),
        "by_category": {
            cat: sum(1 for t in transactions if t.category == cat)
            for cat in {t.category for t in transactions}
        },
    }
