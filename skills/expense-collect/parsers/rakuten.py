"""楽天証券 入出金履歴 + 配当金履歴 parser。

ファイル名で 2 種類を判別:
- Withdrawallist_*.csv: 入出金履歴 (5 列)
    入出金日,入金額[円],出金額[円],内容,出金先
- dividendlist_*.csv: 配当金履歴 (11 列)
    入金日,商品,口座,銘柄コード,銘柄,受取通貨,単価[...],数量[...],配当・分配金合計（税引前）[...],税額合計[...],受取金額[...]

両 CSV とも encoding は cp932。
配当金 CSV は通貨混在 (円 / USドル等) → 円のみ amount_in に計上、他通貨は raw 保持のみ。
"""
from __future__ import annotations

import csv
from pathlib import Path

from money_ops.normalizer.expense_csv import Transaction, classify, to_int, to_iso_date


def parse(csv_path: Path, year: int) -> list[Transaction]:
    name = csv_path.name.lower()
    if name.startswith("withdrawallist"):
        return _parse_withdrawal(csv_path, year)
    if name.startswith("dividendlist"):
        return _parse_dividend(csv_path, year)
    return []


def _parse_withdrawal(csv_path: Path, year: int) -> list[Transaction]:
    transactions: list[Transaction] = []
    with open(csv_path, "r", encoding="cp932") as f:
        rows = list(csv.reader(f))
    header_idx = next(
        (i for i, row in enumerate(rows) if row and row[0] == "入出金日"),
        None,
    )
    if header_idx is None:
        return transactions
    header = rows[header_idx]
    for row in rows[header_idx + 1 :]:
        if not row or not row[0]:
            continue
        d = dict(zip(header, row))
        date = to_iso_date(d.get("入出金日", ""))
        if not date.startswith(str(year)):
            continue
        content = d.get("内容", "")
        dest = d.get("出金先", "")
        text = f"{content} {dest}"
        transactions.append(
            Transaction(
                date=date,
                amount_in=to_int(d.get("入金額[円]", "0")),
                amount_out=to_int(d.get("出金額[円]", "0")),
                description=content,
                category_raw=dest or content,
                category=classify(text),
                security_code=None,
                security_name=None,
                raw=d,
            )
        )
    return transactions


_CURRENCY_MAP = {
    "円": "JPY",
    "USドル": "USD",
    "ユーロ": "EUR",
    "豪ドル": "AUD",
    "NZドル": "NZD",
    "カナダドル": "CAD",
}


def _to_amount(s: str, is_jpy: bool) -> int:
    """金額文字列 → 整数。円は整数化、外貨は小数桁を 100 倍 (cent 単位) で保持。"""
    if not s:
        return 0
    s = str(s).strip().strip('"').replace(",", "")
    if not s or s == "-":
        return 0
    try:
        v = float(s)
    except ValueError:
        return 0
    return int(v) if is_jpy else int(round(v * 100))


def _parse_dividend(csv_path: Path, year: int) -> list[Transaction]:
    transactions: list[Transaction] = []
    with open(csv_path, "r", encoding="cp932") as f:
        rows = list(csv.reader(f))
    header_idx = next(
        (i for i, row in enumerate(rows) if row and row[0] == "入金日"),
        None,
    )
    if header_idx is None:
        return transactions
    header = rows[header_idx]
    for row in rows[header_idx + 1 :]:
        if not row or not row[0]:
            continue
        d = dict(zip(header, row))
        date = to_iso_date(d.get("入金日", ""))
        if not date.startswith(str(year)):
            continue
        currency_raw = d.get("受取通貨", "").strip()
        currency = _CURRENCY_MAP.get(currency_raw, currency_raw or "JPY")
        is_jpy = (currency == "JPY")
        amount_in = _to_amount(d.get("受取金額[円/現地通貨]", "0"), is_jpy)
        meigara = d.get("銘柄", "").strip()
        transactions.append(
            Transaction(
                date=date,
                amount_in=amount_in,
                amount_out=0,
                description=meigara,
                category_raw="配当・分配金",
                category="dividend",
                currency=currency,
                security_code=d.get("銘柄コード", "").strip() or None,
                security_name=meigara or None,
                raw=d,
            )
        )
    return transactions
