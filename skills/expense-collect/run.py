"""expense-collect 一括実行ランナー

使い方:
    python skills/expense-collect/run.py --year 2025
    python skills/expense-collect/run.py --year 2025 --sites sbi
    python skills/expense-collect/run.py --year 2025 --force
    python skills/expense-collect/run.py --year 2025 --fail-fast

デフォルト: 収集済み（data/expenses/<code>/<year>/raw/ に CSV 1つ以上存在）はスキップ。
--force: 収集済みでも再実行。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

_SKILLS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SKILLS_DIR.parents[1]
_REGISTRY = _SKILLS_DIR / "registry.json"
_VALID_CODE = re.compile(r"^[a-z0-9-]+$")

_CURRENT_YEAR = datetime.now().year


def load_accounts() -> list[dict]:
    try:
        data = json.loads(_REGISTRY.read_text(encoding="utf-8"))
        accounts = data["accounts"]
        if not isinstance(accounts, list):
            raise TypeError("accounts が list でない")
        return accounts
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[ERROR] registry.json 読み込み失敗: {e}")
        sys.exit(1)


def is_collected(code: str, year: int) -> bool:
    """収集済み判定: data/expenses/<code>/<year>/raw/ に CSV ファイルが 1 つ以上存在。"""
    raw_dir = _PROJECT_ROOT / "data" / "expenses" / code / str(year) / "raw"
    if not raw_dir.exists():
        return False
    return any(raw_dir.glob("*.csv"))


def _print_header(label: str) -> None:
    print(f"\n{'='*60}")
    print(label)
    print(f"{'='*60}")


def run_account(code: str, name: str, year: int) -> Literal["ok", "error", "missing"]:
    script = _SKILLS_DIR / "sites" / code / "collect.py"
    if not script.exists():
        print(f"\n[{code}] スクリプトなし: {script}")
        return "missing"

    _print_header(f"[{code}] {name} 開始 ({datetime.now().strftime('%H:%M:%S')})")

    try:
        result = subprocess.run(
            [sys.executable, str(script), "--year", str(year)],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
    except OSError as e:
        print(f"[{code}] 起動失敗: {e}")
        return "error"

    return "ok" if result.returncode == 0 else "error"


def main() -> None:
    parser = argparse.ArgumentParser(description="expense-collect 一括実行ランナー")
    parser.add_argument(
        "--year", type=int, default=_CURRENT_YEAR,
        help=f"対象年（暦年、デフォルト: 当年 {_CURRENT_YEAR}）",
    )
    parser.add_argument("--sites", nargs="+", metavar="CODE")
    parser.add_argument("--force", action="store_true", help="収集済みでも再実行")
    parser.add_argument("--fail-fast", action="store_true", dest="fail_fast")
    args = parser.parse_args()

    if not (1900 <= args.year <= _CURRENT_YEAR):
        print(f"[ERROR] 年が範囲外: {args.year}（未来年は不可）")
        sys.exit(1)

    accounts = load_accounts()

    if args.sites:
        for code in args.sites:
            if not _VALID_CODE.match(code):
                print(f"[ERROR] 不正なコード: {code}")
                sys.exit(1)
        codes = list(dict.fromkeys(args.sites))
        unknown = set(codes) - {a["code"] for a in accounts}
        if unknown:
            print(f"[ERROR] 不明な口座コード: {', '.join(sorted(unknown))}")
            sys.exit(1)
        account_map = {a["code"]: a for a in accounts}
        accounts = [account_map[c] for c in codes]

    if not accounts:
        print("[WARN] 実行対象口座なし")
        sys.exit(0)

    results: dict[str, list[str]] = {"ok": [], "error": [], "missing": [], "skip": [], "done": []}
    stop = False

    try:
        for account in accounts:
            if stop:
                break
            code = account["code"]
            name = account["name"]
            collection = account.get("collection", "auto")

            if collection != "auto":
                print(f"\n[SKIP] {code} ({name}): 未対応の収集方式 ({collection!r})")
                results["skip"].append(code)
                continue

            if not args.force and is_collected(code, args.year):
                print(f"\n[DONE] {code} ({name}): 収集済み（スキップ）")
                results["done"].append(code)
                continue

            status = run_account(code, name, args.year)
            results[status].append(code)

            if status in ("error", "missing") and args.fail_fast:
                print(f"\n[FAIL-FAST] {code} でエラー → 停止")
                stop = True

    except KeyboardInterrupt:
        print("\n[中断] Ctrl+C")

    if not results["ok"] and not results["error"] and not results["missing"]:
        print("\n[WARN] 実行した口座なし（全件 収集済みまたはスキップ）")

    print(f"\n{'='*60}")
    print("=== 収集結果 ===")
    print(f"  OK      : {', '.join(results['ok']) or 'なし'}")
    print(f"  ERROR   : {', '.join(results['error']) or 'なし'}")
    print(f"  MISSING : {', '.join(results['missing']) or 'なし'}  ← スクリプト未作成")
    print(f"  DONE    : {', '.join(results['done']) or 'なし'}  ← 収集済みスキップ")
    print(f"  SKIP    : {', '.join(results['skip']) or 'なし'}  ← 手動/未対応")
    print(f"{'='*60}")

    if results["error"] or results["missing"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
