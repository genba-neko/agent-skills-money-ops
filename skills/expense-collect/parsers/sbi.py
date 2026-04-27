"""SBI証券 入出金明細 (DetailInquiry_*.csv) parser。

CSV 構造 (UTF-8 BOM):
    （先頭3行はメタ情報）
    入出金日,取引,区分,摘要,出金額,入金額
    "2025/12/30","出金","その他","投信るいとうお買付預り金振替","100000","0"
"""
from __future__ import annotations

import csv
from pathlib import Path

from money_ops.normalizer.expense_csv import Transaction, classify, to_int, to_iso_date


def parse(csv_path: Path, year: int) -> list[Transaction]:
    """SBI 入出金明細 CSV を読み、当該 year のトランザクション list を返す。"""
    transactions: list[Transaction] = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        # 先頭の見出し + メタ情報を skip し、データヘッダ行 (`入出金日` で始まる) を探す
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
        torihiki = d.get("取引", "")
        kbn = d.get("区分", "")
        tekiyou = d.get("摘要", "")
        text = f"{torihiki} {kbn} {tekiyou}"
        transactions.append(
            Transaction(
                date=date,
                amount_in=to_int(d.get("入金額", "0")),
                amount_out=to_int(d.get("出金額", "0")),
                description=tekiyou,
                category_raw=f"{torihiki}/{kbn}",
                category=classify(text),
                security_code=None,
                security_name=None,
                raw=d,
            )
        )
    return transactions
