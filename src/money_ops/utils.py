import random
import time


def wait(lo: float = 1.0, hi: float = 3.0) -> None:
    """lo〜hi 秒のランダム待機（レート制限・BAN 対策）"""
    time.sleep(random.uniform(lo, hi))
