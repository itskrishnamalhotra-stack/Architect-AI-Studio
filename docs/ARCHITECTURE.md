# Architecture and design pipeline

## Architectural data layers

```text
PropertyRequest (typed input, seed, feature policies)
    ↓
Feature-policy decisions (required/auto/forbidden)
    ↓
Deterministic layout search (architect/property_search.py)
    ↓
Property generator (architect/property_generator.py)
    ├─ Site/parcel + landscape/access/parking
    ├─ Building → level(s) → private units & common space IDs
    └─ Geometry → rooms, walls, hosted openings, objects and cores
    ↓
Property & floor validators (architect/property_validate.py, validate.py)
    ↓
Candidate scoring and comparison (heuristic, no aesthetics certificate)
    ↓
Measured drawing (architect/property_render.py → SVG/DXF; browser PNG)
    ↓
JSON export (source-of-truth for future 3D)
```

The generator is **deterministic** in the software-engineering sense: the same typed request + seed + code version produces repeatable decisions where the implementation is deterministic. It is **not** a learned floor-plan model. The geometry is created from explicit programmatic coordinate rules. **Gemini is optional and limited to natural-language brief parsing** (`architect/property_ai.py`) before generation.

## Data contract

The versioned `PropertyProject` model combines parcel/site information, standalone buildings, local floor plans, independent dwelling-unit records and shared spaces. It is stricter than a flat image: rooms are polygons; walls are line segments with thickness and height; doors/windows are hosted on walls; objects have sizes/placement; stair and lift cores are modeled elements. See `PROPERTY_BLUEPRINT_V4.md` for the authoritative schema and 3D migration fields.

## Current design quality limits

1. Search enumerates programmed layouts (linear, irregular, wing and opposed where applicable). It does not optimize all imaginable footprints or solve unknown architectural programmes.
2. Scoring includes space efficiency, circulation and window opportunity. It is **not** a visual appeal or regulatory-compliance score.
3. Some rooms in generated concepts may lack adequate external windows/ventilation; the catalog records those warnings.
4. Full structural design, fire separation, access regulation, plumbing/electrical services, daylight standards and local development control rules are outside the current checks.
5. The interactive editor changes defined elements but does not yet provide a generalized topology/constraint-solver CAD editing experience.
6. An API key does not cause the deterministic engine to become an architectural-domain AI; it enables natural-language requirement interpretation only.

## REST endpoints

- `GET /api/v4/status`, `/api/v4/schema`, `/api/v4/sample`
- `POST /api/v4/alternatives` — generate candidate alternatives
- `POST /api/v4/validate` — geometry/property checks
- `POST /api/v4/render` — site or floor SVG
- `POST /api/v4/export/svg`, `/api/v4/export/dxf`
- `POST /api/v4/edit/auto-place` — bounded suggested furniture placement
- `POST /api/v4/ai-brief` — optional Gemini interpretation
- `GET /legacy` — old V3-style geometry editor
- `GET /docs` — interactive OpenAPI docs

## A sample JSON input for the alternatives endpoint

```json
{
  "property_type": "apartment",
  "plot_width_mm": 36000,
  "plot_depth_mm": 31000,
  "floors": 2,
  "units_per_floor": 2,
  "bedrooms_per_unit": 2,
  "alternatives": 3,
  "stairs": "auto",
  "lift": "forbidden",
  "garage": "forbidden",
  "lawn": "forbidden",
  "seed": 42
}
```

From `http://127.0.0.1:8000/docs`, try the endpoint with this example. The returned alternatives contain separate `project` and validation report records. Large responses are normal because geometry is explicit.
