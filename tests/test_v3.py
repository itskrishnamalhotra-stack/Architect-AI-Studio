"""Regression and adversarial tests: never call a paid AI provider."""
import copy
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from architect.models import FloorPlan, DesignConstraints
from architect.procedural import TemplateRequest,generate_template,suggest_bedroom_repair
from architect.validate import validate_plan,at_wall,wall_length
from architect.functional import door_approaches
from architect.render import render_svg,render_dxf
from app import app

ROOT=Path(__file__).resolve().parents[1]
API=TestClient(app)

def base():return generate_template(TemplateRequest())
def find(plan,kind):return next(o for o in plan.levels[0].objects if o.kind==kind)
def codes(plan):return {x.code for x in validate_plan(plan).issues if x.severity=='error'}

@pytest.mark.parametrize('count',[1,2,3,4])
@pytest.mark.parametrize('mode',['standard','irregular','core'])
def test_many_topologies_have_no_known_errors(count,mode):
    plan=generate_template(TemplateRequest(bedrooms=count,seed=count*37,
                      irregular_living=mode=='irregular',include_core=mode=='core',floors=2 if mode=='core' else 1))
    report=validate_plan(plan)
    assert report.errors==0,report.model_dump_json(indent=2)
    assert len([r for r in plan.levels[0].spaces if r.kind=='bedroom'])==count
    if mode=='core':
        assert len(plan.levels)==2 and len(plan.levels[0].vertical_connectors)==2
        assert len(plan.levels[0].built_elements)>=2
    if mode=='irregular':
        assert any(len(s.polygon)>4 for s in plan.levels[0].spaces)

@pytest.mark.parametrize('seed',[0,1,40,99,1001])
def test_multiple_randomized_seeds(seed):
    plan=generate_template(TemplateRequest(seed=seed,bedrooms=3,width_mm=13700+seed%8*100,depth_mm=11700))
    assert validate_plan(plan).valid

def test_bed_cannot_float_in_centre():
    plan=base();room=next(r for r in plan.levels[0].spaces if r.id=='bedroom_1')
    xs=[p.x for p in room.polygon];ys=[p.y for p in room.polygon]
    bed=find(plan,'bed');bed.center.x=(min(xs)+max(xs))/2;bed.center.y=(min(ys)+max(ys))/2
    assert 'BED_NO_HEADWALL' in codes(plan)

def test_cabinet_cannot_block_door_approach_even_if_leaf_sweeps_elsewhere():
    plan=base();lv=plan.levels[0]
    op=next(o for o in lv.openings if o.id=='D_LIVING');wall=next(w for w in lv.walls if w.id==op.host_wall_id)
    living=next(s for s in lv.spaces if s.id=='living')
    from architect.functional import polygon
    r=polygon(living.polygon)
    centre=next(a.centroid for a in door_approaches(wall,op) if r.covers(a.centroid))
    from architect.models import PlacedObject, Point
    lv.objects.append(PlacedObject(id='door_cabinet',name='Door-blocking cupboard',kind='wardrobe',
           center=Point(x=centre.x,y=centre.y),width_mm=700,depth_mm=550,height_mm=2200,space_id='living'))
    assert 'DOOR_APPROACH_BLOCKED' in codes(plan)

def test_tall_wardrobe_cannot_obstruct_window():
    plan=base();lv=plan.levels[0]
    op=next(o for o in lv.openings if o.kind=='window' and o.id=='WN_B1')
    wall=next(w for w in lv.walls if w.id==op.host_wall_id)
    x,y=at_wall(wall,op.offset_mm+op.width_mm/2)
    wardrobe=next(o for o in lv.objects if o.kind=='wardrobe' and o.space_id=='bedroom_1')
    wardrobe.center.x=x+(300 if x<500 else -300)
    wardrobe.center.y=y+(300 if y<500 else -300)
    assert 'FURNITURE_BLOCKS_WINDOW' in codes(plan)

def test_object_over_column_blocked():
    plan=base();lv=plan.levels[0];col=lv.built_elements[0]
    x=sum(p.x for p in col.polygon)/len(col.polygon);y=sum(p.y for p in col.polygon)/len(col.polygon)
    table=next(o for o in lv.objects if o.kind=='table')
    table.center.x=x;table.center.y=y
    assert 'OBJECT_HITS_BUILT_ELEMENT' in codes(plan)

def test_shafts_and_columns_are_distinct_from_furniture():
    p=generate_template(TemplateRequest(include_core=True,floors=2))
    s=render_svg(p)
    assert 'layer-structure' in s and 'data-built-id="MEP_01"' in s
    assert 'data-core-id="STAIR_01"' in s and 'data-core-id="LIFT_01"' in s
    d=render_dxf(p)
    assert b'A-CORE' in d and b'A-STRUCT' in d and b'A-SHAFT' in d


def test_stair_mismatch_detected():
    p=generate_template(TemplateRequest(include_core=True,floors=2))
    p.levels[0].vertical_connectors[0].rise_mm=230
    assert 'STAIR_ELEVATION_MISMATCH' in codes(p)


def test_irregular_room_and_holes_are_distinct_geometry():
    p=generate_template(TemplateRequest(irregular_living=True))
    assert validate_plan(p).valid
    # Insert a footprint hole in the middle of an occupied room, which must be rejected.
    from architect.models import Point
    p.levels[0].footprint_holes=[[Point(x=1000,y=9000),Point(x=1600,y=9000),
                                  Point(x=1600,y=9600),Point(x=1000,y=9600)]]
    assert 'SPACE_OUTSIDE_FOOTPRINT' in codes(p) or 'ROOM_CROSSES_FOOTPRINT_HOLE' in codes(p)


def test_old_sample_is_now_rejected_for_bad_furniture():
    old=FloorPlan.model_validate(json.loads((ROOT/'examples/legacy_v2_plan_rejected.json').read_text()))
    report=validate_plan(old)
    assert not report.valid and 'BED_NO_HEADWALL' in {v.code for v in report.issues}
    result=suggest_bedroom_repair(old)
    assert result['proposed_report'].errors<report.errors
    assert result['changes']


def test_no_unjustified_export_or_false_success():
    raw=base().model_dump(mode='json');raw['levels'][0]['openings'][0]['host_wall_id']='DOES_NOT_EXIST'
    check=API.post('/api/validate',json={'plan':raw})
    assert check.status_code==200
    assert check.json()['valid'] is False
    assert API.post('/api/export/svg',json={'plan':raw}).status_code==422
    assert API.post('/api/export/dxf',json={'plan':raw}).status_code==422


def test_api_template_and_explicit_repair():
    r=API.post('/api/template',json={'bedrooms':3,'seed':123,'irregular_living':True})
    assert r.status_code==200,r.text[:1200]
    p=r.json()['plan'];assert r.json()['report']['valid']
    assert p['schema_version']=='1.1.0'
    assert API.post('/api/template',json={'bedrooms':40}).status_code==422
    rep=API.post('/api/repair/bedrooms',json={'plan':p})
    assert rep.status_code==200
    assert 'changes' in rep.json()
    assert API.get('/api/schema').json()['properties']['levels']
    assert API.get('/api/status').json()['schema_version']=='1.1.0'


def test_svg_dxf_exports_and_3d_fields():
    p=base();s=render_svg(p);d=render_dxf(p)
    assert s.startswith('<svg') and 'layer-dimensions' in s and 'data-object-id' in s
    assert b'HEADER' in d and len(d)>7000
    bed=find(p,'bed')
    assert bed.height_mm and bed.depth_mm and bed.width_mm and bed.base_z_mm==0


def test_ai_requires_explicit_key(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    r=API.post('/api/generate',json={'brief':'Plan a house with a three-bedroom family arrangement and a stair.'})
    assert r.status_code==503
