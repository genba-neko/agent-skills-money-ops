import random
import re
import time

_RE_FILENAME = re.compile(r'filename[^;=\n]*=([^;\n]*)')


def wait(lo: float = 1.0, hi: float = 3.0) -> None:
    """lo〜hi 秒のランダム待機（レート制限・BAN 対策）"""
    time.sleep(random.uniform(lo, hi))


def extract_filename(content_disposition: str, fallback: str = "") -> str:
    """Content-Disposition ヘッダからファイル名を抽出する。取得できなければ fallback を返す。"""
    m = _RE_FILENAME.search(content_disposition)
    return m.group(1).strip().strip('"\'') if m else fallback
