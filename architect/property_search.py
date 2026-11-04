"""Bounded alternative search, explicit feasibility gating and transparent heuristic ranking.

This is a deterministic candidate evaluator, not an architectural optimization certificate.
"""
from __future__ import annotations
from collections import Counter
from shapely.geometry import Polygon
from .property_generator import generate_property,PlanningError
from .property_models import PropertyRequest,PropertyProject
from .property_validate import audit_property
from .validate import poly


def score_property(project,report):
    if not report.valid:return -1e9
    main=project.buildings[0].plan
    level=main.levels[0]
    rooms={s.id:s for s in level.spaces}
    privateids={sid for u in project.buildings[0].units if u.level_id==level.id for sid in u.space_ids}
    private_area=sum(poly(rooms[sid].polygon).area for sid in privateids if sid in rooms)
    total_area=poly(level.footprint).area
    common_area=sum(poly(s.polygon).area for s in level.spaces if s.id not in privateids)
    circulation_private=sum(poly(s.polygon).area for s in level.spaces if s.id in privateids and s.kind in ('corridor','entry','hall'))
    circulation_ratio=(common_area+circulation_private)/total_area if total_area else 1
    bedrooms=sum(s.kind=='bedroom' for s in level.spaces)
    windows=sum(o.kind=='window' for o in level.openings)
    habitable=sum(s.kind in ('bedroom','living','kitchen','study','office') for s in level.spaces)
    # Soft preference only: a site plan with too much corridor is less space efficient.
    # Retained warnings are shown separately; score is not a substitute for professional review.
    daylight_opportunity= min(1,windows/max(1,habitable))
    efficiency=private_area/max(1,total_area)
    score=50 +efficiency*23 -circulation_ratio*18 +daylight_opportunity*12 -report.warnings*1.1
    # Avoid preference by seed; stable ties are expected for geometrically equal alternatives.
    return round(score,2),{
       'private_area_m2':round(private_area/1e6,1),'common_area_m2':round(common_area/1e6,1),
       'circulation_area_percent':round(circulation_ratio*100,1),
       'window_count':windows,'habitable_room_count':habitable,'bedrooms':bedrooms,
       'heuristic': 'Relative comparison only; no regulatory compliance or aesthetic certification'}

def generate_alternatives(request:PropertyRequest):
    if request.layout_strategy!='auto':
        strategies=[request.layout_strategy]
    else:
        strategies=['linear','irregular']
        if request.bedrooms_per_unit<=2:strategies.append('wing')
        if request.units_per_floor==2:strategies.append('opposed')
    # Reproducible attempts with distinct topology first, then controlled seed variations.
    attempts=[];results=[];signatures=set()
    trial=0
    while len(results)<request.alternatives and trial<max(8,request.alternatives*4):
        strategy=strategies[trial%len(strategies)]
        seed=request.seed+(trial//len(strategies))*101+trial%len(strategies)*17
        trial+=1
        try:
            project=generate_property(request,variant=strategy,seed=seed)
            report=audit_property(project)
            if not report.valid:
                attempts.append({'strategy':strategy,'accepted':False,'reason':'Geometric validation failure',
                                 'errors':[i.code for i in report.issues if i.severity=='error'][:8]})
                continue
            score,metrics=score_property(project,report)
            # Avoid calling the same geometry another "different design" because furniture moved 100 mm.
            level=project.buildings[0].plan.levels[0]
            signature=(strategy,len(level.spaces),tuple(tuple((round(pt.x/100),round(pt.y/100)) for pt in r.polygon)
                                          for r in level.spaces))
            if signature in signatures:
                attempts.append({'strategy':strategy,'accepted':False,'reason':'Duplicate topology'})
                continue
            signatures.add(signature)
            project.heuristic_score=score
            results.append({'id':f'ALT-{len(results)+1}', 'strategy':strategy,'score':score,
                 'quality_metrics':metrics,'project':project,'report':report})
            attempts.append({'strategy':strategy,'accepted':True,'score':score})
        except (PlanningError,ValueError) as exc:
            attempts.append({'strategy':strategy,'accepted':False,'reason':str(exc)[:350]})
    results.sort(key=lambda x:(-x['score'],x['strategy']))
    for i,item in enumerate(results):item['rank']=i+1
    return {'alternatives':results,'attempts':attempts,'candidates_tested':len(attempts),
            'limitations':['A small set of programmed residential topologies is searched; no guarantee of global optimum',
                'Scores favor space use and window opportunities, but cannot measure architectural beauty',
                'Professional structural, MEP, fire, accessibility and local planning review is required']}
