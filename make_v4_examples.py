"""Regenerate the V4 showcase from measured JSON. Never hand-edit the exported SVG."""
from pathlib import Path
import json
from architect.property_models import PropertyRequest
from architect.property_generator import generate_property
from architect.property_validate import audit_property
from architect.property_render import render_site_svg,render_floor_svg,render_floor_dxf
OUT=Path(__file__).resolve().parent/'examples'
CASES={
 'v4_sample_property':dict(property_type='villa',layout_strategy='wing',garage='required',lawn='required',plot_width_mm=25000,plot_depth_mm=28000),
 'v4_two_flats':dict(property_type='apartment',units_per_floor=2,floors=3,plot_width_mm=35500,plot_depth_mm=29000,layout_strategy='linear'),
 'v4_opposed':dict(property_type='apartment',units_per_floor=2,floors=2,plot_width_mm=22000,plot_depth_mm=34000,layout_strategy='opposed'),
 'v4_mixed_use':dict(property_type='mixed_use',units_per_floor=2,floors=3,plot_width_mm=38000,plot_depth_mm=30000,layout_strategy='linear'),
 'v4_core':dict(property_type='apartment',units_per_floor=2,floors=4,plot_width_mm=40000,plot_depth_mm=29000,lift='required',shaft='required'),
}

def make_one(name,req,include_png=False):
    p=generate_property(PropertyRequest(**req));r=audit_property(p)
    if not r.valid:raise RuntimeError(f'{name}: {r.errors} errors: '+str([(i.code,i.message) for i in r.issues if i.severity=='error'][:4]))
    (OUT/f'{name}.json').write_text(p.model_dump_json(indent=2),encoding='utf-8')
    site=render_site_svg(p);floor=render_floor_svg(p,style='presentation')
    (OUT/f'{name}_site.svg').write_text(site,encoding='utf-8')
    (OUT/f'{name}_floor.svg').write_text(floor,encoding='utf-8')
    (OUT/f'{name}_floor.dxf').write_bytes(render_floor_dxf(p))
    if include_png:
        import cairosvg
        cairosvg.svg2png(bytestring=site.encode(),write_to=str(OUT/f'{name}_site.png'),output_width=1120)
        cairosvg.svg2png(bytestring=floor.encode(),write_to=str(OUT/f'{name}_floor.png'),output_width=1120)
    return {'name':name,'errors':r.errors,'warnings':r.warnings,'independent_units':r.metrics['independent_units']}

if __name__=='__main__':
    import sys
    names=sys.argv[1:] or list(CASES)
    report=[]
    for name in names:
        if name not in CASES:raise SystemExit(f'unknown example: {name}')
        result=make_one(name,CASES[name],include_png=name in ('v4_sample_property','v4_two_flats','v4_mixed_use'))
        report.append(result);print(result,flush=True)
    (OUT/'v4_example_reports.json').write_text(json.dumps(report,indent=2))
