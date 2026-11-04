"""Property-aware concept generator: building/site hierarchy and independent dwelling units.

Uses deterministic candidate search. It does not certify structure, code, MEP, or egress.
"""
from __future__ import annotations
from collections import defaultdict
from math import hypot
from shapely.geometry import Polygon, Point as SPoint, LineString
from shapely.ops import unary_union
from pydantic import ValidationError
from .property_models import (PropertyRequest,PropertyProject,ParcelSite,SiteArea,
                              FeatureDecision,PropertyBuilding,UnitRecord)
from .models import (Point,Space,Wall,Opening,Level,FloorPlan,ProjectInfo,VerticalConnector,
                     PlacedObject,BuiltElement)
from .procedural import (P,rectangle,ring,TemplateRequest,generate_template,
                         _lines_from_rooms,_shared_wall,_outer_wall,add_furniture)
from .validate import at_wall,wall_length,validate_plan,poly
from .functional import polygon

class PlanningError(ValueError):
    pass

def policy(req:PropertyRequest):
    decisions=[]
    rules={
      'stairs':(req.floors>1,'Multiple occupied levels need designed vertical circulation; concept stair is included for multi-storey projects.'),
      'lift':(req.floors>=4 or req.accessibility_priority,'Automatically considered for 4+ floors or stated accessibility priority; not a building-code verdict.'),
      'garage':(False,'Garage only when explicitly required; outdoor parking is a separate request.'),
      'lawn':(False,'Private landscaping only when explicitly required; no automatic lawn insertion.'),
      'shaft':(False,'Dedicated service shaft only when explicitly required; MEP engineering remains unresolved.')}
    for name,(default,why) in rules.items():
        selection=getattr(req,name)
        include=selection=='required' or (selection=='auto' and default)
        if name=='stairs' and req.floors>1 and selection=='forbidden':
            raise PlanningError('Multi-storey request forbids stairs without a modeled alternative; cannot produce usable circulation.')
        if name=='lift' and req.floors==1 and selection=='required':
            raise PlanningError('A one-level lift with no level to serve is not modeled; change floors or lift requirement.')
        decisions.append(FeatureDecision(name=name,requested=selection,included=include,
                reason=('Explicit user requirement' if selection=='required' else 'Explicit exclusion' if selection=='forbidden' else why)))
    return decisions

def transform(pt,dx,dy,rotation=0,W=0,H=0):
    if rotation==180:return P(W-pt.x+dx,H-pt.y+dy)
    return P(pt.x+dx,pt.y+dy)

def move_level(lv,dx,dy,prefix,rotation=0):
    lv=lv.model_copy(deep=True)
    W=max(p.x for p in lv.footprint);H=max(p.y for p in lv.footprint)
    f=lambda pt:transform(pt,dx,dy,rotation,W,H)
    lv.footprint=[f(p) for p in lv.footprint]
    lv.footprint_holes=[[f(p) for p in h] for h in lv.footprint_holes]
    wallids={}
    for sp in lv.spaces:
        old=sp.id;sp.id=f'{prefix}_{old}';sp.name=f'{prefix.replace("U", "FLAT ")} · {sp.name}'
        sp.polygon=[f(p) for p in sp.polygon];sp.holes=[[f(p) for p in h] for h in sp.holes]
    for w in lv.walls:
        old=w.id;w.id=f'{prefix}_{old}';wallids[old]=w.id
        w.start=f(w.start);w.end=f(w.end)
    for o in lv.openings:
        o.id=f'{prefix}_{o.id}';o.host_wall_id=wallids[o.host_wall_id]
    for obj in lv.objects:
        obj.id=f'{prefix}_{obj.id}';obj.center=f(obj.center)
        if obj.space_id:obj.space_id=f'{prefix}_{obj.space_id}'
        if rotation:obj.rotation_degrees=((obj.rotation_degrees+rotation+180)%360)-180
    for b in lv.built_elements:
        b.id=f'{prefix}_{b.id}';b.polygon=[f(p) for p in b.polygon]
    for v in lv.vertical_connectors:
        v.id=f'{prefix}_{v.id}';v.polygon=[f(p) for p in v.polygon]
        v.landings=[[f(p) for p in r] for r in v.landings]
    for a in lv.annotations:a.id=f'{prefix}_{a.id}';a.at=f(a.at)
    for d in lv.dimensions:d.id=f'{prefix}_{d.id}';d.start=f(d.start);d.end=f(d.end)
    return lv

def _make_wing_module(bedrooms:int,W:int,H:int,seed:int):
    """A second *room adjacency topology*: vertical gallery with lateral bedroom wing."""
    if bedrooms>2:raise PlanningError('Wing topology currently supports up to two bedrooms; choose auto or linear')
    c0=int(W*.48/50)*50;c1=c0+1500
    ybed=int(H*.425/50)*50
    leftkitchen=int(W*.205/50)*50
    kitchenbottom=int(H*.305/50)*50
    specs=[
      ('living','L-SHAPED LIVING / DINING','living',ring((leftkitchen,0),(c0,0),(c0,H),(0,H),(0,kitchenbottom),(leftkitchen,kitchenbottom))),
      ('kitchen','KITCHEN','kitchen',rectangle(0,0,leftkitchen,kitchenbottom)),
      ('gallery','PRIVATE GALLERY','corridor',rectangle(c0,0,c1,H)),
      ('bedroom_1','PRIMARY BEDROOM','bedroom',rectangle(c1,0,W,ybed)),
      ('bedroom_2' if bedrooms==2 else 'study','BEDROOM 2' if bedrooms==2 else 'STUDY','bedroom' if bedrooms==2 else 'study',rectangle(c1,ybed,W,ybed*2)),
      ('bath','BATHROOM','bathroom',rectangle(c1,ybed*2,W,H))]
    spaces=[Space(id=i,name=n,kind=k,polygon=p) for i,n,k,p in specs]
    footprint=rectangle(0,0,W,H);outer=poly(footprint).boundary
    walls=[]
    for j,(a,b) in enumerate(_lines_from_rooms(spaces,footprint)):
        exterior=outer.distance(LineString([a,b]).interpolate(.5,normalized=True))<.1
        walls.append(Wall(id=f'W{j:03d}',start=P(*a),end=P(*b),
              thickness_mm=230 if exterior else 120,kind='exterior' if exterior else 'interior'))
    openings=[]
    for i,a,b,width in [('D_LIVING','living','gallery',1050),('D_KITCHEN','kitchen','living',850),
                         ('D_B1','bedroom_1','gallery',900),('D_B2','bedroom_2' if bedrooms==2 else 'study','gallery',900),
                         ('D_BATH','bath','gallery',850)]:
        w=_shared_wall(walls,spaces,a,b);L=wall_length(w)
        off=(L-width)/2
        openings.append(Opening(id=i,host_wall_id=w.id,kind='sliding_door',offset_mm=off,
                               width_mm=width,height_mm=2100,hinge='none',swing='none'))
    # Opening at south of living, facing the access yard / apartment lobby.
    ext=[w for w in _outer_wall(walls,spaces,'living') if abs(w.start.y-H)<.1 and abs(w.end.y-H)<.1]
    w=max(ext,key=wall_length)
    openings.append(Opening(id='D_ENTRY',host_wall_id=w.id,kind='sliding_door',offset_mm=(wall_length(w)-1100)/2,
                            width_mm=1100,height_mm=2200,hinge='none',swing='none'))
    for i in ('bedroom_1','bedroom_2' if bedrooms==2 else 'study','living','kitchen'):
        ext=_outer_wall(walls,spaces,i)
        ext=[w for w in ext if w.id != openings[-1].host_wall_id and wall_length(w)>1850]
        if not ext:continue
        w=max(ext,key=wall_length);L=wall_length(w);size=min(1400,L-650)
        openings.append(Opening(id=f'WN_{i}',host_wall_id=w.id,kind='window',offset_mm=(L-size)/2,
                     width_mm=size,height_mm=1300,sill_mm=900,hinge='none',swing='none'))
    level=Level(id='L0',name='Wing',footprint=footprint,spaces=spaces,walls=walls,openings=openings,objects=[])
    add_furniture(level,seed=seed)
    # Furniture and plumbing fitted into generously sized left-wing / lower rooms.
    level.objects.append(PlacedObject(id='sofa',name='Sofa',kind='sofa',center=P(900,H-1950),width_mm=1880,
               depth_mm=790,height_mm=850,rotation_degrees=-90,space_id='living'))
    level.objects.append(PlacedObject(id='k_sink',name='Sink',kind='sink',center=P(440,850),width_mm=480,
                depth_mm=480,height_mm=230,space_id='kitchen'))
    level.objects.append(PlacedObject(id='k_hob',name='Cooktop',kind='hob',center=P(440,1700),width_mm=470,
                depth_mm=460,height_mm=130,space_id='kitchen'))
    level.objects.append(PlacedObject(id='b_wc',name='WC',kind='wc',center=P(W-700,H-800),width_mm=490,
                depth_mm=650,height_mm=750,rotation_degrees=180,space_id='bath'))
    # Reusable enrichment: only include fixtures if the general collision/clearance
    # auditor still accepts the WHOLE room arrangement. Never draw decorative icons
    # without backing PlacedObject dimensions / room ownership.
    concept=FloorPlan(project=ProjectInfo(name='Wing topology',revision='V4'),levels=[level])
    optional=[
        ('dining_table','Dining Table','table',3200,H-2400,1520,900,750,'living',0),
        ('dining_chair_left','Dining Chair','chair',2240,H-2400,480,480,820,'living',0),
        ('dining_chair_right','Dining Chair','chair',4160,H-2400,480,480,820,'living',0),
        ('coffee_table','Coffee Table','table',2180,H-1750,850,540,430,'living',0),
        ('bath_shower','Shower','shower',c1+1140,H-780,1050,1010,2150,'bath',0),
        ('bath_basin','Basin','sink',W-2090,H-480,470,400,230,'bath',0),
        ('kitchen_counter','Kitchen Counter','counter',leftkitchen-470,730,470,1020,900,'kitchen',0),
    ]
    for ident,name,kind,x,y,width,depth,height,space,rot in optional:
        ob=PlacedObject(id=ident,name=name,kind=kind,center=P(x,y),width_mm=width,
                    depth_mm=depth,height_mm=height,space_id=space,rotation_degrees=rot)
        before=validate_plan(concept)
        level.objects.append(ob)
        after=validate_plan(concept)
        if after.errors>before.errors or after.warnings>before.warnings:
            level.objects.pop()
    # Prefer realistic hinged doors. Retain a sliding door where the swing would
    # block a room or fixture; every change is checked against the same validator.
    bywall={w.id:w for w in level.walls}
    for opening in level.openings:
        if not opening.id.startswith('D_') or opening.id=='D_ENTRY' or opening.kind!='sliding_door':continue
        wall=bywall[opening.host_wall_id];L=wall_length(wall)
        mid=at_wall(wall,opening.offset_mm+opening.width_mm/2)
        ux=(wall.end.x-wall.start.x)/L;uy=(wall.end.y-wall.start.y)/L
        normal=(-uy,ux)
        before=validate_plan(concept)
        options=[]
        target={'D_LIVING':'living','D_KITCHEN':'kitchen','D_B1':'bedroom_1',
                'D_B2':'bedroom_2' if bedrooms==2 else 'study','D_BATH':'bath'}.get(opening.id)
        target_shape=poly(next(s.polygon for s in level.spaces if s.id==target)) if target else None
        for hinge in ('start','end'):
            for swing in ('left','right'):
                opening.kind='door';opening.hinge=hinge;opening.swing=swing
                result=validate_plan(concept)
                if result.errors<=before.errors and result.warnings<=before.warnings:
                    hinge_point=at_wall(wall,opening.offset_mm if hinge=='start' else opening.offset_mm+opening.width_mm)
                    inside=bool(target_shape and target_shape.covers(SPoint(hinge_point[0]+normal[0]*(1 if swing=='right' else -1)*400,
                                                               hinge_point[1]+normal[1]*(1 if swing=='right' else -1)*400)))
                    options.append((0 if inside else 1,result.errors,result.warnings,hinge,swing))
        if options:
            _,_,_,hinge,swing=sorted(options)[0]
            opening.kind='door';opening.hinge=hinge;opening.swing=swing
        else:
            opening.kind='sliding_door';opening.hinge='none';opening.swing='none'
    return concept

def module_plan(req,variant,seed):
    W=max(11600,req.bedrooms_per_unit*3500+1400)
    H=11600
    if variant=='wing' and req.bedrooms_per_unit<=2:
        return _make_wing_module(req.bedrooms_per_unit,W,H,seed)
    return generate_template(TemplateRequest(bedrooms=req.bedrooms_per_unit,width_mm=W,depth_mm=H,
                seed=seed,irregular_living=variant=='irregular',include_core=False,floors=1))

def _rebuild_walls(spaces,footprint):
    outline=poly(footprint).boundary
    walls=[]
    for j,(a,b) in enumerate(_lines_from_rooms(spaces,footprint)):
        line=LineString([a,b])
        external=outline.distance(line.interpolate(.5,normalized=True))<.2
        walls.append(Wall(id=f'W_{j:04d}',start=P(*a),end=P(*b),
                          thickness_mm=250 if external else 145,
                          kind='exterior' if external else 'interior',structural=external))
    return walls

def _rehost_openings(originals,newwalls):
    """Rebase hosted opening distance onto the noded, deduplicated shared-wall topology."""
    openings=[];skipped=[]
    for opening,wall in originals:
        a=at_wall(wall,opening.offset_mm);b=at_wall(wall,opening.offset_mm+opening.width_mm)
        segment=LineString([a,b]);mid=segment.interpolate(.5,normalized=True)
        matches=[]
        for newwall in newwalls:
            nl=LineString([(newwall.start.x,newwall.start.y),(newwall.end.x,newwall.end.y)])
            if nl.distance(mid)>.5 or nl.buffer(1).intersection(segment).length<segment.length-.5:continue
            # A private window must never look directly into an adjacent flat/corridor.
            if opening.kind in ('window','vent') and newwall.kind!='exterior':continue
            offset=nl.project(SPoint(a));off2=nl.project(SPoint(b));offset=min(offset,off2)
            if offset<0 or offset+segment.length>nl.length+.5:continue
            matches.append((newwall,offset))
        if not matches:
            skipped.append(opening.id);continue
        nw,off=matches[0]
        o=opening.model_copy(deep=True);o.host_wall_id=nw.id;o.offset_mm=round(off,2)
        # Preserve the actual hinge physical location after re-orientation of wall centerlines.
        if opening.kind=='door':
            old_hinge=at_wall(wall,opening.offset_mm if opening.hinge!='end' else opening.offset_mm+opening.width_mm)
            new_start=at_wall(nw,off)
            o.hinge='start' if hypot(*[x-y for x,y in zip(old_hinge,new_start)])<10 else 'end'
            # V3 swing direction refers to host orientation; reverse if new wall orientation reversed.
            old_vec=(wall.end.x-wall.start.x,wall.end.y-wall.start.y)
            new_vec=(nw.end.x-nw.start.x,nw.end.y-nw.start.y)
            if old_vec[0]*new_vec[0]+old_vec[1]*new_vec[1]<0:
                o.swing='right' if opening.swing=='left' else 'left'
        openings.append(o)
    return openings,skipped

def _add_shared_opening(spaces,walls,out,name,a,b,*,width=1000,kind='sliding_door'):
    wall=_shared_wall(walls,spaces,a,b);length=wall_length(wall)
    if length<width+150:raise PlanningError(f'Insufficient wall between {a} and {b} for required opening')
    op=Opening(id=name,host_wall_id=wall.id,kind=kind,offset_mm=(length-width)/2,
           width_mm=width,height_mm=2200,hinge='none',swing='none')
    out.append(op);return op

def _add_outside(spaces,walls,footprint,out,roomid,name):
    line=poly(footprint).boundary
    shp=poly(next(s for s in spaces if s.id==roomid).polygon).boundary
    candidates=[]
    for w in walls:
        if w.kind!='exterior' or wall_length(w)<1150:continue
        wl=LineString([(w.start.x,w.start.y),(w.end.x,w.end.y)])
        if shp.intersection(wl).length>1100:candidates.append(w)
    if not candidates:raise PlanningError(f'No facade available for entrance into {roomid}')
    wall=max(candidates,key=wall_length)
    out.append(Opening(id=name,host_wall_id=wall.id,kind='sliding_door',
           offset_mm=(wall_length(wall)-1050)/2,width_mm=1050,height_mm=2200,hinge='none',swing='none'))

def build_one_floor(req,variant,seed,has_stairs,has_lift,has_shaft):
    """Build one coherent level. Returns canonical Level + unit records + common IDs."""
    count=req.units_per_floor
    W=max(11600,req.bedrooms_per_unit*3500+1400);H=11600
    layout='opposed' if variant=='opposed' and count==2 else 'linear'
    level_units=[];module_regions=[];oldopenings=[];objects=[];built=[]
    common=[];connectors=[]
    if layout=='linear':
        for i in range(count):
            orig=module_plan(req,'wing' if variant=='wing' else 'irregular' if variant=='irregular' else 'linear',seed+i*17)
            lv=move_level(orig.levels[0],i*W,0,f'U{i+1}')
            level_units.append(lv);module_regions.append(poly(lv.footprint))
        by=W*count
        common.append(Space(id='COMMON_GALLERY' if count>1 else 'PRIVATE_GALLERY',
                name='COMMON ACCESS GALLERY' if count>1 else 'PRIVATE ENTRY GALLERY',kind='corridor',
                polygon=rectangle(0,H,by,H+1850)))
        entry_common=common[0].id
        if has_stairs:
            common.append(Space(id='STAIRWELL',name='STAIR HALL',kind='stairwell',
                        polygon=rectangle(by,H-4700,by+4400,H)))
            common.append(Space(id='CORE_LOBBY',name='COMMON LOBBY' if count>1 else 'PRIVATE STAIR LOBBY',kind='lift_lobby',
                        polygon=rectangle(by,H,by+4400,H+1850)))
            if has_lift:
                common.append(Space(id='LIFT_SHAFT',name='LIFT SHAFT',kind='shaft',
                        polygon=rectangle(by+4400,H-2800,by+6800,H)))
                common.append(Space(id='LIFT_LOBBY',name='LIFT LOBBY',kind='lift_lobby',
                        polygon=rectangle(by+4400,H,by+6800,H+1850)))
        elif count>1:
            common.append(Space(id='COMMON_LOBBY',name='COMMON ENTRANCE LOBBY',kind='lift_lobby',
                        polygon=rectangle(by,H,by+2600,H+1850)))
    else:
        # Two households face a real central common corridor, rather than one subdivided dwelling.
        for i in range(2):
            orig=module_plan(req,'linear',seed+i*17)
            lv=move_level(orig.levels[0],0,(0 if i==0 else H+1850),f'U{i+1}',rotation=0 if i==0 else 180)
            # top unit entrance faces down, bottom unit entrance faces up.
            level_units.append(lv);module_regions.append(poly(lv.footprint))
        common.append(Space(id='COMMON_GALLERY',name='CENTRAL COMMON CORRIDOR',kind='corridor',
                   polygon=rectangle(0,H,W,H+1850)))
        entry_common='COMMON_GALLERY';by=W
        if has_stairs:
            common.append(Space(id='STAIRWELL',name='STAIR HALL',kind='stairwell',
                   polygon=rectangle(W,H-4700,W+4400,H)))
            common.append(Space(id='CORE_LOBBY',name='CORE LOBBY',kind='lift_lobby',
                   polygon=rectangle(W,H,W+4400,H+1850)))
            if has_lift:
                common.append(Space(id='LIFT_SHAFT',name='LIFT SHAFT',kind='shaft',
                   polygon=rectangle(W+4400,H-2800,W+6800,H)))
                common.append(Space(id='LIFT_LOBBY',name='LIFT LOBBY',kind='lift_lobby',
                   polygon=rectangle(W+4400,H,W+6800,H+1850)))
        else:
            common.append(Space(id='COMMON_LOBBY',name='COMMON ENTRANCE LOBBY',kind='lift_lobby',
                   polygon=rectangle(W,H,W+2600,H+1850)))
    spaces=[s for lv in level_units for s in lv.spaces]+common
    rectangles=[poly(s.polygon) for s in spaces]
    footprint_shape=unary_union(rectangles)
    if footprint_shape.geom_type!='Polygon' or not footprint_shape.is_valid:
        raise PlanningError('Generated building envelope is not a single connected valid polygon')
    footprint=[P(*p) for p in list(footprint_shape.exterior.coords)[:-1]]
    walls=_rebuild_walls(spaces,footprint)
    for lv in level_units:
        wmap={w.id:w for w in lv.walls}
        oldopenings.extend((o,wmap[o.host_wall_id]) for o in lv.openings)
        objects+=lv.objects;built+=lv.built_elements
    opens,skips=_rehost_openings(oldopenings,walls)
    if any('_D_ENTRY' in item for item in skips):raise PlanningError('Could not retain an apartment entry after wall merging')
    if 'COMMON_LOBBY' in [s.id for s in common]:
        _add_shared_opening(spaces,walls,opens,'D_GALLERY_LOBBY',entry_common,'COMMON_LOBBY',width=1000)
        _add_outside(spaces,walls,footprint,opens,'COMMON_LOBBY','D_MAIN_EXTERNAL')
    elif has_stairs:
        _add_shared_opening(spaces,walls,opens,'D_GALLERY_LOBBY',entry_common,'CORE_LOBBY',width=1000)
        _add_shared_opening(spaces,walls,opens,'D_STAIR','STAIRWELL','CORE_LOBBY',width=1100)
        _add_outside(spaces,walls,footprint,opens,'CORE_LOBBY','D_MAIN_EXTERNAL')
        sx,sy,sX,sY=poly(next(s.polygon for s in common if s.id=='STAIRWELL')).bounds
        cp=rectangle(sx+210,sy+240,sX-210,sY-200)
        connector=VerticalConnector(id='CORE_STAIR',name='Two-flight vertical stair (concept)',kind='stair',
            polygon=cp,serves_level_ids=[f'L{i}' for i in range(req.floors)],
            step_count=18,rise_mm=175,going_mm=255,
            landings=[rectangle(sx+260,sy+280,sX-260,sy+1170),
                      rectangle(sx+260,sY-1110,sX-260,sY-220)])
        connectors.append(connector)
        if has_lift:
            _add_shared_opening(spaces,walls,opens,'D_CORE_LIFT_LOBBY','CORE_LOBBY','LIFT_LOBBY',width=1000)
            _add_shared_opening(spaces,walls,opens,'D_LIFT','LIFT_LOBBY','LIFT_SHAFT',width=900)
            qx,qy,qX,qY=poly(next(s.polygon for s in common if s.id=='LIFT_SHAFT')).bounds
            connectors.append(VerticalConnector(id='CORE_LIFT',name='Passenger lift (concept)',kind='lift',
                 polygon=rectangle(qx+120,qy+120,qX-120,qY-120),serves_level_ids=[f'L{i}' for i in range(req.floors)],
                 cabin_width_mm=qX-qx-500,cabin_depth_mm=qY-qy-400,door_opening_id='D_LIFT'))
    else:
        _add_outside(spaces,walls,footprint,opens,entry_common,'D_MAIN_EXTERNAL')
    if has_shaft:
        # Add a shaft as an adjacent service enclosure that does NOT consume a living space.
        # This is implemented as a void in an explicit service-space module.
        # If there is no physical core, refuse it rather than placing it through a bedroom.
        if not has_stairs:raise PlanningError('This generator requires a designed core for an explicit service shaft')
        # Use a small protected zone in the stair hall that is not used as a landing.
        # A 600mm duct is an indicative placeholder, not a coordinated MEP riser.
        bx=by+270;yy=H-4450
        built.append(BuiltElement(id='MEP_SHAFT_01',name='Service riser (concept)',kind='shaft',
            polygon=rectangle(bx,yy,bx+600,yy+650),height_mm=3000))
    lv=Level(id='L0',name='Ground Floor',footprint=footprint,spaces=spaces,walls=walls,
             openings=opens,objects=objects,built_elements=built,vertical_connectors=connectors)
    unit_records=[]
    for i,mod in enumerate(level_units):
        prefix=f'U{i+1}'
        ent=next((o.id for o in opens if o.id==f'{prefix}_D_ENTRY'),None)
        if not ent:raise PlanningError(f'Unit {prefix} has no entrance')
        unit_records.append(UnitRecord(id=f'{prefix}_L0',name=f'Flat {i+1}',level_id='L0',
              space_ids=[s.id for s in mod.spaces],entrance_opening_id=ent))
    return lv,unit_records,[s.id for s in common],skips


def make_garage(x,y):
    footprint=rectangle(0,0,3900,6100)
    room=Space(id='garage',name='ENCLOSED GARAGE',kind='garage',polygon=footprint)
    walls=_rebuild_walls([room],footprint)
    bottom=next(w for w in walls if abs(w.start.y-6100)<.1 and abs(w.end.y-6100)<.1)
    door=Opening(id='D_GARAGE',host_wall_id=bottom.id,kind='sliding_door',offset_mm=(wall_length(bottom)-2800)/2,
                 width_mm=2800,height_mm=2500,hinge='none',swing='none')
    plan=FloorPlan(project=ProjectInfo(name='Garage Outbuilding',revision='V4'),
           levels=[Level(id='L0',name='Garage',footprint=footprint,spaces=[room],walls=walls,openings=[door])])
    return PropertyBuilding(id='garage_block',name='Detached Garage',site_origin=P(x,y),plan=plan,
                            summary='Detached enclosed garage; vehicle clearances are indicative')

def generate_property(request:PropertyRequest,variant:str|None=None,seed:int|None=None):
    req=request.model_copy(deep=True)
    if seed is not None:req.seed=seed
    choices=policy(req);flags={i.name:i.included for i in choices}
    if req.property_type=='apartment' and req.units_per_floor==1 and req.floors==1:
        # One self-contained unit with no unjustified shared gallery.
        pass
    variant=variant or ('wing' if req.layout_strategy=='wing' else 'irregular' if req.layout_strategy=='irregular' else 'opposed' if req.layout_strategy=='opposed' else 'linear')
    if variant=='opposed' and req.units_per_floor!=2:raise PlanningError('Opposed layout requires exactly two independent units per floor')
    if variant=='wing' and req.bedrooms_per_unit>2:raise PlanningError('Wing topology has two-bedroom capacity; use a different strategy')
    if flags['shaft'] and not flags['stairs']:
        raise PlanningError('Dedicated riser requires a designed service core; choose stair/core enabled')
    has_stairs=flags['stairs'];has_lift=flags['lift']
    if req.units_per_floor==1 and not has_stairs:
        plan=module_plan(req,variant,req.seed)
        level=plan.levels[0]
        units=[UnitRecord(id='U1_L0',name='Private Home',level_id='L0',
                 space_ids=[s.id for s in level.spaces],entrance_opening_id='D_ENTRY')]
        common_ids=[];skipped=[]
    else:
        level,units,common_ids,skipped=build_one_floor(req,variant,req.seed,has_stairs,has_lift,flags['shaft'])
        plan=FloorPlan(project=ProjectInfo(name='Property Block',revision='V4'),levels=[level])
    # Shared structure and apartment footprints are modelled per floor, not copied as separate buildings.
    if req.floors>1:
        for i in range(1,req.floors):
            dup=level.model_copy(deep=True)
            dup.id=f'L{i}';dup.name=f'Level {i+1}';dup.elevation_mm=3150*i
            # No street entrances hovering in upper levels; access is via the vertical core.
            dup.openings=[o for o in dup.openings if o.id!='D_MAIN_EXTERNAL']
            plan.levels.append(dup)
            for u in [u for u in units if u.level_id=='L0']:
                units.append(u.model_copy(update={'id':u.id.replace('_L0',f'_L{i}'),'level_id':f'L{i}'}))
    if req.property_type in ('villa','duplex'):
        # One continuous home across several levels, not one apartment per floor.
        for u in units:
            u.dwelling_id='HOUSE_1';u.name='Private Home' if req.property_type=='villa' else 'Duplex Home'
    if req.property_type=='mixed_use':
        # Retail arcade on level 0 and independent residential apartments above.
        # Public ground access and private stair-lobby access use separate facade entries.
        if not has_stairs:
            raise PlanningError('Mixed use needs a separately modeled vertical residential core')
        ground=plan.levels[0]
        for sp in ground.spaces:
            if sp.id.startswith('U'):
                orig=sp.kind
                if orig in ('bedroom','living','study','dining'):
                    sp.kind='office';sp.name=sp.name.replace('BEDROOM','RETAIL').replace('LIVING / DINING','SHOWROOM').replace('STUDY','DISPLAY')
                    sp.tags=['retail_arcade','ground_commercial']
                elif orig in ('kitchen','utility'):
                    sp.kind='storage';sp.name=sp.name.replace('KITCHEN','STAFF / STOCK').replace('UTILITY / LAUNDRY','STOCKROOM')
                    sp.tags=['shop_service']
                elif orig=='bathroom':
                    sp.kind='toilet';sp.name=sp.name.replace('BATHROOM','SHOP WC')
                elif orig=='corridor':
                    sp.name=sp.name.replace('CENTRAL CORRIDOR','PRIVATE SHOP ACCESS')
        for ob in ground.objects:
            if ob.kind=='bed':ob.kind='table';ob.name='Retail display table';ob.placement='freestanding'
            elif ob.kind=='wardrobe':ob.kind='cabinet';ob.name='Merchandise shelving';ob.placement='wall_anchored'
            elif ob.kind=='sofa':ob.name='Showroom seating'
        for u in units:
            u.dwelling_id=f'SHOP_{u.id.split("_")[0]}' if u.level_id=='L0' else f'RES_{u.level_id}_{u.id.split("_")[0]}'
            u.kind='retail' if u.level_id=='L0' else 'residence'
            u.name=('Shop ' if u.level_id=='L0' else 'Apartment ')+u.id.split('_')[0][1:]
        shared=next((sp for sp in ground.spaces if sp.id in ('COMMON_GALLERY','PRIVATE_GALLERY')),None)
        if shared:
            # Commercial/public entrance is not the private residential-lobby door.
            _add_outside(ground.spaces,ground.walls,ground.footprint,ground.openings,shared.id,'D_PUBLIC_ARCADE')
        # The connecting arcade-to-core doorway still requires access-control/fire review.
    plan.project=ProjectInfo(name=f'{req.property_type.title()} · {req.units_per_floor} unit(s) per level',
       description='Site-aware schematic concept with independent private units and shared circulation',revision='V4')
    # Locate primary building with room for garage and garden, if requested.
    shp=poly(level.footprint);minx,miny,maxx,maxy=shp.bounds
    bw=maxx-minx;bh=maxy-miny
    leftlane=5300 if flags['garage'] else 0
    ox=max(req.concept_margin_mm+400,leftlane+req.concept_margin_mm+400)
    oy=max(req.concept_margin_mm+800,1600)
    if ox+bw+req.concept_margin_mm>req.plot_width_mm or oy+bh+req.concept_margin_mm>req.plot_depth_mm:
        raise PlanningError(f'BUILDING_NOT_FIT: envelope {bw/1000:.1f}×{bh/1000:.1f}m plus conceptual margins cannot fit {req.plot_width_mm/1000:.1f}×{req.plot_depth_mm/1000:.1f}m plot; enlarge plot or reduce units/features')
    primary=PropertyBuilding(id='main',name='Main Building',site_origin=P(ox-minx,oy-miny),plan=plan,
                            units=units,common_space_ids={l.id:common_ids for l in plan.levels},
                            summary=f'{len(plan.levels)} floors, {len(units)} modeled units; strategy {variant}')
    buildings=[primary];areas=[]
    if flags['garage'] and req.parking_spaces>1:
        raise PlanningError('One enclosed garage models one car; additional parking bays must be planned separately. Reduce the requested parking count or turn off garage to use open bays.')
    if flags['garage']:
        gx=max(900,req.concept_margin_mm+50);gy=req.plot_depth_mm-7400
        garage=make_garage(gx,gy)
        gp=poly(garage.plan.levels[0].footprint)
        mainpoly=shp.translate if False else poly(level.footprint)
        from shapely.affinity import translate
        if translate(gp,xoff=gx,yoff=gy).intersects(translate(shp,xoff=ox-minx,yoff=oy-miny)):
            raise PlanningError('Garage and main building would overlap; increase plot width/depth')
        if gy+6100>req.plot_depth_mm-400:raise PlanningError('Insufficient forecourt for garage access')
        buildings.append(garage)
        # Driveway ends directly at the garage opening and at the south road.
        areas.append(SiteArea(id='driveway_garage',kind='driveway',label='VEHICLE ACCESS',
                    polygon=rectangle(gx+250,gy+6100,gx+3650,req.plot_depth_mm),
                    attributes={'surface':'concrete','clear_width_mm':3400}))
        areas.append(SiteArea(id='gate_garage',kind='gate',label='VEHICLE GATE',
                    polygon=rectangle(gx+250,req.plot_depth_mm-90,gx+3650,req.plot_depth_mm),
                    attributes={'opening_width_mm':3400}))
    elif req.parking_spaces:
        bays=min(req.parking_spaces,req.plot_width_mm//2850)
        if bays<req.parking_spaces:
            raise PlanningError('Not enough frontage for requested parking bays in this schematic parking strategy')
        px=req.concept_margin_mm+450
        py=req.plot_depth_mm-7100
        if py<oy+bh+650:
            raise PlanningError('No space for parking in front yard; increase plot depth')
        for i in range(bays):
            x=px+i*2800
            areas.append(SiteArea(id=f'parking_{i+1}',kind='parking_bay',label=f'P{i+1}',
                polygon=rectangle(x,py,x+2600,py+5200),attributes={'stall_width_mm':2600,'stall_length_mm':5200}))
        areas.append(SiteArea(id='parking_aisle',kind='driveway',label='ACCESS AISLE',
                 polygon=rectangle(px,py+5300,px+bays*2800,req.plot_depth_mm),
                 attributes={'maneuvering_layout':'schematic; traffic engineer review required'}))
        areas.append(SiteArea(id='entry_gate',kind='gate',label='ENTRY',polygon=rectangle(px+100,req.plot_depth_mm-90,
                     min(px+bays*2800-100,req.plot_width_mm-800),req.plot_depth_mm)))
    # Outdoor lawn only when requested. Choose a genuine non-overlapping area.
    if flags['lawn']:
        from shapely.affinity import translate
        main=translate(shp,xoff=ox-minx,yoff=oy-miny)
        other=[translate(poly(b.plan.levels[0].footprint),xoff=b.site_origin.x,yoff=b.site_origin.y) for b in buildings[1:]]
        taken=unary_union([main,*other,*[poly(a.polygon) for a in areas if a.kind not in ('gate',)]])
        proposals=[Polygon([(ox,oy+bh+900),(ox+bw,oy+bh+900),(ox+bw,req.plot_depth_mm-850),(ox,req.plot_depth_mm-850)]),
                   Polygon([(ox+bw+900,oy),(req.plot_width_mm-800,oy),(req.plot_width_mm-800,oy+bh),(ox+bw+900,oy+bh)]),
                   Polygon([(850,850),(ox-800,850),(ox-800,oy+bh),(850,oy+bh)])]
        available=[p for p in proposals if p.is_valid and p.area>10e6 and p.difference(taken).area>=p.area-.5]
        if not available:raise PlanningError('A usable uninterrupted lawn cannot be placed in the remaining plot area')
        chosen=max(available,key=lambda p:p.area)
        areas.append(SiteArea(id='private_lawn',kind='lawn',label='LANDSCAPED LAWN',
             polygon=[P(*p) for p in list(chosen.exterior.coords)[:-1]],attributes={'landscape_stage':'concept'}))
    # Pedestrian access traces the ACTUAL hosted entrance geometry, rather than
    # drawing a decorative path at an arbitrary x coordinate. Crossing the grass
    # is intentional: a paved path replaces its surface under the walkway.
    from shapely.affinity import translate
    l=plan.levels[0]
    entrance=next((o for o in l.openings if o.id in ('D_MAIN_EXTERNAL','D_ENTRY')),None)
    footpath_added=False
    if entrance:
        host=next((w for w in l.walls if w.id==entrance.host_wall_id),None)
        if host:
            at=at_wall(host,entrance.offset_mm+entrance.width_mm/2)
            line=LineString([(host.start.x,host.start.y),(host.end.x,host.end.y)])
            ux=(host.end.x-host.start.x)/line.length;uy=(host.end.y-host.start.y)/line.length
            norm=(-uy,ux);local=poly(l.footprint)
            if local.covers(SPoint(at[0]+norm[0]*500,at[1]+norm[1]*500)):
                norm=(-norm[0],-norm[1])
            ex=at[0]+primary.site_origin.x;ey=at[1]+primary.site_origin.y
            p0=(ex+norm[0]*720,ey+norm[1]*720)
            p1=(ex+norm[0]*1450,ey+norm[1]*1450)
            # If the entrance is on the back facade, route around the building.
            mainworld=translate(local,xoff=primary.site_origin.x,yoff=primary.site_origin.y)
            trial=LineString([p0,p1,(p1[0],req.plot_depth_mm-120)])
            if trial.buffer(520).intersection(mainworld).area>350:
                edge=mainworld.bounds[2]+1050
                trial=LineString([p0,p1,(edge,p1[1]),(edge,req.plot_depth_mm-120)])
            path=trial.buffer(530,cap_style=2,join_style=2).intersection(poly(rectangle(0,0,req.plot_width_mm,req.plot_depth_mm)))
            if path.geom_type=='Polygon' and path.is_valid:
                conflicts=[poly(a.polygon) for a in areas if a.kind in ('driveway','parking_bay')]
                if (path.intersection(mainworld).area<350 and
                    all(path.intersection(c).area<350 for c in conflicts)):
                    areas.append(SiteArea(id='pedestrian_path',kind='walkway',label='RESIDENTIAL ENTRY PATH',
                         polygon=[P(*p) for p in list(path.exterior.coords)[:-1]],
                         attributes={'connects_to_opening':entrance.id,'slope_and_accessibility_unverified':True}))
                    footpath_added=True
    if skipped:notes=[f'{len(skipped)} internal-facing module windows or split-wall openings removed: '+', '.join(skipped[:10])]
    else:notes=[]
    if not footpath_added:notes.append('No conflict-free road-to-entry footpath was generated; pedestrian access needs manual design.')
    if req.property_type=='mixed_use':notes.append('Retail ground-floor arcade; residential access-control, fire separation and commercial services need dedicated design review.')
    notes.append('No jurisdiction-specific setback, accessibility, fire, parking or structural compliance is asserted.')
    req.layout_strategy=variant if variant in ('linear','wing','opposed','irregular') else 'linear'
    return PropertyProject(request=req,site=ParcelSite(boundary=rectangle(0,0,req.plot_width_mm,req.plot_depth_mm),
                  assumptions=['Plot geometry is illustrative and must be surveyed','Road is on the south/page-bottom edge']),
              site_areas=areas,buildings=buildings,feature_decisions=choices,design_notes=notes,
              limitations=['Schematic design, not construction documents','Structure, MEP and fire escape require licensed review',
                           'Auto-inclusion policies are design heuristics, not regulations'])
