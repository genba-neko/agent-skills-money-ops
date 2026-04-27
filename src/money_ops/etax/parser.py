"""e-Tax xtx (XML) を素 JSON に変換する core モジュール。

xtx は平文 UTF-8 XML。namespace 多数 (shotoku/general/kyotsu/dsig 等) だが
ローカル名 (tag の `}` 以降) のみで識別する。

帳票 (KOA020-1, KOB060-1 等) ごとに **階層 dict** に変換。
- leaf 要素: text 値
- 子持ち要素: dict
- 同名タグ複数 (繰り返し行): list

xmldsig 署名 (`<dsig:Signature>`) は出力対象外。
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"

_SKIP_NS_PREFIXES = ("dsig", "ds", "ns3", "rdf", "xsi")


def _localname(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _ns_prefix(tag: str) -> str:
    if "}" not in tag:
        return ""
    ns = tag[1:].split("}", 1)[0]
    if "/dsig" in ns or "xmldsig" in ns:
        return "dsig"
    if "/general" in ns:
        return "gen"
    if "/kyotsu" in ns:
        return "kyo"
    if "/shotoku" in ns:
        return ""        # default 扱い、prefix 不要
    if "/rdf" in ns:
        return "rdf"
    return ""


def _key(tag: str) -> str:
    prefix = _ns_prefix(tag)
    local = _localname(tag)
    return f"{prefix}:{local}" if prefix else local


def _to_obj(el: ET.Element) -> Any:
    """XML element → JSON 互換オブジェクト。

    - leaf (子なし): text (str)
    - 子持ち: dict (子の tag → 値、同名複数は list)
    - 子も text もない: 空文字
    """
    children = [c for c in el if _ns_prefix(c.tag) not in _SKIP_NS_PREFIXES]
    text = (el.text or "").strip()
    if not children:
        return text
    out: dict = {}
    for c in children:
        k = _key(c.tag)
        sub = _to_obj(c)
        if k in out:
            existing = out[k]
            if isinstance(existing, list):
                existing.append(sub)
            else:
                out[k] = [existing, sub]
        else:
            out[k] = sub
    if text:
        out["#text"] = text
    return out


@dataclass
class Form:
    form_id: str               # "KOA020-1" / "TEG70020250312230122811" 等
    form_code: str             # "KOA020" / "TEG700" 等 (id の英字prefix)
    fields: Any                # 階層 dict (leaf=str、繰り返し=list)


@dataclass
class NormalizedReturn:
    schema_version: str
    tax_type: str              # "shotoku" 等
    form_version: str          # "VR" 属性 (例 "24.0.0")
    source_file: str
    header: Any                # IT 帳票 (受信通知/受付情報)
    forms: list[Form]          # 申告書本体の各帳票
    attachments: list[Form]    # TENPU 配下の添付書類 (TEG158/TEG700/TEG830 等)
    sofusho: Any = None        # SOFUSHO (送付書/添付目録)、なければ None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def write(self, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(self.to_json(), encoding="utf-8")


def _form_code_from_id(form_id: str) -> str:
    """'KOA020-1' → 'KOA020'、'TEG70020250312...' → 'TEG700' (英字+数字3桁固定)。"""
    import re
    m = re.match(r"^([A-Z]+\d{3})", form_id)
    return m.group(1) if m else form_id


def parse(xtx_path: Path) -> NormalizedReturn:
    text = xtx_path.read_text(encoding="utf-8")
    root = ET.fromstring(text)

    # tax_type: default namespace から
    tax_type = "unknown"
    for ns in ("shotoku", "shouhi", "zoyo"):
        if f"/XSD/{ns}" in text[:500]:
            tax_type = ns
            break

    # RKO0010 (申告書本体) を探す
    rko = None
    for el in root.iter():
        if _localname(el.tag) == "RKO0010":
            rko = el
            break
    if rko is None:
        raise ValueError(f"RKO0010 not found in {xtx_path.name}")

    form_version = rko.attrib.get("VR", "")

    contents = None
    for c in rko:
        if _localname(c.tag) == "CONTENTS":
            contents = c
            break
    if contents is None:
        raise ValueError(f"CONTENTS not found in {xtx_path.name}")

    header: Any = None
    forms: list[Form] = []
    attachments: list[Form] = []
    sofusho: Any = None

    for elem in contents:
        local = _localname(elem.tag)
        eid = elem.attrib.get("id", local)

        if local == "IT":
            header = _to_obj(elem)
            continue

        if local == "TENPU":
            # TENPU 配下の各添付書類 (TEG158/TEG700/TEG830) を attachments へ
            for sub in elem:
                sub_local = _localname(sub.tag)
                sub_id = sub.attrib.get("id", sub_local)
                attachments.append(
                    Form(
                        form_id=sub_id,
                        form_code=_form_code_from_id(sub_id),
                        fields=_to_obj(sub),
                    )
                )
            continue

        if local == "SOFUSHO":
            sofusho = {"form_id": eid, "fields": _to_obj(elem)}
            continue

        forms.append(
            Form(
                form_id=eid,
                form_code=_form_code_from_id(eid),
                fields=_to_obj(elem),
            )
        )

    return NormalizedReturn(
        schema_version=SCHEMA_VERSION,
        tax_type=tax_type,
        form_version=form_version,
        source_file=xtx_path.name,
        header=header,
        forms=forms,
        attachments=attachments,
        sofusho=sofusho,
    )
