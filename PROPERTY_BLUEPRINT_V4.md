# Architect AI Studio V4 — Property-scale Architectural Blueprint Contract

Document status: **implemented schema and planning pipeline, revision 4.0.**

This document defines the V4 AI-to-planner-to-CAD interface. The lower-level geometry specification remains `ARCHITECTURE_BLUEPRINT.md` (V3 FloorPlan schema 1.1.0), which V4 reuses unchanged. **Neither contract certifies structural integrity, accessibility, planning permissions or compliance with any building code.**

## 1. Overall architecture and ownership

```
Natural-language project brief (optional Gemini interpreter)
    ↓  PropertyRequest: typed, reviewable parameters
Required / Forbidden / Auto feature policy
    ↓  no automatically assumed amenities
Candidate topology search
    ├─ linear zone arrangement
    ├─ irregular/L-shaped social zone
    ├─ wing/vertical-gallery arrangement (up to 2 bedrooms per unit)
    └─ opposed flats across a shared central corridor (exactly 2 flats)
    ↓  physical envelope / requested-unit feasibility
Versioned PropertyProject JSON 2.0.0
    ├─ Site boundary, access, garage, lawn, parking, pedestrian path
    ├─ Building(s) with site-space origin
    │   └─ Reusable FloorPlan 1.1.0 per building
    │       └─ Level(s) with spaces, hosted walls/openings,
    │           furniture, structure and vertical connectors
    └─ Unit ownership of each floor's spaces + common shared spaces
    ↓
Geometry + furniture + egress-adjacency checks (V3)
Property-level validation (V4)
    ├─ plot and building non-overlap
    ├─ unit-by-unit room ownership and passable entrance
    ├─ shared circulation identification
    ├─ vertical core to levels connection
    ├─ requested vs included facility decisions
    ├─ landscape / vehicle/garage geometries
    └─ exports blocked for known-invalid geometry
    ↓
Bounded ranking of accepted alternatives (relative heuristic)
    ↓
Site SVG, technical floor SVG, presentation floor SVG, native CAD DXF,
versioned JSON for subsequent 3D geometry + material conversion
```

**Source of truth:** geometry is never recovered by reading pixels from an SVG. The model is a strict JSON object. The renderer is a pure geometric view of that JSON. JSON exports are editable, and `POST /api/v4/validate` must be called before exporting modified data.

## 2. Site, buildings, levels and units

The top-level document has this structure:

```json
{
  "schema_version": "2.0.0",
  "request": { "property_type": "apartment", "plot_width_mm": 35000, "plot_depth_mm": 29000, "floors": 3, "units_per_floor": 2 },
  "site": {"boundary": [{"x": 0,"y": 0}, {"x": 35000,"y": 0}, {"x": 35000,"y": 29000}, {"x": 0,"y": 29000}], "road_edge": "south"},
  "site_areas": [ {"id":"pedestrian_path", "kind":"walkway", "label":"ENTRY WALK", "polygon": ["... actual Point objects ..."]} ],
  "buildings": [
    {
      "id": "main", "site_origin": {"x": 1200,"y":1600},
      "plan": {"schema_version":"1.1.0", "unit":"mm", "levels":["... full geometry ..."]},
      "units": [
        {"id":"U1_L0", "level_id":"L0", "kind":"residence", "space_ids":["U1_living", "U1_bedroom_1"], "entrance_opening_id":"U1_D_ENTRY"},
        {"id":"U2_L0", "level_id":"L0", "kind":"residence", "space_ids":["U2_living", "U2_bedroom_1"], "entrance_opening_id":"U2_D_ENTRY"}
      ],
      "common_space_ids": {"L0": ["COMMON_GALLERY", "CORE_LOBBY", "STAIRWELL"]}
    }
  ],
  "feature_decisions": [ {"name":"stairs", "requested":"auto", "included":true, "reason":"Multi-storey circulation"} ]
}
```

The above is **an illustrative fragment, not a complete valid file**. For a schema-valid sample including all required fields and concrete geometry, use `examples/v4_sample_property.json`. For machine-readable field definitions use `GET /api/v4/schema`. Examples include a one-level property, multi-unit buildings, multi-storey core, and mixed-use retail arcade.

All coordinates, dimensions, elevations and clearances are in **millimetres**. Each private space belongs to one unit or one common grouping, never both. `dwelling_id` ties one *duplex* residence across multiple floors. In an apartment building, a first-floor unit is not the same home as the similarly numbered unit on another floor.

Buildings have **local level coordinates** and an explicit `site_origin`, permitting independent buildings and garages on one parcel without altering their own internal CAD model. All geometry is in 2D with separate `height_mm`, `base_z_mm`, `elevation_mm`, slab thickness and material/texture fields for future 3D.

## 3. Natural-language AI contract

The optional AI must return **`PropertyRequest`** (available from `PropertyRequest.model_json_schema()` in `architect/property_models.py`). It does **not** return a picture or make unverified spatial claims. Interpret:

- Plot width/depth, property type (`villa`, `apartment`, `duplex`, `mixed_use`), floor count, independent units per floor and bedrooms per unit.
- Feature states for stairs, lift, garage, lawn and service shaft: `required`, `forbidden` or `auto`.
- Whether there are separate parking bays and an accessibility priority.
- Layout strategy: `auto`, `linear`, `irregular`, `wing`, or `opposed`.
- Explicit constraints first. If the brief lacks data, apply **clearly disclosed software defaults** and ask the user to review them. Never infer a plot survey, setback permission or structural column layout from thin air.

Do not assume a lift simply because the system supports it. Do not assume there is an indoor common lobby in a detached ground-floor house. Do not infer that four identical flats on different floors are one dwelling. Do not put the garage inside the residential module unless it is explicitly modeled as a room with an actual vehicle-access opening.

The optional Gemini step only translates the brief. The *deterministic* candidate generator and validators control accepted coordinates. The legacy AI model-to-`FloorPlan` generation API still exists at `/api/generate` for experimental direct spatial proposals and is independent of the V4 property pipeline.

## 4. Hard planning conditions

- No modeled room outside the building's footprint; no room/room overlaps and no two independent units sharing a private room.
- Each unit entrance must be a hosted passable opening connected to that unit and to an identified common space or an exterior boundary.
- Apartments with two or more homes on a level must have explicit common circulation, not just a double-drawn shared wall.
- If multiple occupied levels are present, the staircase connects all named levels; no automatic lift unless design policy selects it or the user requires it.
- Stairs and lifts are excluded when not required by the selected concept; service shafts are only included when explicitly requested in the current generator.
- Doors and glazing must remain hosted to a real wall, with measured offsets and no overlapping openings.
- Bedroom headboard placement, door swing/approach collisions, window obstruction and furniture operating clearances are checked by the underlying V3 validator.
- Site areas must be within the plot; building footprints may not overlap. Lawn, paved drive and garage must not overlap as incompatible uses. Paved walkways can cross lawn polygons as an intentional replacement of the grass surface.
- Requests that cannot fit are **rejected** with a geometric/design reason. Do not silently compress dimensions to provide a false accepted result.

## 5. Relative candidate ranking

V4 ranks several **valid** alternative topologies using a transparent **soft score**, combining modeled private usable area, circulation footprint, number of exterior windows as a daylight opportunity, and validation warning penalties. This is **not a professional aesthetic score, design competition jury, legal approval or global-optimization proof**. Distinct arrangement families are preferred over different random seeds producing essentially the same walls. If only 1–2 viable and distinct alternatives are found, return fewer than requested rather than fabricate diversity.

Preserve all nonfatal warnings for human review. `NO_EXTERNAL_WINDOW` in some adjacent apartments is especially important; a floor may pass collision checks and still require architectural rearrangement to improve daylight and ventilation.

## 6. Drawings and export

- **Site SVG:** measured plot, road edge, buildings placed at site origins, lawn, driveway, garage, parking bays, a pedestrian access path when feasible, north arrow, dimensions and title block.
- **Technical floor SVG:** wall construction hatching, hosted door leaves, swings, windows, furniture symbols, sanitary symbols, room names/areas, stair/lift/shaft symbols and dimension chains, from the existing measured renderer.
- **Presentation floor SVG:** the *same geometry* with a softer color treatment; retains dimensions and object IDs.
- **CAD DXF:** wall/door/window/furniture/core geometry and named CAD discipline layers; compatible with millimetre coordinates.
- **JSON:** strict authoritative model with multiple floors, materials, object sizes and elevations suitable for future 3D mesh creation.

## 7. Known limits and engineering responsibilities

This is an operational **schematic planning prototype**, not a commercially complete architectural CAD/BIM or structural engine. Important limitations:

1. The offline candidate search spans four **residential** spatial arrangement families and a basic indoor retail arcade; not arbitrary parcel shapes, hospitals, warehouses, courtyard mansions or optimized skyscrapers.
2. The site generator currently accepts a rectangular south-road plot; no arbitrary polygon surveyed land, contours, true georeferencing, zoning/FAR/FSI calculation or legal setback solver.
3. The layouts are searched by enumeration, **not** a mathematically complete constraint-programming/MILP/CSP optimization proof. Visual design quality still requires a qualified architect.
4. Structural columns, service shafts, stairs, lifts, accessible paths and fire compartments are **schematic geometry**. No soil, RCC/steel design, load/deflection, fire escape travel-distance, occupant-load, MEP sizing, accessibility or jurisdiction-specific code certification is performed.
5. Garages are a one-car detached concept in the current generator. Vehicle turning/swept-path analysis is not implemented. Requests for more than one car in the one-car garage are rejected rather than mislabeled as satisfied.
6. Multiple levels preserve vertically linked cores and 3D-ready dimensions but do not yet implement complete 3D objects, textures or a 3D scene renderer.
7. The Gemini brief interpreter requires a live server-side key and was not verified against the real provider in this offline release. Offline plan generation, validation and exports work without it.

**Professional review is mandatory before real construction use.**
