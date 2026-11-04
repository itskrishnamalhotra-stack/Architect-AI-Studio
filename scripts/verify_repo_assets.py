#!/usr/bin/env python3
"""Validate all published repository assets, generated cases, and local documentation links.

Run after: python -m pip install -r requirements.txt Pillow pypdf
"""
from __future__ import annotations

import collections
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

import ezdxf
from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
counts: collections.Counter[str] = collections.Counter()


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def verify_file(path: Path, kind: str, callback) -> None:
    try:
        callback(path)
        counts[kind] += 1
    except Exception as exc:
        errors.append(f"{path.relative_to(ROOT)}: {type(exc).__name__}: {exc}")


def verify_png(path: Path) -> None:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        image.load()
        check(image.width >= 1 and image.height >= 1, f"Empty image: {path}")


def verify_svg(path: Path) -> None:
    root = ET.parse(path).getroot()
    check(root.tag.rsplit("}", 1)[-1] == "svg", f"Not an SVG root: {path}")


def verify_dxf(path: Path) -> None:
    doc = ezdxf.readfile(path)
    auditor = doc.audit()
    check(not auditor.errors, f"DXF audit errors in {path}: {auditor.errors[:3]}")


def verify_json(path: Path) -> None:
    json.loads(path.read_text(encoding="utf-8"))


def verify_markdown_links(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(r'!?\[[^\]\n]*\]\(([^)]+)\)', text):
        target = match.group(1).split(' "')[0].split(" '")[0]
        if target.startswith(("http:", "https:", "mailto:", "#", "data:")):
            continue
        local = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not local:
            continue
        dest = (path.parent / local).resolve()
        check(dest.is_relative_to(ROOT) and dest.exists(),
              f"Broken local Markdown link in {path.relative_to(ROOT)}: {target}")
    counts["markdown"] += 1


def verify_catalog() -> None:
    base = ROOT / "showcase" / "catalog"
    manifest = json.loads((base / "catalog_manifest.json").read_text(encoding="utf-8"))
    examples = manifest["examples"]
    expected = {"villa": 11, "duplex": 3, "apartment": 14, "mixed_use": 7}
    actual = dict(collections.Counter(e["typology"] for e in examples))
    check(len(examples) == 35 and actual == expected,
          f"Catalog count mismatch: total={len(examples)}, categories={actual}")
    check(manifest.get("accepted") == 35 and manifest.get("rejected") == 0,
          "Manifest acceptance totals differ from expected 35/0")
    expected_ids = {e["id"] for e in examples}
    actual_ids = {p.name for p in base.iterdir()
                  if p.is_dir() and re.fullmatch(r"[VDAM]\d{2}", p.name)}
    check(expected_ids == actual_ids,
          f"Catalog directory IDs mismatch: missing={expected_ids-actual_ids}, extra={actual_ids-expected_ids}")
    for case in examples:
        folder = base / case["id"]
        for name in ("project.json", "report.json", "site.svg"):
            check((folder / name).is_file(), f"Missing example {case['id']}/{name}")
        for level in case.get("levels_drawn", []):
            check((folder / f"floor_{level}.svg").is_file(),
                  f"Missing generated floor {case['id']}/{level}")
    with (base / "catalog_index.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    check(len(rows) == 35, f"CSV has {len(rows)} scenarios rather than 35")
    check({r["ID"] for r in rows} == expected_ids, "CSV IDs do not match catalog examples")
    index = json.loads((base / "pdf_page_index.json").read_text(encoding="utf-8"))
    pdf = base / index["pdf_file"]
    check(pdf.is_file(), f"PDF index references missing file: {pdf.name}")
    if pdf.is_file():
        reader = PdfReader(str(pdf), strict=True)
        check(len(reader.pages) == 92, f"Catalog PDF has {len(reader.pages)} pages instead of 92")
        check(len(reader.pages) == index["total_pages"], "PDF and page-index counts disagree")
        check(all(page.get_contents() is not None for page in reader.pages),
              "At least one PDF page has no content stream")
        check(set(index["cases"]) == expected_ids, "PDF page index does not cover all catalog IDs")
        check(all(1 <= int(n) <= len(reader.pages) for n in index["cases"].values()),
              "PDF page index points outside the PDF")
        counts["pdf"] += 1
    results = ET.parse(ROOT / "docs" / "test-results.xml").getroot()
    suite = results.find("testsuite")
    check(suite is not None and suite.attrib.get("tests") == "44" and
          suite.attrib.get("failures") == "0" and suite.attrib.get("errors") == "0",
          "Preserved JUnit XML summary does not indicate 44 passing tests")
    counts["catalog_examples"] = len(examples)


def main() -> int:
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.suffix == ".json":
            verify_file(path, "json", verify_json)
        elif path.suffix == ".svg":
            verify_file(path, "svg", verify_svg)
        elif path.suffix == ".png":
            verify_file(path, "png", verify_png)
        elif path.suffix == ".dxf":
            verify_file(path, "dxf", verify_dxf)
        elif path.suffix == ".xml":
            verify_file(path, "xml", lambda p: ET.parse(p))
        elif path.suffix == ".md":
            verify_file(path, "markdown_files", verify_markdown_links)
    verify_catalog()
    print("Repository asset verification:", dict(sorted(counts.items())))
    if errors:
        print(f"FAILED: {len(errors)} issues:")
        for issue in errors:
            print(" -", issue)
        return 1
    print("PASS: all checked files parsed; catalog, PDF index and local Markdown links agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
