"""Parametric offline layout generator used for adversarial validation and reproducible demos.

Not a universal architectural optimizer. The AI generator may propose arbitrary topology,
but both it and these offline templates must pass the SAME deterministic checks.
"""
from __future__ import annotations
from collections import defaultdict
import math, random
from pydantic import BaseModel, Field
from shapely.geometry import Polygon, LineString, Point as SPoint
from shapely.ops import unary_union
from .models import (FloorPlan, ProjectInfo, Point, Level, Space, Wall, Opening,
                     PlacedObject, BuiltElement, VerticalConnector)
from .validate import validate_plan, wall_length, at_wall, object_polygon
from .functional import door_approaches, back_edge, front_zone, polygon

class TemplateRequest(BaseModel):
    bedrooms: int = Field(default=3, ge=1, le=4)
    width_mm: int = Field(default=13200, ge=10500, le=25000)
    depth_mm: int = Field(default=11600, ge=9500, le=22000)
    seed: int = Field(default=42, ge=0, le=1000000)
    irregular_living: bool = False
    include_core: bool = False
    floors: int = Field(default=1, ge=1, le=3)


def P(x,y):return Point(x=float(round(x,2)),y=float(round(y,2)))
def ring(*pts):return [P(*xy) for xy in pts]
def rectangle(a,b,c,d):return ring((a,b),(c,b),(c,d),(a,d))

def _lines_from_rooms(rooms,outer):
    edges=[]
    for r in rooms:
        q=r.polygon
        edges.extend(LineString([(a.x,a.y),(b.x,b.y)]) for a,b in zip(q,q[1:]+q[:1]))
    q=outer
    edges.extend(LineString([(a.x,a.y),(b.x,b.y)]) for a,b in zip(q,q[1:]+q[:1]))
    merged=unary_union(edges)
    seq=[]
    def process(x):
        if x.geom_type=='LineString':
            for a,b in zip(x.coords,list(x.coords)[1:]):
                if math.dist(a,b)>80:seq.append((a,b))
        else:
            for sub in getattr(x,'geoms',[]):process(sub)
    process(merged)
    # Canonical orientation ensures offsets are deterministic, not generated randomly.
    unique={}
    for a,b in seq:
        aa=tuple(round(t,1) for t in a);bb=tuple(round(t,1) for t in b)
        key=tuple(sorted([aa,bb]));unique[key]=key
    return list(unique.values())

def _shared_wall(walls,spaces,a,b):
    sa=next(s for s in spaces if s.id==a);sb=next(s for s in spaces if s.id==b)
    seg=polygon(sa.polygon).boundary.intersection(polygon(sb.polygon).boundary)
    options=[]
    for w in walls:
        l=LineString([(w.start.x,w.start.y),(w.end.x,w.end.y)])
        shared=l.intersection(seg).length
        if shared>1050:options.append((shared,w))
    if not options:raise ValueError(f'No wall separating {a} and {b}')
    return max(options,key=lambda x:x[0])[1]

def _outer_wall(walls, rooms, room_id, omit_ids=()):
    boundary=polygon(next(r for r in rooms if r.id==room_id).polygon).boundary
    candidates=[]
    for w in walls:
        if w.kind=='exterior' and w.id not in omit_ids:
            line=LineString([(w.start.x,w.start.y),(w.end.x,w.end.y)])
            if boundary.intersection(line).length>1000:candidates.append(w)
    return sorted(candidates,key=wall_length,reverse=True)

def add_furniture(level: Level, *, seed=42, sources=None):
    """Layout-aware candidates from *arbitrary* polygon edges; no fixed x/y bedroom grid.

    Sequential fit: bed near a wall first; wardrobes are evaluated against door
    approaches, the entire bed outline, and required working zone. If no placement
    passes, the item remains unplaced (never invent a successful room).
    """
    rng=random.Random(seed)
    sources=sources or {}
    walls={w.id:w for w in level.walls}
    def blocked_by_doors(shape,room):
        for op in level.openings:
            if op.kind not in {'door','sliding_door','opening','arch'}:continue
            w=walls.get(op.host_wall_id)
            if not w:continue
            for sector in door_approaches(w,op,730):
                if room.covers(sector.centroid) and sector.intersection(shape).area>12000:return True
            if op.kind=='door':
                a=at_wall(w,op.offset_mm);b=at_wall(w,op.offset_mm+op.width_mm)
                ux=(b[0]-a[0])/op.width_mm;uy=(b[1]-a[1])/op.width_mm
                nx=-uy;ny=ux
                px,py=(b if op.hinge=='end' else a)
                if op.hinge=='end':ux=-ux;uy=-uy
                side=-1 if op.swing=='left' else 1
                st=math.atan2(uy,ux);en=math.atan2(ny*side,nx*side)
                delta=math.atan2(math.sin(en-st),math.cos(en-st))
                coords=[(px,py)]+[(px+op.width_mm*math.cos(st+delta*i/24),py+op.width_mm*math.sin(st+delta*i/24)) for i in range(25)]
                if Polygon(coords).intersection(shape).area>12000:return True
        return False
    def room_cands(room,obj):
        g=polygon(room.polygon,room.holes)
        allowed=[]
        pts=[(p.x,p.y) for p in room.polygon]
        for a,b in zip(pts,pts[1:]+pts[:1]):
            dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
            if length<obj.width_mm+450:continue
            ux,uy=dx/length,dy/length
            norm_a=(-uy,ux);norm_b=(uy,-ux)
            mid=((a[0]+b[0])/2,(a[1]+b[1])/2)
            normal=norm_a if g.covers(SPoint(mid[0]+norm_a[0]*300,mid[1]+norm_a[1]*300)) else norm_b
            theta=math.degrees(math.atan2(normal[1],normal[0]))-90
            for ratio in (.5,.30,.70,.4,.60,.2,.8):
                shift=length*ratio
                if shift <obj.width_mm/2+220 or length-shift<obj.width_mm/2+220:continue
                px=a[0]+ux*shift+normal[0]*(obj.depth_mm/2+135)
                py=a[1]+uy*shift+normal[1]*(obj.depth_mm/2+135)
                test=obj.model_copy(update={'center':P(px,py),'rotation_degrees':theta%360})
                # pydantic copy update bypasses assignment validation: normalize to [-360,360].
                if test.rotation_degrees>180:test.rotation_degrees-=360
                body=object_polygon(test)
                if not g.buffer(-125).covers(body):continue
                if any(body.intersection(object_polygon(o)).area>7000 for o in level.objects if o.kind not in ('floor_drain','light','socket','switch')):continue
                if blocked_by_doors(body,g):continue
                # Never propose a tall wardrobe/shelf across an actual aperture.
                obstructs_window=False
                for aperture in level.openings:
                    if aperture.kind not in ('window','vent'):continue
                    wall=walls.get(aperture.host_wall_id)
                    if not wall or aperture.offset_mm+aperture.width_mm>wall_length(wall):continue
                    if obj.height_mm<=aperture.sill_mm:continue
                    line=LineString([at_wall(wall,aperture.offset_mm),at_wall(wall,aperture.offset_mm+aperture.width_mm)])
                    if body.intersection(line.buffer(470)).area>max(12000,body.area*.05):
                        obstructs_window=True;break
                if obstructs_window:continue
                if obj.kind=='wardrobe':
                    zone=front_zone(test,700)
                    if zone.difference(g).area>zone.area*.08:continue
                    if any(zone.intersection(object_polygon(o)).area>28000 for o in level.objects if o.kind not in ('light','switch','socket')):continue
                    if blocked_by_doors(zone,g):continue
                    if any(object_polygon(test).intersection(front_zone(old,570)).area>18000
                           for old in level.objects if old.kind=='bed'):
                        continue  # wardrobes must not consume foot access to beds
                if obj.kind=='bed':
                    # preserve a free region in front of the bed for foot access
                    foot=front_zone(test,530)
                    if foot.difference(g).area>foot.area*.1:continue
                near_windows=0
                if obj.kind=='bed':
                    for op in level.openings:
                        if op.kind not in ('window','vent'):continue
                        w=walls.get(op.host_wall_id)
                        if not w:continue
                        glazing=LineString([at_wall(w,op.offset_mm),at_wall(w,op.offset_mm+op.width_mm)])
                        if back_edge(test).distance(glazing)<230:near_windows+=1
                priority= near_windows*100000 + rng.random()*180 + abs(ratio-.5)*260
                allowed.append((priority,test))
        return sorted(allowed,key=lambda x:x[0])
    results=[]
    for room in level.spaces:
        if room.kind!='bedroom':continue
        g=polygon(room.polygon,room.holes)
        rx,ry,rX,rY=g.bounds
        bedw=1540 if g.area<15e6 else 1740
        bed=PlacedObject(id=f'{room.id}_bed',name='Double Bed',kind='bed',
            center=P((rx+rX)/2,(ry+rY)/2),width_mm=bedw,depth_mm=1990,height_mm=550,
            placement='wall_anchored',space_id=room.id,attributes={'headboard_to_wall_target_mm':135})
        bed=sources.get((room.id,'bed'),bed)
        bed.space_id=room.id
        candidates=room_cands(room,bed)
        if candidates:
            bed=candidates[0][1];level.objects.append(bed);results.append(bed.id)
        else:results.append(f'NO_BED_FIT:{room.id}')
        wardrobe=PlacedObject(id=f'{room.id}_wardrobe',name='Wardrobe',kind='wardrobe',
            center=P((rx+rX)/2,(ry+rY)/2),width_mm=1450,depth_mm=560,height_mm=2400,
            placement='wall_anchored',space_id=room.id,front_clearance_mm=700)
        wardrobe=sources.get((room.id,'wardrobe'),wardrobe)
        wardrobe.space_id=room.id
        candidates=room_cands(room,wardrobe)
        if candidates:
            wardrobe=candidates[0][1];level.objects.append(wardrobe);results.append(wardrobe.id)
        else:results.append(f'NO_WARDROBE_FIT:{room.id}')
    return results


def generate_template(params: TemplateRequest) -> FloorPlan:
    rng=random.Random(params.seed)
    W=params.width_mm;H=params.depth_mm
    top=int(round(H*.425/50)*50);hallh=1450;band=top+hallh
    # Top row has n bedrooms; leave one study for 1-bed layouts.
    n=max(2,params.bedrooms)
    widths=[W/n]*n
    if n>2:
        shake=min(130, W/n*.045)
        widths=[W/n + rng.uniform(-shake,shake) for i in range(n)]
        scale=W/sum(widths);widths=[x*scale for x in widths]
    xx=[0]+[round(sum(widths[:i]),1) for i in range(1,n)]+[W]
    spaces=[]
    def space(id,name,kind,poly):
        spaces.append(Space(id=id,name=name,kind=kind,polygon=poly,is_habitable=kind not in ('shaft','stairwell','storage')))
    for i in range(n):
        space(f'bedroom_{i+1}' if i<params.bedrooms else 'study_1',
              f'BEDROOM {i+1}' if i<params.bedrooms else 'STUDY',
              'bedroom' if i<params.bedrooms else 'study',rectangle(xx[i],0,xx[i+1],top))
    space('hall','CENTRAL CORRIDOR','corridor',rectangle(0,top,W,band))
    # Bottom zone partitions scale with the envelope, not a frozen example.
    if params.include_core:
        x1=round(W*.385/50)*50;x2=round(W*.615/50)*50;x3=round(W*.735/50)*50
        ycore=round((band+(H-band)*.57)/50)*50
        space('living','LIVING / DINING','living',rectangle(0,band,x1,H))
        space('kitchen','KITCHEN','kitchen',rectangle(x1,band,x2,H))
        space('bath','BATHROOM','bathroom',rectangle(x2,band,x3,H))
        corex=x3+1100
        ycore=round((band+(H-band)*.595)/50)*50
        mid=W-850
        space('lift_lobby','CORE LOBBY','lift_lobby',rectangle(x3,band,corex,H))
        space('stairwell','STAIRWELL','stairwell',rectangle(corex,band,W,ycore))
        space('lift_shaft','LIFT SHAFT','shaft',rectangle(corex,ycore,mid,H))
        space('shaft_space','MEP SHAFT','shaft',rectangle(mid,ycore,W,H))
    else:
        x1=round(W*.47/50)*50;x2=round(W*.75/50)*50
        if params.irregular_living:
            cuty=round((band+(H-band)*.63)/50)*50
            cutx=round(x1*.69/50)*50
            # A genuine six-vertex L-shaped living room, not a fake rectangle.
            space('living','L-SHAPED LIVING','living',ring((0,band),(x1,band),(x1,cuty),(cutx,cuty),(cutx,H),(0,H)))
            space('store','STORE','storage',rectangle(cutx,cuty,x1,H))
        else:space('living','LIVING / DINING','living',rectangle(0,band,x1,H))
        space('kitchen','KITCHEN','kitchen',rectangle(x1,band,x2,H))
        bathbottom=round((band+(H-band)*.50)/50)*50
        space('bath','BATHROOM','bathroom',rectangle(x2,band,W,bathbottom))
        space('utility','UTILITY / LAUNDRY','utility',rectangle(x2,bathbottom,W,H))
    footprint=rectangle(0,0,W,H)
    segments=_lines_from_rooms(spaces,footprint)
    outline=polygon(footprint).boundary
    walls=[]
    for wi,(a,b) in enumerate(segments):
        seg=LineString([a,b]); mid=seg.interpolate(.5,normalized=True)
        exterior=outline.distance(mid)<1
        walls.append(Wall(id=f'W{wi+1:03d}',start=P(*a),end=P(*b),
                          thickness_mm=230 if exterior else 120,kind='exterior' if exterior else 'interior',
                          structural=exterior,height_mm=3000))
    # Build openings from true shared wall topology. Use an offset relative to HOST start.
    openings=[]
    def add_door(name,room_a,room_b,*,prefer_into=None,width=900,kind='door',near=None):
        wall=_shared_wall(walls,spaces,room_a,room_b)
        length=wall_length(wall)
        # Openings are moderately centered, leaving room for furniture on corners.
        offset=(length-width)/2 if length<width+600 else max(300,min((length-width)/2,length-width-300))
        if near is not None:
            ux=(wall.end.x-wall.start.x)/length;uy=(wall.end.y-wall.start.y)/length
            t=(near[0]-wall.start.x)*ux+(near[1]-wall.start.y)*uy
            offset=max(80,min(length-width-80,t-width/2))
        direction='right'
        if kind=='door':
            m=at_wall(wall,offset+width/2)
            dx=(wall.end.x-wall.start.x)/length;dy=(wall.end.y-wall.start.y)/length
            normal=(-dy,dx)
            into=polygon(next(r for r in spaces if r.id==(prefer_into or room_a)).polygon)
            direction='right' if into.covers(SPoint(m[0]+normal[0]*350,m[1]+normal[1]*350)) else 'left'
        op=Opening(id=name,host_wall_id=wall.id,kind=kind,offset_mm=offset,
            width_mm=width,height_mm=2100,hinge='start',swing=direction if kind=='door' else 'none')
        openings.append(op)
    for i in range(n):add_door(f'D_B{i+1}',f'bedroom_{i+1}' if i<params.bedrooms else 'study_1','hall',prefer_into=f'bedroom_{i+1}' if i<params.bedrooms else 'study_1')
    for id in ['living','kitchen','bath']:
        add_door(f'D_{id.upper()}',id,'hall',prefer_into=id,width=880 if id=='bath' else 950)
    if params.include_core:
        add_door('D_CORE','lift_lobby','hall',prefer_into='lift_lobby',width=900)
        add_door('D_STAIR','stairwell','lift_lobby',prefer_into='lift_lobby',width=920,near=(corex,band+590))
        add_door('D_LIFT','lift_shaft','lift_lobby',prefer_into='lift_lobby',width=900,kind='sliding_door')
    else:
        add_door('D_UTILITY','utility','kitchen',prefer_into='utility',width=850)
    if params.irregular_living and not params.include_core:
        add_door('D_STORE','store','living',prefer_into='store',width=850)
    # Entrance into living at a quiet part of an exterior side.
    ext=[w for w in _outer_wall(walls,spaces,'living') if wall_length(w)>2000]
    # Prefer south/bottom if available, otherwise west.
    entry_wall=max(ext,key=lambda w: (min(w.start.y,w.end.y)==H, wall_length(w)))
    L=wall_length(entry_wall);off=(L-1050)*.55
    pos=at_wall(entry_wall,off+525)
    ux=(entry_wall.end.x-entry_wall.start.x)/L;uy=(entry_wall.end.y-entry_wall.start.y)/L
    inward=polygon(next(r for r in spaces if r.id=='living').polygon)
    normal=(-uy,ux)
    entry_swing='right' if inward.covers(SPoint(pos[0]+normal[0]*350,pos[1]+normal[1]*350)) else 'left'
    openings.append(Opening(id='D_ENTRY',host_wall_id=entry_wall.id,kind='door',offset_mm=off,
                            width_mm=1050,height_mm=2200,hinge='start',swing=entry_swing))
    for ri,r in enumerate(spaces):
        if r.kind not in ('bedroom','living','kitchen','study'):continue
        candidates=_outer_wall(walls,spaces,r.id,omit_ids=[entry_wall.id])
        if not candidates:continue
        w=next((x for x in candidates if wall_length(x)>1800),None)
        if not w:continue
        width=min(1250,wall_length(w)-700)
        offset=max(350,(wall_length(w)-width)/2)
        label = f'WN_B{ri+1}' if r.kind=='bedroom' else f'WN_{r.kind[:2].upper()}_{ri+1}'
        openings.append(Opening(id=label,host_wall_id=w.id,kind='window',
                                offset_mm=offset,width_mm=width,height_mm=1300,sill_mm=900,
                                hinge='none',swing='none'))
    level=Level(id='L0',name='Ground Floor',elevation_mm=0,footprint=footprint,
                spaces=spaces,walls=walls,openings=openings,objects=[])
    # Furniture packs within rooms; all are separate 3D-sized semantic objects.
    add_furniture(level,seed=params.seed)
    # Add basic functioning schematic fixtures where unobstructed.
    def obj(id,name,kind,cx,cy,w,d,h,space_id,rotation=0):
        level.objects.append(PlacedObject(id=id,name=name,kind=kind,center=P(cx,cy),width_mm=w,
            depth_mm=d,height_mm=h,space_id=space_id,rotation_degrees=rotation))
    sr={s.id:polygon(s.polygon) for s in spaces}
    def bbox(id):return sr[id].bounds
    lx,ly,lX,lY=bbox('living')
    obj('living_sofa','Sofa','sofa',lx+900,ly+1450,1850,800,850,'living',rotation=-90)
    obj('dining_table','Dining Table','table',min(lX-1350,lx+1950),lY-1970,1350,850,750,'living')
    kx,ky,kX,kY=bbox('kitchen')
    obj('kitchen_counter','Kitchen Counter','counter',kx+420,ky+1200,580,1900,910,'kitchen')
    obj('kitchen_sink','Kitchen Sink','sink',kx+420,ky+950,410,450,230,'kitchen')
    obj('kitchen_hob','Hob','hob',kx+420,ky+1570,400,420,160,'kitchen')
    # Bathrooms are intentionally sparse in this concept generator; fixtures require
    # full user/architect clearances and may be rejected and revised by the validator.
    bx,by,bX,bY=bbox('bath')
    obj('bath_wc','WC','wc',bX-550,bY-750,510,680,750,'bath',rotation=180)
    obj('bath_basin','Wash Basin','sink',(bX-1260 if bX-bx>2500 else bx+340),bY-620,500,400,220,'bath')
    # Shower is modeled as a separate occupied area, not a vague bathroom icon.
    obj('bath_shower','Shower','shower',bx+600,by+(1450 if bX-bx>2500 else 1850),1000,1000,2100,'bath')
    if not params.include_core:
        ux,uy,uX,uY=bbox('utility')
        obj('utility_washer','Washing Machine','washing_machine',uX-650,uY-600,620,620,900,'utility')
    if params.include_core:
        sx,sy,sX,sY=bbox('stairwell')
        level.vertical_connectors.append(VerticalConnector(id='STAIR_01',name='Double-flight Stair',kind='stair',
            polygon=rectangle(sx+140,sy+110,sX-140,sY-140),serves_level_ids=[f'L{i}' for i in range(params.floors)],
            step_count=18,rise_mm=175,going_mm=250,
            landings=[rectangle(sx+200,sy+140,sX-200,sy+1050),rectangle(sx+200,sY-950,sX-200,sY-220)]))
        qx,qy,qX,qY=bbox('lift_shaft')
        level.vertical_connectors.append(VerticalConnector(id='LIFT_01',name='Passenger Lift',kind='lift',
            polygon=rectangle(qx+90,qy+100,qX-90,qY-100),serves_level_ids=[f'L{i}' for i in range(params.floors)],
            door_opening_id='D_LIFT', cabin_width_mm=max(900,(qX-qx)-300),cabin_depth_mm=max(900,(qY-qy)-320)))
        qx,qy,qX,qY=bbox('shaft_space')
        level.built_elements.append(BuiltElement(id='MEP_01',name='Vertical MEP Shaft',kind='shaft',
                    polygon=rectangle(qx+150,qy+150,qX-150,qY-150),height_mm=3000))
    # A column is an explicit polygon, never camouflaged as furniture.
    level.built_elements.append(BuiltElement(id='COL_01',name='250mm RC Column (intent only)',kind='column',
                        polygon=rectangle(240,band+240,490,band+490),height_mm=3000,load_bearing_assumed=True))
    levels=[level]
    for i in range(1,params.floors):
        duplicate=level.model_copy(deep=True)
        duplicate.id=f'L{i}';duplicate.name=f'Floor {i+1}';duplicate.elevation_mm=3150*i
        levels.append(duplicate)
    plan=FloorPlan(schema_version='1.1.0',unit='mm',origin='top_left',x_positive='right',y_positive='down',
        project=ProjectInfo(name=f'Parametric {params.bedrooms}-Bedroom Concept',
         description='Reproducible planning stress-test; schematic only, no building-code approval',revision='V3'),
        levels=levels,assumptions=['Example concept dimensions, not a surveyed site',
        'Stair, shaft, foundation and lift are schematic and need specialist verification'])
    add_optional_furnishing(plan)
    return plan


def suggest_bedroom_repair(original: FloorPlan, seed: int=17):
    """Reposition existing bedroom beds and wardrobes without mutating the input.

    Explicitly reports all relocations and incomplete/failed fits. Never claims that
    a lower error count means certified usability or that non-bedroom issues are fixed.
    """
    clone=original.model_copy(deep=True)
    changes=[]
    from .validate import validate_plan
    oldreport=validate_plan(original)
    for level in clone.levels:
        bedroom_ids={r.id for r in level.spaces if r.kind=='bedroom'}
        room_shapes={r.id:polygon(r.polygon,r.holes) for r in level.spaces if r.kind=='bedroom'}
        sources={}
        kept=[]
        for obj in level.objects:
            room_id=obj.space_id
            if not room_id:
                p=SPoint(obj.center.x,obj.center.y)
                room_id=next((rid for rid,shape in room_shapes.items() if shape.covers(p)),None)
            if room_id in bedroom_ids and obj.kind in ('bed','wardrobe') and (room_id,obj.kind) not in sources:
                sources[(room_id,obj.kind)]=obj
            else: kept.append(obj)
        level.objects=kept
        placed=add_furniture(level,seed=seed,sources=sources)
        for old_key,obj in sources.items():
            updated=next((o for o in level.objects if o.id==obj.id),None)
            if updated:
                if obj.center!=updated.center or obj.rotation_degrees!=updated.rotation_degrees:
                    changes.append({'level_id':level.id,'id':obj.id,'kind':obj.kind,
                      'from':obj.center.model_dump(),'to':updated.center.model_dump(),
                      'old_rotation':obj.rotation_degrees,'new_rotation':updated.rotation_degrees})
            else:
                # Important: don't lose source geometry if no workable placement exists.
                level.objects.append(obj)
                changes.append({'level_id':level.id,'id':obj.id,'status':'UNRESOLVED_NO_FIT'})
        for item in placed:
            if item.startswith('NO_'):
                changes.append({'level_id':level.id,'status':item})
    newreport=validate_plan(clone)
    accepted=(newreport.errors,newreport.warnings)<(oldreport.errors,oldreport.warnings)
    return {'accepted':accepted,'plan':clone if accepted else original,
            'original_report':oldreport,'report':newreport if accepted else oldreport,
            'proposed_report':newreport,'changes':changes}


def add_optional_furnishing(plan: FloorPlan) -> list[str]:
    """Try additional furniture only if the shared validator accepts each proposal.

    This is not a decorating algorithm for every building type; it illustrates
    a key quality guarantee: aesthetic enrichment cannot invalidate the geometry.
    """
    from .validate import validate_plan
    accepted=[]
    def propose(lv,obj):
        before=validate_plan(plan)
        lv.objects.append(obj)
        after=validate_plan(plan)
        if after.errors>before.errors or after.warnings>before.warnings:
            lv.objects.pop();return False
        accepted.append(obj.id);return True
    for lv in plan.levels:
        index={r.id:polygon(r.polygon,r.holes) for r in lv.spaces}
        if 'living' in index:
            x0,y0,x1,y1=index['living'].bounds
            table=next((o for o in lv.objects if o.id=='dining_table'),None)
            if table:
                for side in (-1,1):
                    propose(lv,PlacedObject(id=f'chair_dining_{"left" if side==-1 else "right"}',
                         name='Dining Chair',kind='chair',space_id='living',
                         center=P(table.center.x+side*(table.width_mm/2+355),table.center.y),
                         width_mm=500,depth_mm=500,height_mm=850))
            propose(lv,PlacedObject(id='living_tv_unit',name='TV Console',kind='cabinet',space_id='living',
                 placement='wall_anchored',center=P(x1-275,y0+1450),
                 width_mm=1230,depth_mm=340,height_mm=690,rotation_degrees=90))
        if 'kitchen' in index:
            x0,y0,x1,y1=index['kitchen'].bounds
            propose(lv,PlacedObject(id='kitchen_lower_cabinets',name='Lower Cabinets',kind='counter',
                space_id='kitchen',placement='built_in',center=P(x0+(x1-x0)*.59,y1-435),
                width_mm=min(1450,(x1-x0)*.47),depth_mm=550,height_mm=850))
    return accepted
