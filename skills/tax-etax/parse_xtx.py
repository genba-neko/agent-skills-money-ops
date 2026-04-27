"""e-Tax xtx → 素 JSON 変換 CLI。

入力: data/etax/<year>/raw/JyusinData*.xtx
出力: data/etax/<year>/normalized.json

使い方:
    python skills/tax-etax/parse_xtx.py --year 2024
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows コマンドプロンプト cp932 対策
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

_SKILLS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SKILLS_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from money_ops.etax.parser import parse  # noqa: E402
from money_ops.etax.labeler import apply_labels, coverage_stats  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="e-Tax xtx → 素 JSON 変換")
    ap.add_argument("--year", type=int, required=True, help="申告対象年 (例: 2024)")
    ap.add_argument("--with-labels", action="store_true",
                    help="mapping を引いて labeled.json も併せて出力")
    args = ap.parse_args()

    raw_dir = _PROJECT_ROOT / "data" / "etax" / str(args.year) / "raw"
    if not raw_dir.exists():
        print(f"[ERR] {raw_dir} なし。xtx を配置してください。", file=sys.stderr)
        sys.exit(1)

    xtxs = sorted(raw_dir.glob("*.xtx"))
    if not xtxs:
        print(f"[ERR] {raw_dir} に xtx ファイルなし", file=sys.stderr)
        sys.exit(1)

    if len(xtxs) > 1:
        print(f"[WARN] xtx 複数 ({len(xtxs)}件) 検出 → 最新 {xtxs[-1].name} を採用", file=sys.stderr)

    xtx = xtxs[-1]
    report = parse(xtx)
    out_path = _PROJECT_ROOT / "data" / "etax" / str(args.year) / "normalized.json"
    report.write(out_path)

    def _depth_count(obj):
        """dict/list を再帰して leaf (str) 数を数える。"""
        if isinstance(obj, dict):
            return sum(_depth_count(v) for v in obj.values())
        if isinstance(obj, list):
            return sum(_depth_count(x) for x in obj)
        return 1 if obj else 0

    print(f"[OK] {xtx.name}")
    print(f"  tax_type      : {report.tax_type}")
    print(f"  form_version  : {report.form_version}")
    print(f"  forms         : {len(report.forms)}")
    print(f"  attachments   : {len(report.attachments)}")
    print(f"  sofusho       : {'あり' if report.sofusho else 'なし'}")
    print(f"  output        : {out_path}")
    print()
    print("  帳票内訳 (leaf 値数):")
    for f in report.forms:
        print(f"    {f.form_id:30s}  leaves={_depth_count(f.fields):4d}")
    if report.attachments:
        print("\n  添付書類:")
        for f in report.attachments:
            print(f"    {f.form_id:40s}  ({f.form_code})  leaves={_depth_count(f.fields):4d}")

    if args.with_labels:
        import json as _json
        normalized = _json.loads(out_path.read_text(encoding="utf-8"))
        labeled = apply_labels(normalized)
        labeled_path = out_path.with_name("labeled.json")
        labeled_path.write_text(
            _json.dumps(labeled, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        stats = coverage_stats(normalized)
        t = stats["total"]
        pct = 100 * t["hit"] / (t["hit"] + t["miss"]) if (t["hit"] + t["miss"]) else 0
        print(f"\n[OK] labeled JSON: {labeled_path}")
        print(f"  mapping カバレッジ: {t['hit']}/{t['hit']+t['miss']} ({pct:.1f}%)")
        for form_id, s in stats["by_form"].items():
            mark = "✓" if s["miss"] == 0 else "△"
            print(f"    {mark} {form_id:30s} hit={s['hit']:4d} miss={s['miss']:3d}")


if __name__ == "__main__":
    main()
