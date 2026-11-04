# Verification & test results — V4.1

## Result of this package's actual test run

**44 passed / 0 failed / 0 errors / 0 skipped** in **71.33 seconds** on **Python 3.13.5 / Linux x86_64**, executed on 2026-11-04.

```bash
python -m pytest tests/test_v4.py tests/test_v3.py -v --durations=10 --junitxml=docs/test-results.xml
```

The results are preserved as [JUnit XML](test-results.xml) (one entry for every executed case) and [machine-readable summary](verification-summary.json). **This is a real executed result**, not merely the presence of test files. The GitHub Actions workflow has now run successfully on Python 3.11; check its latest status for subsequent commits.

### Coverage

| Test file | Cases | Validated classes |
|---|---:|---|
| `tests/test_v4.py` | 15 | Parcel/building/unit hierarchy, garage and lawn, independent flats, cores and lifts, duplex identification, mixed-use, rejection of invalid requests, API validation, exported SVG/DXF, alternatives, AI-key handling and blocked doors |
| `tests/test_v3.py` | 29 | Geometry variations, room shapes, columns/shafts, door/window clearances, furniture, export, regression of known V2 errors, legacy API and edge cases |
| **Total** | **44** | **All passed in this run** |

Additional checks completed: `python -m compileall -q app.py architect` and `node --check static/v4.js`, with no reported syntax errors. The original catalog PDF was checked and contains 92 A3 pages. The included screenshots are actual V4.1 Chromium-rendered output from the previous interface verification—not fabricated UI mockups.

### Architectural dataset / examples verification

The [35-case catalog](EXAMPLE_CATALOG.md) was generated using the V4 Python engine before the V4.1 UI refresh. All 35 passed its *implemented error* checks; **27 scenarios contain architectural warnings**, including 25 with modeled external-window concerns. Those are **known limitations**, not validation successes of every architectural requirement.

## Run the suite yourself

```bash
python -m pip install -r requirements.txt
python -m pytest tests/test_v4.py tests/test_v3.py -v
```

You may also use `python -m pytest tests/test_v4.py -q` for a shorter output. GitHub Actions is configured in `.github/workflows/tests.yml` to run the retained tests and upload JUnit XML output even when they fail.

## What these tests do *not* prove

- No verified construction-code compliance, approval of MEP/structural/fire/accessibility design or real-world building performance.
- No universal proof that generated layouts are visually attractive, furniture arrangements optimal, or all entrances accessible.
- No new 3D renderer or complete editable CAD topology.
- No independently verified live Gemini API call. The no-key error response is tested.
- This test run covers Python logic/APIs; it is *not* a new full-browser E2E suite. The V4.1 interface screenshots and interaction checks were captured separately during the earlier UI redesign, as described in `UI_V4_1_AUDIT.md`.

## Published-file integrity verification

The CI workflow now additionally checks the actual repository files: decoding every PNG screenshot, parsing SVG/XML and JSON, auditing DXF files, opening the combined 92-page PDF, confirming all 35 case directories/indexes, and resolving local Markdown links. It also checks JavaScript syntax. This helps catch broken uploads and references; it does not replace live end-to-end browser tests or professional architectural review.

Run locally after installing requirements plus `Pillow` and `pypdf`:

```bash
python -m pip install Pillow pypdf
python scripts/verify_repo_assets.py
```
