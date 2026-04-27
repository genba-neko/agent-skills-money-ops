"""野村證券 取引履歴 (New_file.csv) parser。

CSV 構造 (UTF-8 BOM):
    （先頭5行はメタ情報）
    約定日,受渡日,商品,銘柄コード,銘柄名,摘要,取引区分,預り区分,...,受渡金額/決済損益,...
    "2025/12/09","...","株式","9023","東京地下鉄","","入金（配当金）",...,"1674",...

amount は「取引区分」で入金/出金判定:
    入金 / 入庫 系 → amount_in
    出金 / 出庫 / 売却 系 → amount_out
"""
from __future__ import annotations

import csv
from pathlib import Path

from money_ops.normalizer.expense_csv import Transaction, classify, to_int, to_iso_date


def parse(csv_path: Path, year: int) -> list[Transaction]:
    transactions: list[Transaction] = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    # row[0]=="約定日" は CSV 上 2 箇所現れる:
    #   (a) メタ情報「基準日」の値として行 3 に記載（7 列）
    #   (b) 実データの列名行（16 列）
    # 列数 >= 10 で実データ header に絞り込む
    header_idx = next(
        (i for i, row in enumerate(rows)
         if row and row[0] == "約定日" and len(row) >= 10),
        None,
    )
    if header_idx is None:
        return transactions
    header = rows[header_idx]
    for row in rows[header_idx + 1 :]:
        if not row or not row[0]:
            continue
        d = dict(zip(header, row))
        date = to_iso_date(d.get("約定日", ""))
        if not date.startswith(str(year)):
            continue
        torihiki_kbn = d.get("取引区分", "")
        amount = to_int(d.get("受渡金額/決済損益", "0"))
        # 取引区分 から入金/出金判定
        amount_in, amount_out = 0, 0
        if "入金" in torihiki_kbn or "入庫" in torihiki_kbn:
            amount_in = amount
        elif "出金" in torihiki_kbn or "出庫" in torihiki_kbn or "売却" in torihiki_kbn:
            amount_out = amount
        else:
            # 不明な区分は受渡金額正符号で in、負で out 想定（実データに応じて調整）
            amount_in = amount

        meigara = d.get("銘柄名", "").strip()
        tekiyou = d.get("摘要", "").strip()
        description = " ".join(filter(None, [meigara, tekiyou])).strip() or torihiki_kbn

        transactions.append(
            Transaction(
                date=date,
                amount_in=amount_in,
                amount_out=amount_out,
                description=description,
                category_raw=torihiki_kbn,
                category=classify(torihiki_kbn),
                security_code=d.get("銘柄コード", "").strip() or None,
                security_name=meigara or None,
                raw=d,
            )
        )
    return transactions
