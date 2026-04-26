"""ブラウザプロファイル バックアップ・リストアツール

使い方:
    # 全 code バックアップ
    python tools/browser_profile.py backup
    # → data/browser/all_YYYY-MM-DD.zip

    # 特定 code バックアップ
    python tools/browser_profile.py backup --code sbi
    # → data/browser/sbi_YYYY-MM-DD.zip

    # 全 code リストア（最新 all_*.zip 自動選択）
    python tools/browser_profile.py restore

    # 特定 code リストア（最新 {code}_*.zip 自動選択）
    python tools/browser_profile.py restore --code sbi

    # ファイル明示指定
    python tools/browser_profile.py restore --file data/browser/sbi_2026-04-27.zip

    # 確認スキップ
    python tools/browser_profile.py restore --yes

profile 保存先: ~/.money-ops-browser/<code>/
backup 保存先: <project>/data/browser/
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PROFILE_ROOT = Path.home() / ".money-ops-browser"
_BACKUP_DIR = _PROJECT_ROOT / "data" / "browser"
_LOCK_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile")
_CODE_RE = re.compile(r"^[a-z0-9-]+$")


def _list_codes() -> list[str]:
    if not _PROFILE_ROOT.exists():
        return []
    return sorted(p.name for p in _PROFILE_ROOT.iterdir() if p.is_dir())


def _is_browser_running(code: str) -> bool:
    profile = _PROFILE_ROOT / code
    return any((profile / lf).exists() for lf in _LOCK_FILES)


def _confirm(msg: str, yes: bool) -> bool:
    if yes:
        return True
    ans = input(f"{msg} [y/N]: ").strip().lower()
    return ans in ("y", "yes")


def _backup(codes: list[str], label: str, yes: bool) -> int:
    """codes をすべて 1 つの zip にまとめて backup。"""
    today = date.today().isoformat()
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = _BACKUP_DIR / f"{label}_{today}.zip"

    running = [c for c in codes if _is_browser_running(c)]
    if running:
        print(f"[WARN] ブラウザ起動中の可能性: {', '.join(running)}")
        if not _confirm("続行しますか?", yes):
            print("[中止]")
            return 1

    if zip_path.exists():
        print(f"[INFO] 既存ファイル上書き: {zip_path}")

    print(f"[BACKUP] {len(codes)} code → {zip_path}")
    total = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for code in codes:
            src = _PROFILE_ROOT / code
            if not src.exists():
                print(f"  [SKIP] {code}: profile なし")
                continue
            count = 0
            dir_count = 0
            # ディレクトリ entry (空ディレクトリ保持) → ファイル entry
            for d in src.rglob("*"):
                if not d.is_dir():
                    continue
                arc = (Path(code) / d.relative_to(src)).as_posix() + "/"
                zf.writestr(zipfile.ZipInfo(arc), "")
                dir_count += 1
            for f in src.rglob("*"):
                if not f.is_file():
                    continue
                arc = (Path(code) / f.relative_to(src)).as_posix()
                try:
                    zf.write(f, arcname=arc)
                    count += 1
                except (OSError, PermissionError) as e:
                    print(f"  [WARN] skip {arc}: {e}")
            print(f"  [OK] {code}: {count} files, {dir_count} dirs")
            total += count

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"[DONE] {total} files, {size_mb:.1f} MB → {zip_path}")
    return 0


def _find_latest(pattern: str) -> Path | None:
    if not _BACKUP_DIR.exists():
        return None
    matches = sorted(_BACKUP_DIR.glob(pattern))
    return matches[-1] if matches else None


def _restore(zip_path: Path, code: str | None, yes: bool) -> int:
    """zip_path を ~/.money-ops-browser/ 配下に展開。

    code 指定時: zip 内の <code>/ のみ抽出。
    code 省略時: zip 内すべて抽出。
    既存 profile は上書き（事前削除）。
    """
    if not zip_path.exists():
        print(f"[ERROR] ファイルなし: {zip_path}")
        return 1

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        codes_in_zip = sorted({n.split("/", 1)[0] for n in names if "/" in n})

    if code:
        if code not in codes_in_zip:
            print(f"[ERROR] zip 内に {code} なし。含まれる code: {codes_in_zip}")
            return 1
        target_codes = [code]
    else:
        target_codes = codes_in_zip

    running = [c for c in target_codes if _is_browser_running(c)]
    if running:
        print(f"[WARN] ブラウザ起動中の可能性: {', '.join(running)}")
        if not _confirm("続行すると profile が破壊されます。続行しますか?", yes):
            print("[中止]")
            return 1

    existing = [c for c in target_codes if (_PROFILE_ROOT / c).exists()]
    if existing:
        print(f"[WARN] 既存 profile を上書きします: {', '.join(existing)}")
        if not _confirm("続行しますか?", yes):
            print("[中止]")
            return 1

    _PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"[RESTORE] {zip_path} → {_PROFILE_ROOT}")

    for c in target_codes:
        dst = _PROFILE_ROOT / c
        if dst.exists():
            shutil.rmtree(dst)
        print(f"  [OK] removed old profile: {c}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        if code:
            members = [n for n in zf.namelist() if n.startswith(f"{code}/")]
            zf.extractall(_PROFILE_ROOT, members=members)
        else:
            zf.extractall(_PROFILE_ROOT)

    print(f"[DONE] restored: {', '.join(target_codes)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="ブラウザプロファイル バックアップ・リストアツール")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_b = sub.add_parser("backup", help="profile を zip 化")
    p_b.add_argument("--code", help="特定 code のみ。省略時は全 code")
    p_b.add_argument("--yes", action="store_true", help="確認スキップ")

    p_r = sub.add_parser("restore", help="zip から profile を復元")
    p_r.add_argument("--code", help="特定 code のみ。省略時は zip 内全 code")
    p_r.add_argument("--file", help="復元元 zip ファイル明示指定")
    p_r.add_argument("--yes", action="store_true", help="確認スキップ")

    args = parser.parse_args()

    if args.code and not _CODE_RE.match(args.code):
        print(f"[ERROR] 不正な code: {args.code}")
        sys.exit(1)

    if args.cmd == "backup":
        if args.code:
            if not (_PROFILE_ROOT / args.code).exists():
                print(f"[ERROR] profile なし: {_PROFILE_ROOT / args.code}")
                sys.exit(1)
            sys.exit(_backup([args.code], args.code, args.yes))
        codes = _list_codes()
        if not codes:
            print(f"[ERROR] profile なし: {_PROFILE_ROOT}")
            sys.exit(1)
        sys.exit(_backup(codes, "all", args.yes))

    if args.cmd == "restore":
        if args.file:
            zip_path = Path(args.file)
            if not zip_path.is_absolute():
                zip_path = _PROJECT_ROOT / zip_path
        elif args.code:
            zip_path = _find_latest(f"{args.code}_*.zip")
            if not zip_path:
                print(f"[ERROR] {args.code}_*.zip が見つかりません: {_BACKUP_DIR}")
                sys.exit(1)
            print(f"[INFO] 最新 zip: {zip_path.name}")
        else:
            zip_path = _find_latest("all_*.zip")
            if not zip_path:
                print(f"[ERROR] all_*.zip が見つかりません: {_BACKUP_DIR}")
                sys.exit(1)
            print(f"[INFO] 最新 zip: {zip_path.name}")
        sys.exit(_restore(zip_path, args.code, args.yes))


if __name__ == "__main__":
    main()
