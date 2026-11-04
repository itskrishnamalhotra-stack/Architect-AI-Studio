"""Architect AI Studio V4: property hierarchy, features, access and exports."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from shapely.affinity import translate
from architect.property_models import PropertyRequest,PropertyProject
from architect.property_generator import generate_property,PlanningError
from architect.property_search import generate_alternatives
from architect.property_validate import audit_property
from architect.property_render import render_site_svg,render_floor_svg,render_floor_dxf
from architect.validate import poly,validate_plan
from app import app

API=TestClient(app)
def request(**kw):return PropertyRequest(**kw)
def create(**kw):
    p=generate_property(request(**kw));r=audit_property(p)
    assert r.errors==0,[(i.code,i.message) for i in r.issues if i.severity=='error']
    return p

def test_default_single_storey_does_not_insert_unrequested_core_or_amenity():
    p=create()
    lv=p.buildings[0].plan.levels[0]
    assert len(lv.vertical_connectors)==0
    assert len(p.buildings)==1 and all(a.kind not in ('lawn','parking_bay') for a in p.site_areas)
    assert len(p.buildings[0].units)==1
    assert any(a.kind=='walkway' for a in p.site_areas)
    assert all(not x.included for x in p.feature_decisions)

def test_sculpted_room_topology_and_real_furniture_rules():
    p=create(layout_strategy='wing')
    lv=p.buildings[0].plan.levels[0]
    assert any(len(s.polygon)>=6 for s in lv.spaces)
    assert len([o for o in lv.objects if o.kind=='bed'])==2
    assert any(o.kind=='table' and o.space_id=='living' for o in lv.objects)
    assert all(not any(i.code.startswith('FLOOR_BED_NO_HEADWALL') for i in audit_property(p).issues) for _ in [0])

def test_explicit_garage_lawn_driveway_access_and_building_boundaries():
    p=create(garage='required',lawn='required',plot_width_mm=25000,plot_depth_mm=28000)
    assert len(p.buildings)==2
    assert {'lawn','driveway','gate','walkway'}<=set(a.kind for a in p.site_areas)
    main=p.buildings[0];garage=p.buildings[1]
    m=translate(poly(main.plan.levels[0].footprint),xoff=main.site_origin.x,yoff=main.site_origin.y)
    g=translate(poly(garage.plan.levels[0].footprint),xoff=garage.site_origin.x,yoff=garage.site_origin.y)
    assert m.intersection(g).area==0
    assert 'site_private_lawn' in render_site_svg(p)

def test_two_independently_accessible_units_on_one_floor():
    p=create(property_type='apartment',units_per_floor=2,plot_width_mm=35500,plot_depth_mm=27000)
    block=p.buildings[0];lv=block.plan.levels[0]
    assert len(block.units)==2
    assert set(block.units[0].space_ids).isdisjoint(block.units[1].space_ids)
    assert len(block.common_space_ids['L0'])>=2
    assert {u.entrance_opening_id for u in block.units} <= {o.id for o in lv.openings}
    assert all(u.entrance_opening_id!=block.units[0].entrance_opening_id for u in block.units[1:])

def test_opposed_is_distinct_real_room_topology():
    kw={'property_type':'apartment','units_per_floor':2,'plot_width_mm':35500,'plot_depth_mm':34000}
    p=create(**kw,layout_strategy='opposed');q=create(**kw,layout_strategy='linear')
    assert poly(p.buildings[0].plan.levels[0].footprint).bounds != poly(q.buildings[0].plan.levels[0].footprint).bounds
    rooms={s.id:s for s in p.buildings[0].plan.levels[0].spaces}
    assert rooms['COMMON_GALLERY'].name=='CENTRAL COMMON CORRIDOR'

def test_multilevel_core_and_optional_lift():
    p=create(property_type='apartment',units_per_floor=2,floors=3,plot_width_mm=35500,plot_depth_mm=30000)
    assert len(p.buildings[0].plan.levels)==3
    assert all(any(c.kind=='stair' for c in lv.vertical_connectors) for lv in p.buildings[0].plan.levels)
    assert all(not any(c.kind=='lift' for c in lv.vertical_connectors) for lv in p.buildings[0].plan.levels)
    assert audit_property(p).metrics['independent_units']==6

def test_explicit_lift_and_service_shaft_included():
    p=create(property_type='apartment',units_per_floor=2,floors=3,
             lift='required',shaft='required',plot_width_mm=39500,plot_depth_mm=30000)
    lv=p.buildings[0].plan.levels[0]
    assert any(c.kind=='lift' and len(c.serves_level_ids)==3 for c in lv.vertical_connectors)
    assert any(e.kind=='shaft' for e in lv.built_elements)

def test_duplex_is_one_residence_not_two_flats():
    p=create(property_type='duplex',floors=2,plot_width_mm=30000,plot_depth_mm=30000)
    assert audit_property(p).metrics['independent_units']==1
    assert len({u.dwelling_id for u in p.buildings[0].units})==1

def test_mixed_use_retail_ground_and_residential_above():
    p=create(property_type='mixed_use',floors=3,units_per_floor=2,plot_width_mm=38000,plot_depth_mm=31000)
    lv=p.buildings[0].plan.levels[0]
    assert {u.kind for u in p.buildings[0].units if u.level_id=='L0'}=={'retail'}
    assert all(u.kind=='residence' for u in p.buildings[0].units if u.level_id=='L1')
    assert any(o.id=='D_PUBLIC_ARCADE' for o in lv.openings)
    assert audit_property(p).metrics['independent_units']==6  # 2 shops and 4 separate flats across two residential levels

def test_constraints_fail_loudly_and_never_squeeze():
    with pytest.raises(ValidationError):request(floors=2,stairs='forbidden')
    with pytest.raises(PlanningError,match='BUILDING_NOT_FIT'):
        generate_property(request(property_type='apartment',units_per_floor=2,plot_width_mm=15000,plot_depth_mm=16000))
    with pytest.raises(PlanningError,match='One enclosed garage'):
        generate_property(request(garage='required',parking_spaces=3))

def test_ownership_tampering_causes_export_rejection():
    p=create(property_type='apartment',units_per_floor=2,plot_width_mm=35000,plot_depth_mm=27000)
    p.buildings[0].units[1].space_ids.append(p.buildings[0].units[0].space_ids[0])
    r=audit_property(p)
    assert not r.valid and any(i.code=='ROOM_OWNED_TWICE' for i in r.issues)
    resp=API.post('/api/v4/export/svg',json={'project':p.model_dump(mode='json')})
    assert resp.status_code==422

def test_v4_api_status_schema_sample_and_exports():
    assert API.get('/').status_code==200
    assert 'Layout alternatives' in API.get('/').text
    assert 'id="alternatives_count"' in API.get('/').text
    assert 'id="alternative_list"' in API.get('/').text
    assert API.get('/legacy').status_code==200
    assert API.get('/api/v4/status').json()['schema_version']=='2.0.0'
    assert 'buildings' in API.get('/api/v4/schema').json()['properties']
    sample=API.get('/api/v4/sample').json()
    r=API.post('/api/v4/validate',json={'project':sample})
    assert r.status_code==200 and r.json()['valid']
    site=API.post('/api/v4/render',json={'project':sample,'view':'site'})
    assert site.status_code==200 and '<svg' in site.json()['svg']
    svg=API.post('/api/v4/export/svg',json={'project':sample,'view':'floor'})
    assert svg.status_code==200 and b'layer-dimensions' in svg.content
    dxf=API.post('/api/v4/export/dxf',json={'project':sample})
    assert dxf.status_code==200 and b'HEADER' in dxf.content
    assert len(dxf.content)>10000

def test_alternatives_are_distinct_and_invalid_briefs_return_error():
    r=API.post('/api/v4/alternatives',json={'alternatives':3,'bedrooms_per_unit':2})
    assert r.status_code==200,r.text[:600]
    data=r.json()
    assert len(data['alternatives'])==3
    assert len({x['strategy'] for x in data['alternatives']})==3
    assert all(x['report']['valid'] for x in data['alternatives'])
    bad=API.post('/api/v4/alternatives',json={'floors':3,'stairs':'forbidden'})
    assert bad.status_code==422

def test_api_ai_needs_server_key(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    response=API.post('/api/v4/ai-brief',json={'brief':'Generate a two-storey property with two flats on each floor and shared stair access.'})
    assert response.status_code==503


def test_door_blocking_wardrobe_is_rejected_at_property_level():
    from architect.models import PlacedObject,Point
    from architect.functional import door_approaches
    from architect.validate import wall_length
    from shapely.geometry import Point as SPoint
    p=create()
    level=p.buildings[0].plan.levels[0]
    opening=next(o for o in level.openings if o.id=='D_LIVING')
    wall=next(w for w in level.walls if w.id==opening.host_wall_id)
    room=next(s for s in level.spaces if s.id=='living')
    centre=next(z.centroid for z in door_approaches(wall,opening) if poly(room.polygon).covers(z.centroid))
    level.objects.append(PlacedObject(id='blocking_wardrobe',name='Wardrobe across doorway',kind='wardrobe',
        center=Point(x=centre.x,y=centre.y),width_mm=700,depth_mm=550,height_mm=2350,space_id='living'))
    report=audit_property(p)
    assert not report.valid
    assert any('DOOR_APPROACH_BLOCKED' in x.code for x in report.issues)
