"""配当金集計ランナー

各社 normalized.json から category=dividend を抽出し、
画面表示 + CSV 出力 (data/expenses/aggregated/dividend_<year>.csv)。

使い方:
    python skills/expense-collect/aggregate_dividend.py --year 2025
    python skills/expense-collect/aggregate_dividend.py --year 2025 --sites sbi rakuten
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path

_RATE_CACHE_FILE = Path(__file__).parent / ".fx_rate_cache.json"


def _load_rate_cache() -> dict:
    if _RATE_CACHE_FILE.exists():
        return json.loads(_RATE_CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_rate_cache(cache: dict) -> None:
    _RATE_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def fetch_rate(date: str, currency: str) -> float | None:
    """frankfurter.app から date の currency → JPY レート取得（cache 付き）。

    休日は前営業日 close レートが返る。失敗時 None。
    """
    if currency == "JPY":
        return 1.0
    cache = _load_rate_cache()
    key = f"{date}_{currency}_JPY"
    if key in cache:
        return cache[key]
    url = f"https://api.frankfurter.app/{date}?from={currency}&to=JPY"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; expense-collect/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        rate = float(data["rates"]["JPY"])
        cache[key] = rate
        _save_rate_cache(cache)
        return rate
    except Exception as e:
        print(f"[WARN] レート取得失敗 {date} {currency}: {e}", file=sys.stderr)
        return None


def _w(s: str) -> int:
    """East Asian Wide/Fullwidth は 2 cell、それ以外は 1 cell として表示幅算出。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def pad(s: str, width: int, align: str = "<") -> str:
    """表示幅 width に padding。truncate も表示幅基準。"""
    s = str(s)
    # truncate（表示幅で切る）
    out = ""
    used = 0
    for c in s:
        cw = 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        if used + cw > width:
            break
        out += c
        used += cw
    pad_n = width - used
    return out + " " * pad_n if align == "<" else " " * pad_n + out

# Windows コマンドプロンプトの cp932 文字化け対策
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

_SKILLS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SKILLS_DIR.parents[1]
_REGISTRY = _SKILLS_DIR / "registry.json"
_CURRENT_YEAR = datetime.now().year


def load_accounts() -> list[dict]:
    return json.loads(_REGISTRY.read_text(encoding="utf-8"))["accounts"]


def collect_dividends(accounts: list[dict], year: int, convert_jpy: bool = False) -> list[dict]:
    rows: list[dict] = []
    for account in accounts:
        code = account["code"]
        category = account.get("category", "securities")
        json_path = _PROJECT_ROOT / "data" / "expenses" / category / code / str(year) / "normalized.json"
        if not json_path.exists():
            continue
        data = json.loads(json_path.read_text(encoding="utf-8"))
        for t in data["transactions"]:
            if t["category"] != "dividend":
                continue
            currency = t.get("currency", "JPY")
            amount = t["amount_in"] / 100 if currency != "JPY" else t["amount_in"]
            jpy_amount = None
            if convert_jpy:
                if currency == "JPY":
                    jpy_amount = amount
                else:
                    rate = fetch_rate(t["date"], currency)
                    jpy_amount = int(round(amount * rate)) if rate else None
            rows.append({
                "date": t["date"],
                "broker": code,
                "currency": currency,
                "security_code": t["security_code"] or "",
                "security_name": t["security_name"] or t["description"],
                "amount": amount,
                "jpy_amount": jpy_amount,
                "category_raw": t["category_raw"],
            })
    rows.sort(key=lambda r: (r["date"], r["broker"]))
    return rows


def print_table(rows: list[dict], convert_jpy: bool) -> None:
    """USD 列・JPY 列を別カラムで表示。
    JPY 行: USD は "-"、JPY に円額
    USD 行: USD に現地通貨額、JPY に円換算後（convert_jpy 時）
    """
    cols = [("日付", 12, "<"), ("社", 10, "<"),
            ("コード", 10, "<"), ("銘柄", 40, "<"),
            ("USD", 12, ">"), ("JPY", 12, ">")]
    print(" ".join(pad(c[0], c[1], c[2]) for c in cols))
    print("-" * (sum(c[1] for c in cols) + len(cols) - 1))
    for r in rows:
        if r["currency"] == "JPY":
            usd_str = "-"
            jpy_str = f'{int(r["amount"]):,}'
        else:
            usd_str = f'{r["amount"]:,.2f}' if r["currency"] == "USD" else f'{r["currency"]} {r["amount"]:,.2f}'
            jpy = r.get("jpy_amount") if convert_jpy else None
            jpy_str = f'{jpy:,}' if jpy is not None else "-"
        vals = [r["date"], r["broker"], r["security_code"], r["security_name"], usd_str, jpy_str]
        print(" ".join(pad(v, c[1], c[2]) for v, c in zip(vals, cols)))


def print_summary(rows: list[dict], convert_jpy: bool = False) -> None:
    # 通貨 × 社 で集計
    agg: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["currency"], r["broker"])
        a = agg.setdefault(key, {"count": 0, "amount": 0})
        a["count"] += 1
        a["amount"] += r["amount"]
    print("\n=== 集計（通貨別 × 社別）===")
    cols = [("通貨", 5, "<"), ("社", 10, "<"), ("件数", 6, ">"), ("合計", 16, ">")]
    print(" ".join(pad(c[0], c[1], c[2]) for c in cols))
    print("-" * (sum(c[1] for c in cols) + len(cols) - 1))
    by_currency: dict[str, dict] = {}
    for (cur, code), s in sorted(agg.items()):
        amt = f'{s["amount"]:,.2f}' if cur != "JPY" else f'{int(s["amount"]):,}'
        vals = [cur, code, str(s["count"]), amt]
        print(" ".join(pad(v, c[1], c[2]) for v, c in zip(vals, cols)))
        c2 = by_currency.setdefault(cur, {"count": 0, "amount": 0})
        c2["count"] += s["count"]
        c2["amount"] += s["amount"]
    print("\n=== 通貨別 合計 ===")
    for cur, s in sorted(by_currency.items()):
        amt = f'{s["amount"]:,.2f}' if cur != "JPY" else f'{int(s["amount"]):,}'
        print(f'{pad(cur, 5)} {pad(str(s["count"]), 6, ">")} 件  {pad(amt, 16, ">")}')

    if convert_jpy:
        total_jpy = sum(r["jpy_amount"] for r in rows if r.get("jpy_amount") is not None)
        missing = sum(1 for r in rows if r.get("jpy_amount") is None)
        print(f'\n=== 全通貨 円換算合計 ===')
        print(f'  合計: {total_jpy:,} 円  (件数: {len(rows)}, レート取得失敗: {missing})')


def write_csv(rows: list[dict], year: int, convert_jpy: bool) -> Path:
    out_dir = _PROJECT_ROOT / "data" / "expenses" / "aggregated"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"dividend_{year}.csv"
    fields = ["date", "broker", "currency", "security_code", "security_name", "amount", "category_raw"]
    if convert_jpy:
        fields.insert(6, "jpy_amount")
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="配当金集計（外貨は受取日のスポットレートで日本円換算）")
    parser.add_argument("--year", type=int, default=_CURRENT_YEAR - 1)
    parser.add_argument("--sites", nargs="+", metavar="CODE")
    parser.add_argument("--no-spot-rate", action="store_true",
                        help="スポットレート換算（外貨→円）を行わない（default: 実行）")
    args = parser.parse_args()

    fx = not args.no_spot_rate

    accounts = load_accounts()
    if args.sites:
        codes = set(args.sites)
        accounts = [a for a in accounts if a["code"] in codes]

    rows = collect_dividends(accounts, args.year, convert_jpy=fx)
    if not rows:
        print(f"[WARN] {args.year} 年の配当金データなし")
        sys.exit(0)

    print_table(rows, convert_jpy=fx)
    print_summary(rows, convert_jpy=fx)
    out_path = write_csv(rows, args.year, convert_jpy=fx)
    print(f"\n[OK] CSV 保存: {out_path}")


if __name__ == "__main__":
    main()
