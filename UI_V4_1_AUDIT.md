# Architect AI Studio — V4.1 Interface Audit & Upgrade

## Baseline issues found in actual V4 code
1. A duplicate HTML ID (`alternatives`) was used by both the numeric design-count input and the results list. Result cards did not render in the original V4 interface.
2. On mobile, users had to scroll through the entire brief before reaching the drawing; there was no plan-first mobile navigation.
3. There was no project workspace saving beyond JSON download, no ordinary geometry-object property inspector, no undo/redo, no zoom/pan controls, and no direct element selection on the SVG.
4. The optional AI button did not clearly signal whether the server had an API key.
5. Several controls could be set to obviously incompatible values without useful inline feedback.
6. Multiple independently generated design alternatives were technically supported by the API but difficult to compare through the UI.
7. There was no PNG download, and controls did not distinguish site-only restrictions like DXF floor export.

## Changes implemented
- Rebuilt responsive three-panel UI with plan-first mobile tabs, accessible labels and focused toolbars.
- Distinct alternatives input (`alternatives_count`) and comparison-card list (`alternative_list`) with real API-based SVG thumbnails.
- Plot dimensions shown in metres, feet, or millimetres, converted to millimetres for the JSON contract.
- Six project presets, contextual constraints for property typology, floor counts, opposed flats and vertical access, and inline validation before generation.
- Interactive floor/site toggle, building/level selectors, technical/presentation view, SVG layers, pan, zoom, reset-fit, and click-to-inspect objects/walls/openings/rooms.
- Measured property edits: furniture dimensions/location/orientation, door and window sizes/offsets/handing, wall thickness/height and structural metadata, room labels/ceiling heights, and site-area labels.
- All mutations sent through `/api/v4/validate`; invalid configurations are rejected and never silently committed. Local undo/redo tracks accepted changes.
- `POST /api/v4/edit/auto-place`: bounded candidate search for common furniture using the existing geometric validator. May refuse objects when no valid spot exists; not a furnishing optimizer.
- Named local-browser drafts (up to 12; no cloud sync), JSON import/download, and SVG/DXF/PNG exports.
- Gemini control reacts to `/api/v4/status`; missing API key disables the feature rather than implying it works.
- Clear reminders that concepts are neither professionally approved nor construction-ready.

## Intentionally not represented as finished
- Dragging / stretching room and wall topology, automatic restructuring of adjoining rooms, and full BIM-grade history/editing.
- Code certification, construction completeness, structural/MEP engineering or a universally valid layout optimizer.
- Cloud sync/accounts, simultaneous collaboration, or guaranteed aesthetically good plans.
- Real-time architectural AI generation via specialist model checkpoints. V4 generator remains the existing validated heuristic system.
- Browser-native hosting; app runs locally through FastAPI or can be deployed by a developer.

## Verification
- The real running API was used via a Chromium browser test harness for SVG rendering, mobile layout, generation of three alternatives, click-to-inspect, invalid move rejection, accepted model edit, undo, and site view switching.
- The test environment restricts Chromium localhost navigation, so screenshots were captured by loading the unmodified application HTML/CSS/JS in Chromium and routing its `fetch` calls to the running local FastAPI server. They are rendered application screenshots, not AI-generated mockups.
- A direct backend test verified successful bounded auto-placement of a new chair, validated by the property checker.
- Existing V4 test cases remain included; an attempted full suite exceeded the execution budget in this environment, so a complete regression pass is not claimed.
