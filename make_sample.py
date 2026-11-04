"""Build several *different* measured floor-plan cases through one generator API."""
from pathlib import Path
from architect.procedural import TemplateRequest,generate_template
from architect.validate import validate_plan
from architect.render import render_svg,render_dxf

CASES={
    'sample_plan':TemplateRequest(bedrooms=3,seed=42),
    'irregular_2bed':TemplateRequest(bedrooms=2,irregular_living=True,seed=3),
    'vertical_core_2level':TemplateRequest(bedrooms=3,include_core=True,floors=2,seed=33),
    'four_bed':TemplateRequest(bedrooms=4,width_mm=15600,depth_mm=12800,seed=91),
    'one_bed':TemplateRequest(bedrooms=1,width_mm=12000,depth_mm=10800,seed=77),
}

def main():
    root=Path(__file__).resolve().parent/'examples';root.mkdir(exist_ok=True)
    for name,config in CASES.items():
        plan=generate_template(config)
        report=validate_plan(plan)
        if not report.valid:raise RuntimeError(f'{name} has validation errors: {report.model_dump_json(indent=2)}')
        (root/(name+'.json')).write_text(plan.model_dump_json(indent=2),encoding='utf-8')
        (root/(name+'.svg')).write_text(render_svg(plan),encoding='utf-8')
        (root/(name+'.dxf')).write_bytes(render_dxf(plan))
        try:
            import cairosvg
            cairosvg.svg2png(url=str(root/(name+'.svg')),write_to=str(root/(name+'.png')),output_width=1600)
        except ImportError:pass
        print(f'{name}: {len(plan.levels)} level(s), {sum(len(l.spaces) for l in plan.levels)} spaces, {report.errors} errors, {report.warnings} warnings')

if __name__=='__main__':main()
