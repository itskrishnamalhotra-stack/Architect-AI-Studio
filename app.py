"""Architect AI Studio V4 — property-scale planning + V3 CAD compatibility API."""
from __future__ import annotations
import json, os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.responses import HTMLResponse, Response, JSONResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from architect.models import FloorPlan, DesignConstraints
from architect.validate import validate_plan
from architect.render import render_svg, render_dxf
from architect.ai import generate_plan, AIConfigurationError, AIUpstreamError, FLOORPLAN_SCHEMA
from architect.procedural import TemplateRequest, generate_template, suggest_bedroom_repair

ROOT=Path(__file__).resolve().parent
app=FastAPI(title="Architect AI Studio",version="4.1.0",
            description="AI-assisted schematic floor planning; no construction / code certification.")
app.mount("/static",StaticFiles(directory=str(ROOT/"static")),name="static")

@app.middleware("http")
async def limit_body(request:Request,call_next):
    # Protect against unexpectedly large provider/model payloads on endpoints.
    if request.method in {"POST","PUT","PATCH"}:
        try:
            size=int(request.headers.get("content-length","0"))
            if size>2_000_000:
                return JSONResponse(status_code=413,content={"detail":"Request exceeds 2 MB limit"})
        except ValueError:
            return JSONResponse(status_code=400,content={"detail":"Invalid Content-Length"})
        # No body streaming beyond the cap if a client omits Content-Length.
        received=await request.body()
        if len(received)>2_000_000:
            return JSONResponse(status_code=413,content={"detail":"Request exceeds 2 MB limit"})
    return await call_next(request)

@app.get("/",include_in_schema=False)
def index():return FileResponse(ROOT/"static"/"v4.html")

@app.get("/legacy",include_in_schema=False)
def legacy():return FileResponse(ROOT/"static"/"index.html")

@app.get("/api/sample")
def sample():return JSONResponse(json.loads((ROOT/"examples"/"sample_plan.json").read_text(encoding="utf-8")))

@app.get("/api/templates")
def templates():
    return {"types":["standard","irregular","with_core"],"bedrooms_min":1,"bedrooms_max":4,
        "description":"Parametric demonstration family; not unlimited typology generation or a professional architectural approval."}

@app.post("/api/template")
def generate_offline_template(data:dict=Body(...)):
    try:opts=TemplateRequest.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422,detail={"code":"PARAMETERS_INVALID","issues":[
            {"path":".".join(map(str,e['loc'])),"message":e['msg']} for e in exc.errors()[:40]]})
    plan=generate_template(opts)
    report=validate_plan(plan)
    if not report.valid:
        # Unlike earlier versions, never present a known-invalid generator candidate as success.
        raise HTTPException(status_code=422,detail={"code":"TEMPLATE_FAILED_VALIDATION","report":report.model_dump(mode="json")})
    return {"plan":plan.model_dump(mode="json"),"report":report.model_dump(mode="json"),
            "generator":"parametric_demonstration","seed":opts.seed,
            "limitations":"Templates demonstrate rules and variations, not unlimited architectural typologies."}

@app.post("/api/repair/bedrooms")
def propose_repair(data:dict=Body(...)):
    plan=load_plan(data.get("plan"))
    seed=data.get("seed",17)
    if not isinstance(seed,int) or isinstance(seed,bool) or not 0<=seed<=1000000:
        raise HTTPException(status_code=422,detail="seed must be an integer from 0 to 1000000")
    proposed=suggest_bedroom_repair(plan,seed=seed)
    return {"accepted":proposed['accepted'],"plan":proposed['plan'].model_dump(mode='json'),
            "changes":proposed['changes'],"original_report":proposed['original_report'].model_dump(mode='json'),
            "proposed_report":proposed['proposed_report'].model_dump(mode='json'),
            "report":proposed['report'].model_dump(mode='json')}

@app.get("/api/schema")
def schema():return JSONResponse(FloorPlan.model_json_schema())

@app.get("/api/ai-schema")
def ai_schema():return JSONResponse(FLOORPLAN_SCHEMA)

@app.get("/api/contract")
def contract():return PlainTextResponse((ROOT/"ARCHITECTURE_BLUEPRINT.md").read_text(encoding="utf-8"))

@app.get("/api/status")
def status():return {"ready":True,"ai_configured":bool(os.getenv("GEMINI_API_KEY")),
                     "default_model":os.getenv("GEMINI_MODEL","gemini-2.5-flash"),
                     "schema_version":"1.1.0"}


def load_plan(data):
    try:return FloorPlan.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422,detail={"code":"SCHEMA_INVALID","issues":[
            {"path":".".join(map(str,e['loc'])),"code":e['type'],"message":e['msg']} for e in exc.errors()[:60]]})

def load_constraints(data):
    try:return DesignConstraints.model_validate(data or {"require_exterior_entrance":False})
    except ValidationError as exc:
        raise HTTPException(status_code=422,detail={"code":"CONSTRAINTS_INVALID","issues":[
            {"path":".".join(map(str,e['loc'])),"code":e['type'],"message":e['msg']} for e in exc.errors()[:60]]})

@app.post("/api/validate")
def validate(data:dict=Body(...)):
    plan=load_plan(data.get("plan"))
    constraints=load_constraints(data.get("constraints"))
    return validate_plan(plan,constraints).model_dump(mode="json")

@app.post("/api/render")
def render(data:dict=Body(...)):
    plan=load_plan(data.get("plan"))
    constraints=load_constraints(data.get("constraints"))
    report=validate_plan(plan,constraints)
    level_id=data.get("level_id")
    if level_id and not any(l.id==level_id for l in plan.levels):
        raise HTTPException(status_code=400,detail="Unknown level_id")
    svg=None
    if report.valid:
        try:svg=render_svg(plan,level_id)
        except (ValueError,TypeError) as exc:
            raise HTTPException(status_code=422,detail={"code":"RENDER_FAILED","message":str(exc)})
    return {"report":report.model_dump(mode="json"),"svg":svg,
            "rendered":svg is not None,"level_id":level_id or plan.levels[0].id}

@app.post("/api/export/svg")
def svg_export(data:dict=Body(...)):
    plan=load_plan(data.get("plan"))
    report=validate_plan(plan)
    if not report.valid:raise HTTPException(status_code=422,detail="Cannot export a plan with validation errors")
    try:res=render_svg(plan,data.get("level_id"))
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc))
    return Response(res,media_type="image/svg+xml",headers={"Content-Disposition":"attachment; filename=architect-plan.svg"})

@app.post("/api/export/dxf")
def dxf_export(data:dict=Body(...)):
    plan=load_plan(data.get("plan"))
    report=validate_plan(plan)
    if not report.valid:raise HTTPException(status_code=422,detail="Cannot export a plan with validation errors")
    try:res=render_dxf(plan,data.get("level_id"))
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc))
    return Response(res,media_type="application/dxf",headers={"Content-Disposition":"attachment; filename=architect-plan.dxf"})

@app.post("/api/generate")
async def generate(data:dict=Body(...)):
    brief=data.get("brief")
    if not isinstance(brief,str) or not 20<=len(brief.strip())<=10000:
        raise HTTPException(status_code=422,detail="brief must contain 20–10000 characters")
    constraints=load_constraints(data.get("constraints"))
    model=data.get("model")
    if model is not None and (not isinstance(model,str) or not model.startswith("gemini-") or len(model)>90):
        raise HTTPException(status_code=422,detail="model must be a Gemini model ID")
    max_revisions=data.get("max_revisions",2)
    if not isinstance(max_revisions,int) or isinstance(max_revisions,bool) or not 0<=max_revisions<=3:
        raise HTTPException(status_code=422,detail="max_revisions must be 0..3")
    review=data.get("design_review",True)
    if not isinstance(review,bool):raise HTTPException(status_code=422,detail="design_review must be boolean")
    try:
        return await run_in_threadpool(generate_plan,brief,constraints,model=model,
                                       max_revisions=max_revisions,perform_design_review=review)
    except AIConfigurationError as exc:raise HTTPException(status_code=503,detail=str(exc))
    except AIUpstreamError as exc:raise HTTPException(status_code=502,detail=str(exc))


# ==== V4 canonical property-level API. Old V3 endpoints remain for compatibility. ====
from architect.property_models import PropertyRequest, PropertyProject
from architect.property_generator import PlanningError
from architect.property_search import generate_alternatives
from architect.property_validate import audit_property
from architect.property_render import render_site_svg, render_floor_svg, render_floor_dxf
from architect.property_ai import brief_to_request


def _v4_request(data):
    try: return PropertyRequest.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422,detail={'code':'BRIEF_INVALID','issues':[
           {'path':'.'.join(map(str,e['loc'])),'message':e['msg']} for e in exc.errors()[:40]]})

def _v4_project(data):
    try:return PropertyProject.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422,detail={'code':'PROJECT_SCHEMA_INVALID','issues':[
           {'path':'.'.join(map(str,e['loc'])),'message':e['msg']} for e in exc.errors()[:50]]})

@app.get('/api/v4/status')
def v4_status():
    return {'ready':True,'version':'4.1.0','schema_version':'2.0.0',
            'ai_configured':bool(os.getenv('GEMINI_API_KEY')),
            'data_contract':'/api/v4/schema','old_interface':'/legacy',
            'disclaimer':'Architectural concept model, not code or construction certification'}

@app.get('/api/v4/schema')
def v4_schema():return PropertyProject.model_json_schema()

@app.get('/api/v4/sample')
def v4_sample():
    return json.loads((ROOT/'examples'/'v4_sample_property.json').read_text(encoding='utf-8'))

@app.post('/api/v4/alternatives')
async def v4_alternatives(data:dict=Body(...)):
    props=_v4_request(data)
    try:result=await run_in_threadpool(generate_alternatives,props)
    except PlanningError as exc:
        raise HTTPException(status_code=422,detail={'code':'SITE_OR_PROGRAM_INFEASIBLE','message':str(exc)})
    if not result['alternatives']:
        raise HTTPException(status_code=422,detail={'code':'NO_VALID_ALTERNATIVE',
            'message':'No supported layout passed the current feasibility checks; edit your brief or plot size',
            'attempts':result['attempts']})
    # Avoid delivering a known-invalid candidate just to meet requested option count.
    if len(result['alternatives'])<props.alternatives:
        result['limitations'].append(f"Only {len(result['alternatives'])} distinct valid alternatives were found within the implemented layout families")
    return result


@app.post('/api/v4/edit/auto-place')
async def v4_auto_place(data:dict=Body(...)):
    from architect.property_edit import suggest_furniture_placement
    project=_v4_project(data.get('project'))
    kwargs={}
    for key in ('building_id','level_id','space_id','kind','name'):
        value=data.get(key)
        if key!='name' and (not isinstance(value,str) or not value or len(value)>120):
            raise HTTPException(status_code=422,detail=f'Invalid {key}')
        kwargs[key]=value
    for key in ('width_mm','depth_mm','height_mm'):
        value=data.get(key)
        if isinstance(value,bool) or not isinstance(value,(float,int)):
            raise HTTPException(status_code=422,detail=f'Invalid {key}')
        kwargs[key]=value
    try:return await run_in_threadpool(suggest_furniture_placement,project,**kwargs)
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc))

@app.post('/api/v4/validate')
def v4_validate(data:dict=Body(...)):
    project=_v4_project(data.get('project'))
    return audit_property(project).model_dump(mode='json')

@app.post('/api/v4/render')
def v4_render(data:dict=Body(...)):
    p=_v4_project(data.get('project'))
    report=audit_property(p)
    if not report.valid:
        return {'rendered':False,'svg':None,'report':report.model_dump(mode='json')}
    view=data.get('view','floor')
    try:
        if view=='site':svg=render_site_svg(p)
        elif view=='floor':svg=render_floor_svg(p,data.get('building_id','main'),data.get('level_id'),data.get('style','technical'))
        else:raise ValueError('view must be site or floor')
    except (TypeError,ValueError) as exc:
        raise HTTPException(status_code=422,detail={'code':'VIEW_INVALID','message':str(exc)})
    return {'rendered':True,'svg':svg,'report':report.model_dump(mode='json'),
            'view':view,'level_id':data.get('level_id'),'building_id':data.get('building_id','main')}

@app.post('/api/v4/export/svg')
def v4_export_svg(data:dict=Body(...)):
    p=_v4_project(data.get('project'))
    report=audit_property(p)
    if not report.valid:raise HTTPException(status_code=422,detail={'code':'PROJECT_INVALID','errors':report.errors})
    view=data.get('view','floor')
    try:
        svg=render_site_svg(p) if view=='site' else render_floor_svg(p,data.get('building_id','main'),data.get('level_id'),data.get('style','technical'))
    except (ValueError,TypeError) as exc:raise HTTPException(status_code=422,detail=str(exc))
    return Response(svg,media_type='image/svg+xml',headers={'Content-Disposition':'attachment; filename="architect-v4-'+view+'.svg"'})

@app.post('/api/v4/export/dxf')
def v4_export_dxf(data:dict=Body(...)):
    p=_v4_project(data.get('project'))
    report=audit_property(p)
    if not report.valid:raise HTTPException(status_code=422,detail={'code':'PROJECT_INVALID','errors':report.errors})
    try:dxf=render_floor_dxf(p,data.get('building_id','main'),data.get('level_id'))
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc))
    return Response(dxf,media_type='application/dxf',headers={'Content-Disposition':'attachment; filename="architect-v4-floor.dxf"'})

@app.post('/api/v4/ai-brief')
async def v4_ai_brief(data:dict=Body(...)):
    brief=data.get('brief','')
    if not isinstance(brief,str) or not 20<=len(brief.strip())<=8000:
        raise HTTPException(status_code=422,detail='Brief must be 20–8000 characters')
    model=data.get('model')
    if model is not None and (not isinstance(model,str) or not model.startswith('gemini-') or len(model)>90):
        raise HTTPException(status_code=422,detail='model must be a valid Gemini model ID')
    try:
        props=await run_in_threadpool(brief_to_request,brief,model=model)
        return {'requirements':props.model_dump(mode='json'),
                'message':'AI translated the brief into reviewable requirements. Check inferred plot dimensions before generating.'}
    except AIConfigurationError as exc:raise HTTPException(status_code=503,detail=str(exc))
    except AIUpstreamError as exc:raise HTTPException(status_code=502,detail=str(exc))


if __name__=="__main__":
    import uvicorn
    uvicorn.run("app:app",host="127.0.0.1",port=8000,reload=False)
