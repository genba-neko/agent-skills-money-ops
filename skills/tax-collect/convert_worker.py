"""PDF → JSON 変換ワーカー（B案: 並列化用デタッチ実行）

使い方:
    python convert_worker.py --pdf <path> --code <code> --year <year> \
        --company <company> [--raw-files name1 name2 ...]

動作:
    - 起動直後に lock ファイル output/converting/<code>_<year>.lock を作成
    - docling 経由 PDF→JSON 変換
    - 結果を data/incomes/securities/<code>/<year>/nenkantorihikihokokusho.json に保存
    - ハートビート: 10秒ごとに「[CONVERT][<code>] 経過Xs」を stderr に出す
    - 終了時（成功・失敗問わず）lock ファイルを削除

run.py から detach 起動され、tax-collect 全社走行と並列に動作する。
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from pathlib import Path

_LOCK_DIR = Path("output") / "converting"


def _heartbeat(code: str, stop_event: threading.Event, interval: int = 10) -> None:
    start = time.time()
    while not stop_event.wait(interval):
        elapsed = int(time.time() - start)
        print(f"[CONVERT][{code}] 変換中... 経過{elapsed}s", file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--code", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--raw-files", nargs="*", default=[])
    args = parser.parse_args()

    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = _LOCK_DIR / f"{args.code}_{args.year}.lock"
    lock_path.write_text(f"{args.pdf}\n", encoding="utf-8")

    stop_event = threading.Event()
    hb = threading.Thread(target=_heartbeat, args=(args.code, stop_event), daemon=True)
    hb.start()

    rc = 0
    try:
        print(f"[CONVERT][{args.code}] 開始: {args.pdf}", file=sys.stderr, flush=True)
        from money_ops.converter.pdf_to_json import convert_pdf_to_json

        data = convert_pdf_to_json(
            pdf_path=args.pdf,
            company=args.company,
            code=args.code,
            year=args.year,
            raw_files=args.raw_files,
        )

        out_dir = Path("data") / "incomes" / "securities" / args.code / str(args.year)
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "nenkantorihikihokokusho.json"
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"[CONVERT][{args.code}] 完了: {json_path}", file=sys.stderr, flush=True
        )
    except Exception as e:
        rc = 1
        print(f"[CONVERT][{args.code}] エラー: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
    finally:
        stop_event.set()
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass

    return rc


if __name__ == "__main__":
    sys.exit(main())
