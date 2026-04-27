"""取引なし向け ゼロ値 nenkantorihikihokokusho.json 生成スクリプト

使い方:
    python skills/tax-collect/create_zero_json.py --year 2025
    python skills/tax-collect/create_zero_json.py --year 2025 --codes sawakami tsumiki
    python skills/tax-collect/create_zero_json.py --year 2025 --force

デフォルト: JSON未存在の全社を対象。
--codes: 特定社のみ。
--force: 既存JSONを上書き。
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
_CURRENT_YEAR = datetime.now().year


def load_registry() -> list[dict]:
    data = json.loads(_REGISTRY.read_text(encoding="utf-8"))
    return data["securities"]


def json_path(code: str, year: int) -> Path:
    return (
        _PROJECT_ROOT / "data" / "incomes" / "securities"
        / code / str(year) / "nenkantorihikihokokusho.json"
    )


def build_zero(site: dict, year: int) -> dict:
    return {
        "company": site["name"],
        "code": site["code"],
        "year": year,
        "document_type": "特定口座年間取引報告書",
        "source": "manual_zero",
        "account": {
            "口座種別": None,
            "譲渡所得源泉徴収": None,
            "配当所得源泉徴収": None,
            "開設日": None,
        },
        "譲渡": {
            "取引件数_上場株式等": 0,
            "取引件数_信用等": 0,
            "取引件数_一般株式等": 0,
            "上場株式等": {
                "譲渡の対価の額": 0,
                "取得費及び譲渡に要した費用の額等": 0,
                "差引金額_譲渡損益": 0,
            },
            "一般株式等": {
                "譲渡の対価の額": 0,
                "取得費及び譲渡に要した費用の額等": 0,
                "差引金額_譲渡損益": 0,
            },
            "損益通算後": {
                "所得控除の額の合計額": 0,
                "差引所得税額": 0,
                "翌年繰越損失額": 0,
            },
            "合計": {
                "課税標準": 0,
                "取得費等": 0,
                "差引損益": 0,
            },
        },
        "配当等": {
            "上場株式の配当等": {
                "配当等の額": 0,
                "所得税": 0,
                "復興特別所得税": 0,
                "地方税": 0,
            },
            "特定株式投資信託の収益の分配等": {
                "配当等の額": 0,
                "所得税": 0,
                "復興特別所得税": 0,
                "地方税": 0,
            },
            "一般株式等の配当等": {
                "配当等の額": 0,
                "所得税": 0,
                "復興特別所得税": 0,
                "地方税": 0,
            },
            "投資信託等の収益の分配等": {
                "配当等の額": 0,
                "所得税": 0,
                "復興特別所得税": 0,
                "地方税": 0,
            },
            "非居住者等への配当等": {
                "配当等の額": 0,
                "所得税": 0,
                "復興特別所得税": 0,
                "地方税": 0,
            },
            "外国株式等の配当等": {
                "配当等の額": 0,
                "外国所得税": 0,
            },
            "NISA口座内の配当等": {
                "配当等の額": 0,
            },
            "合計": {
                "配当等の額": 0,
                "所得税_源泉徴収税額": 0,
                "復興特別所得税": 0,
                "地方税": 0,
                "納付税額": 0,
            },
        },
        "NISA": {
            "譲渡等": {
                "譲渡の対価の額": 0,
                "取得費等": 0,
            },
        },
        "源泉徴収税額合計": {
            "所得税": 0,
            "復興特別所得税": 0,
        },
        "証券会社": {
            "名称": site["name"],
            "法人番号": None,
        },
        "raw_files": [],
        "collected_at": datetime.now().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ゼロ値 JSON 生成")
    parser.add_argument(
        "--year", type=int, default=_CURRENT_YEAR - 1,
        help=f"対象年度（デフォルト: {_CURRENT_YEAR - 1}）",
    )
    parser.add_argument("--codes", nargs="+", metavar="CODE", help="対象会社コード（省略時: JSON未存在の全社）")
    parser.add_argument("--force", action="store_true", help="既存JSONを上書き")
    args = parser.parse_args()

    sites = load_registry()
    site_map = {s["code"]: s for s in sites}

    _TOKUTEI = "特定口座年間取引報告書"

    if args.codes:
        unknown = set(args.codes) - set(site_map)
        if unknown:
            print(f"[ERROR] 不明なコード: {', '.join(sorted(unknown))}")
            sys.exit(1)
        targets = [site_map[c] for c in args.codes]
        non_tokutei = [s for s in targets if s.get("document_type") != _TOKUTEI]
        if non_tokutei:
            for s in non_tokutei:
                print(f"[SKIP] {s['code']} ({s['name']}): document_type={s.get('document_type')!r} - 特定口座外のため対象外")
            targets = [s for s in targets if s.get("document_type") == _TOKUTEI]
    else:
        targets = [
            s for s in sites
            if s.get("document_type") == _TOKUTEI
            and not json_path(s["code"], args.year).exists()
        ]

    if not targets:
        print("[INFO] 対象社なし（全社 JSON 存在）")
        sys.exit(0)

    created, skipped = [], []
    for site in targets:
        code = site["code"]
        out = json_path(code, args.year)

        if out.exists() and not args.force:
            print(f"[SKIP] {code}: 既存 ({out})")
            skipped.append(code)
            continue

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(build_zero(site, args.year), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[OK]   {code}: {out}")
        created.append(code)

    print(f"\n作成: {', '.join(created) or 'なし'}  スキップ: {', '.join(skipped) or 'なし'}")


if __name__ == "__main__":
    main()
