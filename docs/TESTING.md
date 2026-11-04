# Verification & test results — V4.1

## Result of this package's actual test run

**44 passed / 0 failed / 0 errors / 0 skipped** in **71.33 seconds** on **Python 3.13.5 / Linux x86_64**, executed on 2026-11-04.

```bash
python -m pytest tests/test_v4.py tests/test_v3.py -v --durations=10 --junitxml=docs/test-results.xml
```

The results are preserved as [JUnit XML](test-results.xml) (one entry for every executed case) and [machine-readable summary](verification-summary.json). **This is a real executed result**, not merely the presence of test files. The separate GitHub Actions workflow will run on Python 3.11 when the repo is published; that CI environment has **not yet been run**.

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
