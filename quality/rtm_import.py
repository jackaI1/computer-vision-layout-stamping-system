"""Read and write requirement files in CSV and ReqIF, and keep IDs stable.

A requirement has these fields: ``id``, ``title``, ``text``, ``risk``, ``code``
(design elements, ``path::symbol``) and ``tests`` (test patterns). ``code`` and
``tests`` hold several values separated by ``;``.

CSV files use a header row with those column names. ReqIF is the OMG exchange
format used by IBM DOORS and similar tools: an XML file whose ``SPEC-OBJECT``
elements are the requirements and whose ``ATTRIBUTE-VALUE-*`` elements hold the
fields. Both formats carry the requirement's *source* key (the ``id`` column or
ReqIF ``ID`` attribute). :func:`assign_ids` maps each source key to a project
ID such as ``REQ-29`` and keeps that mapping in a registry file, so an ID never
changes once given and a retired ID is never reused.
"""
from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ("id", "title", "text", "risk", "code", "tests")
REQUIRED = ("id", "title", "text", "risk")
REQIF_NS = "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"
_NUMBERED = re.compile(r"^REQ-(\d+)$")


class RequirementFileError(ValueError):
    """A requirement file that is malformed or incomplete."""


def _split(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(";") if v.strip()]


def _record(raw: dict, where: str) -> dict:
    for name in REQUIRED:
        if not str(raw.get(name) or "").strip():
            raise RequirementFileError(f"{where}: requirement is missing '{name}'")
    return {
        "id": str(raw["id"]).strip(),
        "title": str(raw["title"]).strip(),
        "text": str(raw["text"]).strip(),
        "risk": str(raw["risk"]).strip(),
        "code": _split(raw.get("code")),
        "tests": _split(raw.get("tests")),
    }


def _no_duplicates(records: list[dict], where: str) -> list[dict]:
    seen: set[str] = set()
    for rec in records:
        if rec["id"] in seen:
            raise RequirementFileError(f"{where}: duplicate source id {rec['id']}")
        seen.add(rec["id"])
    return records


# --- CSV -------------------------------------------------------------------

def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise RequirementFileError(f"{path.name}: missing column(s) {', '.join(missing)}")
        rows = [_record(row, f"{path.name} line {n}") for n, row in enumerate(reader, start=2)]
    return _no_duplicates(rows, path.name)


def write_csv(records: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(FIELDS)
        for rec in records:
            writer.writerow([rec["id"], rec["title"], rec["text"], rec["risk"],
                             ";".join(rec.get("code", [])), ";".join(rec.get("tests", []))])


# --- ReqIF -----------------------------------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_reqif(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()  # stdlib parser; the file is a local, trusted export
    if _local(root.tag) != "REQ-IF":
        raise RequirementFileError(f"{path.name}: not a ReqIF file")
    # Attribute definitions map an identifier to the field name, e.g. AD-1 -> "title".
    names = {}
    for el in root.iter():
        if _local(el.tag).startswith("ATTRIBUTE-DEFINITION-") and el.get("IDENTIFIER"):
            names[el.get("IDENTIFIER")] = (el.get("LONG-NAME") or "").strip().lower()
    records = []
    for obj in (el for el in root.iter() if _local(el.tag) == "SPEC-OBJECT"):
        raw: dict[str, str] = {}
        for value in (v for v in obj.iter() if _local(v.tag).startswith("ATTRIBUTE-VALUE-")):
            ref = next((r for r in value.iter() if _local(r.tag).endswith("-REF")), None)
            if ref is None or ref.text is None:
                continue
            name = _LABEL_TO_FIELD.get(names.get(ref.text.strip(), ""), "")
            text = value.get("THE-VALUE")
            if text is None:
                inner = next((c for c in value.iter() if _local(c.tag) == "THE-VALUE"), None)
                text = "".join(inner.itertext()) if inner is not None else ""
            raw[name] = text
        raw.setdefault("id", obj.get("LONG-NAME") or obj.get("IDENTIFIER") or "")
        records.append(_record(raw, f"{path.name} object {obj.get('IDENTIFIER')}"))
    return _no_duplicates(records, path.name)


_REQIF_ATTRS = (("id", "ID"), ("title", "Title"), ("text", "Text"), ("risk", "Risk"),
                ("code", "Design element"), ("tests", "Test"))
# Attribute names (lower case) a ReqIF file may use, mapped to our field names.
_LABEL_TO_FIELD = {"id": "id", "title": "title", "text": "text", "risk": "risk",
                   "design element": "code", "design elements": "code",
                   "test": "tests", "tests": "tests"}


def write_reqif(records: list[dict], path: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ET.register_namespace("", REQIF_NS)
    q = lambda tag: f"{{{REQIF_NS}}}{tag}"  # noqa: E731
    doc = ET.Element(q("REQ-IF"))
    header = ET.SubElement(ET.SubElement(doc, q("THE-HEADER")), q("REQ-IF-HEADER"),
                           IDENTIFIER="HDR-1")
    ET.SubElement(header, q("CREATION-TIME")).text = now
    ET.SubElement(header, q("REQ-IF-TOOL-ID")).text = "computer-vision-layout-stamping-system"
    ET.SubElement(header, q("REQ-IF-VERSION")).text = "1.0"
    ET.SubElement(header, q("SOURCE-TOOL-ID")).text = "quality/rtm.py"
    ET.SubElement(header, q("TITLE")).text = path.stem
    content = ET.SubElement(ET.SubElement(doc, q("CORE-CONTENT")), q("REQ-IF-CONTENT"))
    datatypes = ET.SubElement(content, q("DATATYPES"))
    ET.SubElement(datatypes, q("DATATYPE-DEFINITION-STRING"), IDENTIFIER="DT-STRING",
                  **{"LONG-NAME": "String", "MAX-LENGTH": "100000"})
    spec_types = ET.SubElement(content, q("SPEC-TYPES"))
    sot = ET.SubElement(spec_types, q("SPEC-OBJECT-TYPE"), IDENTIFIER="SOT-REQ",
                        **{"LONG-NAME": "Requirement"})
    attrs = ET.SubElement(sot, q("SPEC-ATTRIBUTES"))
    for n, (_, label) in enumerate(_REQIF_ATTRS, start=1):
        ad = ET.SubElement(attrs, q("ATTRIBUTE-DEFINITION-STRING"), IDENTIFIER=f"AD-{n}",
                           **{"LONG-NAME": label})
        typ = ET.SubElement(ad, q("TYPE"))
        ET.SubElement(typ, q("DATATYPE-DEFINITION-STRING-REF")).text = "DT-STRING"
    objects = ET.SubElement(content, q("SPEC-OBJECTS"))
    for rec in records:
        obj = ET.SubElement(objects, q("SPEC-OBJECT"), IDENTIFIER=f"SO-{rec['id']}",
                            **{"LONG-NAME": rec["id"]})
        values = ET.SubElement(obj, q("VALUES"))
        for n, (field, _) in enumerate(_REQIF_ATTRS, start=1):
            value = rec[field] if isinstance(rec.get(field), str) else ";".join(rec.get(field, []))
            av = ET.SubElement(values, q("ATTRIBUTE-VALUE-STRING"), **{"THE-VALUE": value})
            definition = ET.SubElement(av, q("DEFINITION"))
            ET.SubElement(definition, q("ATTRIBUTE-DEFINITION-STRING-REF")).text = f"AD-{n}"
        typ = ET.SubElement(obj, q("TYPE"))
        ET.SubElement(typ, q("SPEC-OBJECT-TYPE-REF")).text = "SOT-REQ"
    ET.SubElement(content, q("SPECIFICATIONS"))
    ET.indent(doc)
    ET.ElementTree(doc).write(path, encoding="utf-8", xml_declaration=True)


# --- dispatch and stable IDs -------------------------------------------------

def load(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        return read_csv(path)
    if path.suffix.lower() in (".reqif", ".xml"):
        return read_reqif(path)
    raise RequirementFileError(f"{path.name}: unsupported file type (use .csv or .reqif)")


def numbered(ids) -> int:
    """Largest N in ``REQ-N`` among ``ids`` (0 when there is none)."""
    return max((int(m.group(1)) for i in ids if (m := _NUMBERED.match(i))), default=0)


def assign_ids(records: list[dict], registry: dict, existing_ids: set[str]) -> list[dict]:
    """Give each record a stable project ID.

    ``registry`` is ``{"next": int, "ids": {source_key: project_id}}`` and is
    updated in place. A source key seen before keeps its ID. A source key equal
    to an existing project ID keeps that ID. Anything else gets the next number.
    Numbers are never handed out twice, so retired IDs stay retired.
    """
    ids: dict[str, str] = registry.setdefault("ids", {})
    registry.setdefault("next", 0)
    registry["next"] = max(registry["next"], numbered(existing_ids), numbered(ids.values()))
    out = []
    for rec in records:
        key = rec["id"]
        if key not in ids:
            if key in existing_ids:
                ids[key] = key
            else:
                registry["next"] += 1
                ids[key] = f"REQ-{registry['next']:02d}"
        out.append({**rec, "source_id": key, "id": ids[key]})
    return out
