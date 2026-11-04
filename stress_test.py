"""Reproducible, bounded generation stress check. No AI key or remote requests."""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
from architect.procedural import TemplateRequest,generate_template
from architect.validate import validate_plan

root=Path(__file__).resolve().parent
summary={"configurations":36,"generator":"residential_parametric_family_only",
         "total_errors":0,"total_warnings":0,"failed_cases":[],"warning_codes":Counter(),
         "bedroom_counts":Counter(),"floor_counts":Counter(),"irregular_count":0,"core_count":0}
for i in range(36):
    bedroom_count=1+(i%4)
    floors=1+(i%13==0)+(i%29==0)
    core=bool(floors>1 or i%5==0)
    irregular=bool(i%3==0)
    params=TemplateRequest(bedrooms=bedroom_count,width_mm=13200+100*(i%7),
         depth_mm=11600+100*(i%9),seed=i*17,
         irregular_living=irregular,include_core=core,floors=floors)
    plan=generate_template(params)
    report=validate_plan(plan)
    summary['total_errors']+=report.errors;summary['total_warnings']+=report.warnings
    summary['bedroom_counts'][str(bedroom_count)]+=1;summary['floor_counts'][str(floors)]+=1
    summary['irregular_count']+=int(irregular);summary['core_count']+=int(core)
    for issue in report.issues:
        if issue.severity=='warning':summary['warning_codes'][issue.code]+=1
    if report.errors:
        summary['failed_cases'].append({"index":i,"settings":params.model_dump(mode='json'),
             "errors":[{"code":x.code,"path":x.path} for x in report.issues if x.severity=='error']})
summary['zero_detected_errors']=not bool(summary['failed_cases'])
summary['disclaimer']='Only implemented deterministic checks; does not prove building compliance, engineering correctness, or absence of architectural design mistakes.'
out=root/'examples'/'stress_test_results.json'
out.write_text(json.dumps(summary,indent=2,default=dict),encoding='utf-8')
print(json.dumps(summary,indent=2,default=dict))
if summary['failed_cases']:raise SystemExit(1)
