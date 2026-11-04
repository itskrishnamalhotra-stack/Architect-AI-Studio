#!/usr/bin/env python3
"""Recreate the catalog scenarios with original Architect AI Studio V4 Python functions."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v4',type=Path,required=True,help='Extracted Architect_AI_Studio_V4 directory')
    parser.add_argument('--out',type=Path,default=Path('regenerated_examples'))
    args=parser.parse_args()
    args.v4=args.v4.expanduser().resolve()
    if not (args.v4/'architect'/'property_generator.py').is_file():
        parser.error('--v4 must point to the original extracted Architect_AI_Studio_V4 project')
    sys.path.insert(0,str(args.v4))
    from architect.property_models import PropertyRequest
    from architect.property_generator import generate_property
    from architect.property_validate import audit_property
    from architect.property_render import render_site_svg,render_floor_svg
    manifest=json.loads((Path(__file__).resolve().parent/'catalog_manifest.json').read_text())
    for case in manifest['examples']:
        req=PropertyRequest(**case['request'])
        project=generate_property(req)
        report=audit_property(project)
        if not report.valid:
            raise RuntimeError(f"{case['id']} failed: {[i.code for i in report.issues if i.severity=='error'][:5]}")
        p=args.out/case['id'];p.mkdir(parents=True,exist_ok=True)
        (p/'project.json').write_text(project.model_dump_json(indent=2),encoding='utf-8')
        (p/'site.svg').write_text(render_site_svg(project),encoding='utf-8')
        for levelid in case['levels_drawn']:
            (p/f'floor_{levelid}.svg').write_text(render_floor_svg(project,level_id=levelid,style='presentation'),encoding='utf-8')
        (p/'validation.json').write_text(report.model_dump_json(indent=2),encoding='utf-8')
        print(f"{case['id']}: valid with {report.warnings} warnings")
if __name__=='__main__':main()
