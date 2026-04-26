"""tax-collect PDF→JSON 変換ランナー（直列・delay付き）

使い方:
    python skills/tax-collect/convert.py --year 2025
    python skills/tax-collect/convert.py --year 2025 --codes webull mufg-esmart
    python skills/tax-collect/convert.py --retry        # *.queue.err も再対象
    python skills/tax-collect/convert.py --delay-sec 60  # 各変換後の待機秒数

動作:
    output/converting/*.queue（および --retry 時 *.queue.err）を列挙し、
    convert_worker.py を順次同期実行する。
    成功で queue 削除、失敗で <code>_<year>.queue.err にリネーム。
    各変換完了後 delay-sec 秒待機（Gemini API レート制限対策）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SKILLS_DIR.parents[1]
_QUEUE_DIR = _PROJECT_ROOT / "output" / "converting"
_WORKER = _SKILLS_DIR / "convert_worker.py"


def _load_queue(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[convert] queue 読込失敗: {path.name} ({e})")
        return None


def _list_queues(year: int | None, codes: list[str] | None, retry: bool) -> list[Path]:
    if not _QUEUE_DIR.exists():
        return []
    paths = sorted(_QUEUE_DIR.glob("*.queue"))
    if retry:
        paths += sorted(_QUEUE_DIR.glob("*.queue.err"))
    result: list[Path] = []
    for p in paths:
        data = _load_queue(p)
        if data is None:
            continue
        if year is not None and data.get("year") != year:
            continue
        if codes and data.get("code") not in codes:
            continue
        result.append(p)
    return result


def _run_one(queue_path: Path) -> bool:
    data = _load_queue(queue_path)
    if data is None:
        return False
    code = data["code"]
    year = data["year"]
    company = data["company"]
    pdf_path = data["pdf_path"]
    raw_files = data.get("raw_files", [])

    print(f"\n[convert] {code} ({company}) 開始 {datetime.now().strftime('%H:%M:%S')}")
    print(f"[convert]   PDF: {pdf_path}")
    cmd = [
        sys.executable, str(_WORKER),
        "--pdf", pdf_path,
        "--code", code,
        "--year", str(year),
        "--company", company,
    ]
    if raw_files:
        cmd += ["--raw-files", *raw_files]

    result = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)
    if result.returncode == 0:
        try:
            queue_path.unlink()
        except OSError:
            pass
        print(f"[convert] {code} 成功 → queue 削除")
        return True

    err_path = queue_path.with_suffix(".queue.err") if queue_path.suffix == ".queue" else queue_path
    if err_path != queue_path:
        try:
            queue_path.rename(err_path)
        except OSError:
            pass
    print(f"[convert] {code} 失敗 (rc={result.returncode}) → {err_path.name}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF→JSON 変換ランナー（直列）")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--codes", nargs="+", metavar="CODE")
    parser.add_argument("--retry", action="store_true", help="*.queue.err も対象")
    parser.add_argument("--delay-sec", type=int, default=30)
    args = parser.parse_args()

    queues = _list_queues(args.year, args.codes, args.retry)
    if not queues:
        print("[convert] 対象キューなし")
        return 0

    print(f"[convert] 対象 {len(queues)} 件 / 各変換後 delay={args.delay_sec}s")
    for p in queues:
        print(f"  - {p.name}")

    ok = 0
    ng = 0
    for i, q in enumerate(queues, 1):
        print(f"\n{'='*60}")
        print(f"[convert] {i}/{len(queues)}")
        print(f"{'='*60}")
        if _run_one(q):
            ok += 1
        else:
            ng += 1
        if i < len(queues):
            print(f"[convert] delay {args.delay_sec}s ...")
            time.sleep(args.delay_sec)

    print(f"\n{'='*60}")
    print(f"=== 変換結果 ===")
    print(f"  成功: {ok} / 失敗: {ng}")
    print(f"{'='*60}")
    return 0 if ng == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
