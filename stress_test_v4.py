"""Reproducible offline sampled property cases; validation is not design certification."""
import json,time
from pathlib import Path
from architect.property_models import PropertyRequest
from architect.property_generator import generate_property,PlanningError
from architect.property_validate import audit_property

cases=[]
for bedrooms in (1,2,3,4):
    cases.append(dict(property_type='villa',bedrooms_per_unit=bedrooms,plot_width_mm=27000,plot_depth_mm=27000,seed=bedrooms*47))
for beds in (1,2):
    cases.append(dict(property_type='villa',bedrooms_per_unit=beds,layout_strategy='wing',plot_width_mm=26000,plot_depth_mm=27000,seed=7*beds))
for s in ('linear','irregular','opposed'):
    cases.append(dict(property_type='apartment',units_per_floor=2,layout_strategy=s,
                      plot_width_mm=38000,plot_depth_mm=34000,seed=65+len(s)))
cases.extend([
    dict(property_type='apartment',units_per_floor=3,plot_width_mm=47000,plot_depth_mm=30000),
    dict(property_type='duplex',floors=2,plot_width_mm=30000,plot_depth_mm=30000),
    dict(property_type='mixed_use',floors=2,units_per_floor=2,plot_width_mm=38000,plot_depth_mm=30000),
    dict(property_type='apartment',units_per_floor=2,floors=3,lift='required',shaft='required',plot_width_mm=43000,plot_depth_mm=30000),
    dict(property_type='villa',garage='required',lawn='required',plot_width_mm=25000,plot_depth_mm=28000),
])
results=[]
for i,kw in enumerate(cases):
    start=time.monotonic()
    try:
        project=generate_property(PropertyRequest(**kw))
        report=audit_property(project)
        result=dict(case=i+1,property_type=kw['property_type'],errors=report.errors,
                    warnings=report.warnings,buildings=len(project.buildings),
                    units=report.metrics['independent_units'],seconds=round(time.monotonic()-start,2),
                    error_codes=[v.code for v in report.issues if v.severity=='error'][:10])
    except Exception as exc:
        result=dict(case=i+1,property_type=kw.get('property_type'),errors=-1,exception=f'{type(exc).__name__}: {exc}')
    results.append(result);print(result,flush=True)
Path('examples/v4_stress_results.json').write_text(json.dumps({'sample_count':len(results),
    'all_passed_implemented_checks':all(r.get('errors')==0 for r in results),
    'cases':results,'note':'Passing algorithmic checks does not imply beautiful or legally buildable designs.'},indent=2))
