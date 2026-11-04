# Architect AI Studio V4 - Generated Example Catalog

This bundle contains **35 property scenarios** generated directly by the original V4 Python project (`Architect_AI_Studio_V4.zip`). It includes **26 distinct base-floor geometries** and variation in site facilities, room counts, building levels, and ownership model. All 35 passed the V4 geometric validation checks with zero flagged errors. This is **not** professional approval; **25 scenarios** have a warning for rooms without modeled external windows, and other warnings concern lifts, vehicle access and bed clearances.

The combined 92-page A3 landscape PDF is available separately as `Architect_AI_Studio_V4_35_Architectural_Examples.pdf`.

## Contents

- `catalog_manifest.json` - all exact generation requests, names, program summaries, per-case metrics, warning counts and error results.
- `pdf_page_index.json` - pages in the combined PDF for each scenario.
- `catalog_index.csv` - concise table of all scenarios.
- `V01/` through `M07/` - each has the original generated `project.json`, the measured `site.svg` and `floor_L0.svg` drawing, optional `floor_L1.svg` if included in the PDF, and `report.json`.
- `reproduce_examples.py` - run against the supplied V4 code base to regenerate all source data and drawings.

## Regeneration

Install V4's requirements and extract V4 first, then run:

```bash
python reproduce_examples.py --v4 /path/to/Architect_AI_Studio_V4 --out /path/to/new_catalog
```

This calls `architect.property_generator.generate_property()` and `architect.property_render.render_site_svg()` / `render_floor_svg()` with the stored request values. No separately drafted CAD files or manually edited geometric SVGs were used.

## Interpret the examples correctly

- **Villa:** one residence per level; optional garage, lawn, surface parking, staircase and lift.
- **Duplex:** one dwelling identifier spanning multiple floors; upper residential floor geometry is cloned.
- **Apartment:** 1-4 homes per level; common gallery, opposed or wing alternatives, multiple floors and optional cores.
- **Mixed use:** model changes the ground level to retail/office/stockroom and maintains residential units upstairs. **Retail fire separation and access control are not engineered**.

Warning counts reflect the original V4 validator. All diagrams are **schematic concepts, not construction documents**. The parking dimensions, lifts, stair dimensions, privacy, natural lighting, structural design, plumbing and code compliance must be reviewed by qualified professionals.
