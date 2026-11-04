# ARCHITECT AI STUDIO — MACHINE BLUEPRINT CONTRACT v1.1.0

**Purpose:** Shared instructions for the architectural design model, the AI generating it, the geometry validator, the SVG/DXF renderer, and a later 3D/BIM converter.

**Normative model:** `architect/models.py`, exposed at `GET /api/schema`. This file defines the *meaning* and placement constraints of schema fields. If a model field name differs from this explanatory document, the programmatic JSON Schema takes priority; do **not** invent alternate spellings. All AI results must be ONE complete schema-valid `FloorPlan` object. An image, free-form SVG, HTML, markdown table or arbitrary code is not a valid canonical output.

**Safety status:** Schematic/design-research concepts only. Validation is limited to explicitly implemented checks. The resulting plans are **not construction drawings, structural designs, permit plans, accessibility certifications, fire/egress analyses, or assurances of any local building-code compliance**. Required local rules must be separately researched, parameterized, independently checked, and reviewed by qualified professionals.

## 1. Units, geometry and hierarchy

- All coordinates and dimensions are floating-point **millimetres**, not metres, feet, pixels or strings; no NaN/Infinity. Each point is `{ "x": 1250, "y": 7200 }`.
- The origin is upper left. Positive X points right; positive Y points down. The later 3D coordinate system uses positive Z upward, with each level's `elevation_mm` and each object/core's `base_z_mm` added to the global Z placement.
- Floor plans are nested: `FloorPlan → levels[] → spaces[], walls[], openings[], objects[], built_elements[], vertical_connectors[], annotations[], dimensions[]`.
- `schema_version = "1.1.0"` for new output. The engine can read legacy `1.0.0` data to test or migrate it, but compatibility does **not** mean previously poor layouts pass V3 checks.
- A `Space.polygon` may have **three or more boundary vertices**, including concave/L/T-shaped rooms. Vertex order must form a **simple polygon**. Do not repeat the first vertex at the end. `Space.holes[]` defines genuine room voids such as planted courtyards or excluded internal cores. `Level.footprint_holes[]` defines excluded building/site floor regions. Holes must be topologically valid and must not be silently repaired.
- Walls are explicit, straight centerline segments with unique IDs, physical thickness/height and optional material. Shared physical walls must be created **once**, not duplicated from both rooms. Where lines intersect, split/nodalize so no duplicate overlapping wall paths remain.
- Every entity's `id` must be unique **within its level**, across every collection. Material IDs must be globally unique. A core serving multiple levels can use the same logical ID on different levels; its vertical connection must explicitly reference the levels it serves.
- All polygons, object footprints and opening offsets are numeric source geometry. The renderer does not infer construction geometry from symbol artwork. Architectural dimensions are calculated from measured source coordinates.

## 2. Architectural entities and how to use them

### `Space`: named usable spatial region

Use `kind` values such as `bedroom`, `living`, `kitchen`, `bathroom`, `toilet`, `corridor`, `study`, `stairwell`, `lift_lobby`, `shaft`, `utility`, `balcony`, `garage`, `office`. Spaces are the semantic zones used to check room allocation, access and fixture placement. A shaft or atrium occupies a designed region but is not traversable ordinary floor space. Specify floor/wall/ceiling finishes and clear height when known. A `Space` can be L-shaped or contain holes; **never reduce everything to rectangles**.

### `Wall`: physical boundary

Each wall has `start`, `end`, `thickness_mm`, `height_mm`, `base_z_mm`, `kind`, `structural`, material references and optional fire-rating metadata. Model uninterrupted physical runs once. A wall marked `structural: true` is **only an intention**; no engineer has checked its capacity. Do not use the exterior footprint outline as proof of a load-bearing solution.

### `Opening`: a hosted void in a wall

Each opening references **one** real `host_wall_id`. `offset_mm` is measured from the host wall's `start` along the centerline; `width_mm` is the width of the cut in that wall, with height/sill in Z. The wall renderer must subtract the precise cut. Door leaf, hinge and `swing` determine the complete swept sector. Windows have real sill/heights. Do not put doors outside their wall spans, make two openings overlap, or place tall wardrobes across windows.

### `PlacedObject`: typed furniture, sanitary and MEP object

Each object includes numeric center X/Y, dimensions `width_mm`, `depth_mm`, `height_mm`, rotation and base Z, plus material/asset references for future 3D. `space_id` identifies its room (if omitted, the validator attempts an unambiguous geometric lookup). Its canonical rectangle describes its actual body, not its text label. A bed symbol may render pillows/blanket but **those visuals do not change physical dimensions**.

For placement semantics, **local -Y is the BACK/headboard side; local +Y is the FRONT/operation side**, rotated using `rotation_degrees`. `placement` distinguishes `freestanding`, `wall_anchored`, `built_in` and `fixture`. `front_clearance_mm` is an optional explicit required working zone. Use real 3D height to reason about vertical overlap with windows; a wardrobe can block a window even when its floor-plan footprint appears harmless.

### `BuiltElement`: structure or excluded service volume

Use this independently typed collection for `column`, `pier`, `shaft`, `duct`, `lightwell`, `atrium` or `void`. Its shape is an **arbitrary polygon**, not only a circle/rectangle (circle approximations can use multiple vertices). `height_mm`, `base_z_mm`, material and attributes are preserved for later extrusion. A shaft is not a wardrobe; a column may protrude into usable floor area and must block object placement. Do not use the legacy `PlacedObject(kind="column")` for new projects.

### `VerticalConnector`: multi-floor circulation/core

Use `kind: stair | lift | ramp | escalator` with an explicit polygon, `serves_level_ids`, and an optional door/opening reference. A stair should have `step_count`, `rise_mm`, `going_mm` and real landing polygons. A lift should have cabin width/depth and a hosted entrance opening. The stair's rise × step count should match connected floor elevations, but this arithmetic check alone **does not validate stairs for construction**. Landings, guardrails, egress, headroom, machine space, shafts and accessibility still need engineering.

## 3. The design order the AI MUST follow

1. **Parse the user's brief** into required spaces, dimensions, plot constraints, entrance, north, floors, families of fixtures, room adjacency priorities and unknown information. Do not invent a missing surveyed footprint or claim that assumptions are surveyed facts.
2. **Model the usable envelope** with a valid footprint and any genuine inner holes, setbacks/voids only if the user supplied them or explicitly requested an assumed conceptual scenario.
3. **Reserve immovable structural/service constraints first**: true columns, shafts, lightwells, stairs, lifts and other core volumes. Keep stacked cores consistent across floors; do not put a new shaft across a bedroom door.
4. **Zone public/private/service rooms**. Provide an accessible-for-review route from an exterior entrance to each intended occupied room, and separate wet areas/utility services where practical. Use irregular polygons if the layout demands them. Do not assume that an overlap-free set of rooms is inherently usable.
5. **Create physically coherent walls** and assign openings. Every door must connect meaningful spaces or outdoors, with the correct side and swing. Every window must appear on an actual suitable wall, with plausible light/ventilation intent.
6. **Choose furniture by wall and clearance constraints**. Beds and wardrobes must be evaluated against all wall solids, doors, stair entries, windows, columns and other objects. Avoid free-floating beds and cupboards in door zones. Position the operating side of furniture toward usable circulation.
7. **Run all deterministic checks**. See section 4. A serious failure invalidates the entire draft even if the SVG happens to look attractive. On failure, revise the geometry or use the explicit opt-in furnishing-repair function; do not quietly move walls or pretend the failures were fixed.
8. **Produce SVG/DXF only after passing hard checks**, while retaining the original JSON and all detected warnings. Preserve typed 3D attributes for subsequent geometry conversion.
9. **Review architectural quality separately**. An independent AI review can recommend improvements for privacy, travel distances, daylight, storage, plumbing adjacency and efficiency. It does not override deterministic errors or professional review.

## 4. Implemented placement and spatial checks

These tests are *heuristic default preferences*, not statutory building standards. Their parameters are not asserted to match the National Building Code of India or any local authority. Their purpose is to catch obvious mistakes automatically.

### Beds

- By default in residential layouts, the **headboard edge must run parallel to and within 260 mm of a room boundary**, and at least 60% of that headboard edge must align with the wall region. A bed at the geometric center of a room fails `BED_NO_HEADWALL`.
- Its headboard must not be anchored over a door/opening. The foot must have approximately 570 mm of clear access, and at least one side must have approximately 530 mm of ordinary approach clearance. A double bed accessible only from one side raises a warning.
- A bed can be intentionally floating in a very special interior design, but the default generator must not do it. Such an exception requires an explicit design policy change and manual review, not a generic AI guess.

### Wardrobes, cabinets and appliances

- Storage front is the object's **local +Y**. Allow a default 700 mm wardrobe front working zone and around 600 mm for large cabinets, with explicit overrides when justified. Preserve open fronts away from door approaches and furniture collisions.
- Do not put wardrobes on top of floor-level doors, inside their whole leaf sweep, or within required door-approach regions. Sliding doors and open passages still need clear approach space.
- Tall objects that overlap the window's Z interval must not cover the glazing/ventilation zone. A small low object may coexist under a high-sill window; a full-height cupboard may not.
- Built-in hobs and sinks may deliberately overlap countertops. This is a modeled assembly exception, not permission for all objects to overlap.

### Doors, circulation and geometry

- Validate full 90-degree door-leaf sweep, both immediate doorway approach rectangles, missing wall hosts, opening overruns/overlaps, wall intersections and sensible connection topology.
- Exclude immovable columns, shafts and other physical bodies from usable furniture/circulation regions. A simple free-space connected-components check can detect some blocked routes between portals in the same room. **This is not a certified egress/accessible-route solver**.
- A stair entrance must open to a modeled landing rather than directly onto a run of treads. Validate that step count × rise matches the intended height difference where both are supplied.
- Reject invalid polygons, overlapping spaces, rooms outside the actual footprint (including holes), object-wall penetration and material/reference failures. Exports fail closed for **errors**; warnings remain visible for expert review.

### Robust error behavior

Return explicit issue codes and affected element paths, e.g. `BED_NO_HEADWALL`, `FURNITURE_ACCESS_BLOCKED`, `DOOR_APPROACH_BLOCKED`, `FURNITURE_BLOCKS_WINDOW`, `OBJECT_HITS_BUILT_ELEMENT`, `STAIR_DOOR_ON_TREADS`, `INVALID_ROOM_HOLES`, `ROOM_CIRCULATION_BLOCKED`.

Never automatically call `buffer(0)` / `make_valid()` to alter a malformed polygon behind the user's back. Never fill in guessed site dimensions, invent a door's host, or silently discard critical structural objects. A partial proposal with unresolved errors must be labeled invalid and blocked from SVG/DXF export.

## 5. AI → validator → deterministic 2D output

The runtime starts with a user brief and optional `DesignConstraints`. The AI returns **the complete structured JSON plan**, following the live schema. The application does all geometry and drafting deterministically. The main stages are:

```text
User requirements + explicit constraints
          |
          v
AI spatial and architectural proposal (JSON)
          |
          v
Pydantic schema check (types, references, numeric ranges)
          |
          v
Shapely geometry + topology + circulation + furniture validator
          |                                |
       Accepted                         Errors
          |                                |
          |                    Deterministic bedroom reflow proposal
          |                                |
          |                    Re-check (and expose all moves)
          |                                |
          |                    Bounded AI revision with error codes
          |                                |
          |                          Check again
          v                                v
Architectural reviewer (advisory)    Invalid candidate
          |                                |
          v                                v
SVG/DXF sheet + canonical JSON      NO successful export
          |
          v
Later: 3D scene / BIM adapter from JSON (NOT from the SVG)
```

Only genuinely improved candidates may replace an accepted draft. The bedroom reflow endpoint `POST /api/repair/bedrooms` returns a **proposed** revised plan with a detailed change log and before/after reports. It does not modify the user's uploaded original file. Repair cannot fix all room/wall/structural mistakes; these must be regenerated or corrected deliberately.

## 6. Independent rendering requirements

- SVG uses individual selectable semantic layers for `walls`, `spaces`, `openings`, `structure`, `objects`, `labels`, `dimensions`, title block and annotations. Build walls as thickness-bearing polygons with hosted opening intervals **subtracted**. Use actual door arcs and explicit window jamb/glazing linework, not guessed icons.
- DXF writes native CAD linework, polylines, hatches, arcs and texts in millimetres, with distinct architectural layers including `A-STRUCT`, `A-CORE` and `A-SHAFT`.
- Furniture family symbols use their real width/depth orientation. Columns/shafts/stair flights/lifts draw their own symbols from dedicated typed data. Include a north arrow, dimensions and **NOT FOR CONSTRUCTION** titleblock disclaimer.
- Never infer dimensions or functional capacity from an SVG screenshot. Export data is derived from canonical JSON, not from an LLM-generated illustration.

## 7. Rules for varying layouts

The **general schema and checker** support arbitrary user-proposed valid room polygons, holes, many rooms, separate structural elements and multiple levels. The **offline template generator** is intentionally narrower and is only an automated regression/demo family: 1–4 bedrooms, configurable width/depth/seed, standard or irregular living areas, and optionally a staircase/lift/shaft core. Its purpose is to repeatedly test the same architecture across different inputs, **not** to pretend that every building can be solved by a hard-coded rectangle packer.

For new building types, add a typology-aware layout generator or solver, room program, furniture rules, service routing and verified jurisdictional rule pack **without changing the JSON/validator/renderer boundary**. Future optimization could use CP-SAT/mixed-integer methods for discrete constraints plus geometric feasibility and human-guided multiobjective scoring. Do not call an unimplemented solver or a generated image a finished architectural plan.

## 8. Reserved for future 3D/IFC implementation

Retain dimensions, floors, elevations, base Z, material IDs, textures, asset references, wall thickness/height, door/window cuts, shaft and column polygons, stair flights/landings, and lift cabin/door references. A future engine should make slabs from polygon rings including holes, extrude walls and columns, subtract valid 3D openings, instantiate scaled assets with actual base Z, and link connectors across levels. Export to IFC 4.3 requires a dedicated semantic mapping and IFC-specific tests; **this V3 release does not export IFC, generate 3D meshes, or certify structure**.

## 9. How to invoke and inspect the implementation

- `GET /api/schema`: exact canonical JSON Schema.
- `GET /api/contract`: this Markdown contract.
- `POST /api/generate`: Gemini proposal / validation / bounded repair / reviewer, requires server-side `GEMINI_API_KEY`.
- `POST /api/template`: offline 1–4 bedroom parametric demonstration options and seed; no AI key required.
- `POST /api/repair/bedrooms`: furniture-repositioning suggestion with changes and reports.
- `POST /api/validate`: independent report for any schema-compatible plan.
- `POST /api/render` and `/api/export/{svg,dxf}`: drawing and exports, blocked by errors.

Every candidate is an **AI-assisted schematic draft**, **not a verified/buildable architectural design**. Engineering, planning approval, life-safety, structural feasibility, daylight assessment and local regulation analysis remain independent responsibilities.
