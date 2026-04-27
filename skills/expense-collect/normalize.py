"""expense-collect 共通フォーマット正規化ランナー

使い方:
    python skills/expense-collect/normalize.py --year 2025
    python skills/expense-collect/normalize.py --year 2025 --sites sbi rakuten

入力: data/expenses/securities/<code>/<year>/raw/*.csv
出力: data/expenses/securities/<code>/<year>/normalized.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SKILLS_DIR.parents[1]
_REGISTRY = _SKILLS_DIR / "registry.json"

sys.path.insert(0, str(_SKILLS_DIR))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from money_ops.normalizer.expense_csv import (  # noqa: E402
    NormalizedReport,
    Transaction,
    build_summary,
)
from parsers import nomura, rakuten, sbi  # noqa: E402

_CURRENT_YEAR = datetime.now().year

_PARSERS = {
    "sbi": sbi.parse,
    "nomura": nomura.parse,
    "rakuten": rakuten.parse,
}


def load_accounts() -> list[dict]:
    data = json.loads(_REGISTRY.read_text(encoding="utf-8"))
    return data["accounts"]


def normalize_one(account: dict, year: int) -> Path | None:
    code = account["code"]
    category = account.get("category", "securities")
    parser_fn = _PARSERS.get(code)
    if parser_fn is None:
        print(f"[SKIP] {code}: parser 未実装")
        return None

    raw_dir = _PROJECT_ROOT / "data" / "expenses" / category / code / str(year) / "raw"
    if not raw_dir.exists():
        print(f"[SKIP] {code}: raw dir なし ({raw_dir})")
        return None

    csv_files = sorted(raw_dir.glob("*.csv"))
    if not csv_files:
        print(f"[SKIP] {code}: CSV なし")
        return None

    # 同種 CSV (filename prefix が同じもの) は最新のみ採用
    # 例: SBI が同年に複数回採取 → DetailInquiry_*.csv 3 ファイル → 最新 1 つ
    by_prefix: dict[str, Path] = {}
    for p in csv_files:
        # prefix = 拡張子と末尾の数字（タイムスタンプ）を除いた識別子
        import re
        m = re.match(r"([A-Za-z_]+)", p.stem)
        prefix = m.group(1) if m else p.stem
        if prefix not in by_prefix or p.stat().st_mtime > by_prefix[prefix].stat().st_mtime:
            by_prefix[prefix] = p
    selected = sorted(by_prefix.values())

    transactions: list[Transaction] = []
    sources: list[str] = []
    for csv_path in selected:
        txs = parser_fn(csv_path, year)
        transactions.extend(txs)
        sources.append(csv_path.name)
        print(f"  [{code}] {csv_path.name}: {len(txs)}件")

    transactions.sort(key=lambda t: t.date)
    report = NormalizedReport(
        broker=code,
        year=year,
        source_file=", ".join(sources),
        transactions=transactions,
        summary=build_summary(transactions),
    )

    out_path = _PROJECT_ROOT / "data" / "expenses" / category / code / str(year) / "normalized.json"
    report.write(out_path)
    print(f"[{code}] → {out_path} (件数: {len(transactions)}, "
          f"配当: {report.summary['by_category'].get('dividend', 0)})")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="expense-collect 共通フォーマット正規化")
    parser.add_argument("--year", type=int, default=_CURRENT_YEAR - 1)
    parser.add_argument("--sites", nargs="+", metavar="CODE")
    args = parser.parse_args()

    accounts = load_accounts()
    if args.sites:
        codes = set(args.sites)
        accounts = [a for a in accounts if a["code"] in codes]

    if not accounts:
        print("[WARN] 対象 account なし")
        sys.exit(0)

    results = {"ok": [], "skip": []}
    for account in accounts:
        try:
            out = normalize_one(account, args.year)
            (results["ok"] if out else results["skip"]).append(account["code"])
        except Exception as e:
            print(f"[ERROR] {account['code']}: {e}")
            results["skip"].append(account["code"])

    print(f"\n=== 正規化結果 ===")
    print(f"  OK   : {', '.join(results['ok']) or 'なし'}")
    print(f"  SKIP : {', '.join(results['skip']) or 'なし'}")


if __name__ == "__main__":
    main()
