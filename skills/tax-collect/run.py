"""tax-collect 一括実行ランナー

使い方:
    python skills/tax-collect/run.py --year 2025
    python skills/tax-collect/run.py --year 2025 --sites sbi rakuten
    python skills/tax-collect/run.py --year 2025 --force
    python skills/tax-collect/run.py --year 2025 --fail-fast

デフォルト: 収集済み（nenkantorihikihokokusho.json 存在）はスキップ。
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

# resolve() で絶対パス化。parents[0]=skills/, parents[1]=project root
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


def is_collected(category: str, code: str, year: int) -> bool:
    json_path = (
        _PROJECT_ROOT / "data" / "incomes" / category
        / code / str(year) / "nenkantorihikihokokusho.json"
    )
    return json_path.exists() and json_path.stat().st_size > 0


def _print_header(label: str) -> None:
    print(f"\n{'='*60}")
    print(label)
    print(f"{'='*60}")


def run_site(code: str, name: str, year: int) -> Literal["ok", "error", "missing"]:
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


def _prompt_android(code: str, name: str) -> bool:
    """Enterで実行、s で スキップ。非対話(EOF)はスキップ側。戻り: True=実行, False=スキップ"""
    _print_header(f"[{code}] {name} - Android収集")
    print("  1. デバイスをUSBで接続")
    print("  2. USBデバッグを有効化（開発者オプション）")
    print("\nEnterで収集開始、Sキー+Enterでスキップ: ", end="", flush=True)
    try:
        ans = input().strip().lower()
    except EOFError:
        print("\n[非対話実行] 実行")
        return True
    return ans != "s"


def main() -> None:
    parser = argparse.ArgumentParser(description="tax-collect 一括実行ランナー")
    parser.add_argument(
        "--year", type=int, default=_CURRENT_YEAR - 1,
        help=f"対象年度（デフォルト: {_CURRENT_YEAR - 1}）",
    )
    parser.add_argument("--sites", nargs="+", metavar="CODE")
    parser.add_argument("--force", action="store_true", help="収集済みでも再実行")
    parser.add_argument("--fail-fast", action="store_true", dest="fail_fast")
    args = parser.parse_args()

    if not (1900 <= args.year <= _CURRENT_YEAR):
        print(f"[ERROR] 年度が範囲外: {args.year}")
        sys.exit(1)

    accounts = load_accounts()

    if args.sites:
        for code in args.sites:
            if not _VALID_CODE.match(code):
                print(f"[ERROR] 不正なコード: {code}")
                sys.exit(1)
        codes = list(dict.fromkeys(args.sites))  # 重複除去・順序保持
        unknown = set(codes) - {a["code"] for a in accounts}
        if unknown:
            print(f"[ERROR] 不明な会社コード: {', '.join(sorted(unknown))}")
            sys.exit(1)
        account_map = {a["code"]: a for a in accounts}
        accounts = [account_map[c] for c in codes]

    if not accounts:
        print("[WARN] 実行対象サイトなし")
        sys.exit(0)

    results: dict[str, list[str]] = {"ok": [], "error": [], "missing": [], "skip": [], "done": []}
    stop = False

    try:
        for account in accounts:
            if stop:
                break
            code = account["code"]
            name = account["name"]
            category = account.get("category", "securities")
            collection = account.get("collection")

            if collection not in ("auto", "android"):
                print(f"\n[SKIP] {code} ({name}): 未対応の収集方式 ({collection!r})")
                results["skip"].append(code)
                continue

            if not args.force and is_collected(category, code, args.year):
                print(f"\n[DONE] {code} ({name}): 収集済み（スキップ）")
                results["done"].append(code)
                continue

            if collection == "android":
                if not _prompt_android(code, name):
                    results["skip"].append(code)
                    continue

            status = run_site(code, name, args.year)
            results[status].append(code)

            if status in ("error", "missing") and args.fail_fast:
                print(f"\n[FAIL-FAST] {code} でエラー → 停止")
                stop = True

    except KeyboardInterrupt:
        print("\n[中断] Ctrl+C")

    if not results["ok"] and not results["error"] and not results["missing"]:
        print("\n[WARN] 実行した社なし（全件 収集済みまたはスキップ）")

    print(f"\n{'='*60}")
    print("=== 収集結果 ===")
    print(f"  OK      : {', '.join(results['ok']) or 'なし'}")
    print(f"  ERROR   : {', '.join(results['error']) or 'なし'}")
    print(f"  MISSING : {', '.join(results['missing']) or 'なし'}  ← スクリプト未作成")
    print(f"  DONE    : {', '.join(results['done']) or 'なし'}  ← 収集済みスキップ")
    print(f"  SKIP    : {', '.join(results['skip']) or 'なし'}  ← 手動/未対応")
    print(f"{'='*60}")

    _report_pdf_queue()

    if results["error"] or results["missing"]:
        sys.exit(1)


def _report_pdf_queue() -> None:
    """PDF→JSON変換キューの登録件数を表示。実変換は convert.py で行う。"""
    queue_dir = _PROJECT_ROOT / "output" / "converting"
    if not queue_dir.exists():
        return
    queues = sorted(queue_dir.glob("*.queue"))
    err_queues = sorted(queue_dir.glob("*.queue.err"))
    if not queues and not err_queues:
        return
    if queues:
        print(f"\n[QUEUE] PDF→JSON変換キュー: {len(queues)}件")
        for p in queues:
            print(f"  - {p.stem}")
    if err_queues:
        print(f"\n[QUEUE] 前回失敗キュー: {len(err_queues)}件（.queue にリネームで再実行可）")
        for p in err_queues:
            print(f"  - {p.name}")
    print(f"[QUEUE] 変換実行: python skills/tax-collect/convert.py --year <YEAR>")


if __name__ == "__main__":
    main()
