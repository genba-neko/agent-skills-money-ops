from money_ops.registry import get_company, list_auto_companies, load_registry


def test_load_registry():
    registry = load_registry()
    assert "securities" in registry
    assert len(registry["securities"]) > 0


def test_get_company_found():
    company = get_company("rakuten")
    assert company["name"] == "楽天証券"
    assert company["has_xml"] is True
    assert company["collection"] == "auto"


def test_get_company_not_found():
    import pytest
    with pytest.raises(KeyError):
        get_company("nonexistent")


def test_list_auto_companies():
    companies = list_auto_companies()
    codes = [c["code"] for c in companies]
    assert "rakuten" in codes
    assert "webull" not in codes


def test_all_companies_have_required_fields():
    registry = load_registry()
    required = {"code", "name", "site_url", "has_xml", "マイナ連携", "collection"}
    for company in registry["securities"]:
        missing = required - company.keys()
        assert not missing, f"{company['code']} にフィールドが不足: {missing}"
