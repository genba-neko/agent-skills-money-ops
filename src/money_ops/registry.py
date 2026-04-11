import json
from pathlib import Path

_REGISTRY_PATH = Path(__file__).parent.parent.parent / "skills" / "tax-collect" / "registry.json"


def load_registry() -> dict:
    with open(_REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_company(code: str) -> dict:
    registry = load_registry()
    for company in registry["securities"]:
        if company["code"] == code:
            return company
    raise KeyError(f"会社コード '{code}' が registry.json に見つかりません")


def list_auto_companies() -> list[dict]:
    registry = load_registry()
    return [c for c in registry["securities"] if c["collection"] == "auto"]
