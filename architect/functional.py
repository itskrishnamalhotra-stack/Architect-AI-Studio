"""General-purpose geometry/placement/circulation audits for architectural concepts.

All measurements are millimetres. Distances here are editable *heuristic* design
preferences, NOT building code, accessibility certification or structural approval.
An error prevents declaring a candidate ready; geometry is never silently moved.
"""
from __future__ import annotations
import math
from collections import defaultdict
from shapely.geometry import Polygon, LineString, Point as SPoint
from shapely.ops import unary_union
from shapely.errors import GEOSException
from .models import FloorPlan, DesignConstraints, Issue
from .validate import at_wall, wall_length, object_polygon

PASSABLE={"door","sliding_door","arch","opening"}
PHYSICAL={"bed","sofa","table","desk","chair","counter","cabinet","wardrobe","sink","wc","shower","bathtub","hob","fridge","washing_machine","appliance","furniture","fixture"}
STORAGE={"wardrobe","cabinet"}
NO_BODY={"light","switch","socket","electrical","doorbell","floor_drain","plumbing"}

def polygon(points, holes=()):
    return Polygon([(p.x,p.y) for p in points], [[(p.x,p.y) for p in ring] for ring in holes])

def _local(o, x, y):
    a=math.radians(o.rotation_degrees); c=math.cos(a); s=math.sin(a)
    return (o.center.x+x*c-y*s,o.center.y+x*s+y*c)

def back_edge(o):
    return LineString([_local(o,-o.width_mm/2,-o.depth_mm/2),_local(o,o.width_mm/2,-o.depth_mm/2)])

def bed_side_zone(o,side, clearance=530):
    """Access rectangle along one side, excluding headboard zone."""
    x0=-o.width_mm/2-clearance if side<0 else o.width_mm/2+40
    x1=-o.width_mm/2-40 if side<0 else o.width_mm/2+clearance
    y0=-o.depth_mm*.17; y1=o.depth_mm*.48
    return Polygon([_local(o,x0,y0),_local(o,x1,y0),_local(o,x1,y1),_local(o,x0,y1)])

def front_zone(o,depth):
    w=o.width_mm/2
    return Polygon([_local(o,-w,o.depth_mm/2+40), _local(o,w,o.depth_mm/2+40),
                    _local(o,w,o.depth_mm/2+depth),_local(o,-w,o.depth_mm/2+depth)])

def door_approaches(w, op, distance_mm=690):
    """Two unobstructed rectangles immediately inside either side of a passable wall opening."""
    if wall_length(w)<op.offset_mm+op.width_mm:return []
    a=at_wall(w,op.offset_mm+60);b=at_wall(w,op.offset_mm+op.width_mm-60)
    if op.width_mm<=120:a=at_wall(w,op.offset_mm);b=at_wall(w,op.offset_mm+op.width_mm)
    length=wall_length(w);nx=-(w.end.y-w.start.y)/length;ny=(w.end.x-w.start.x)/length
    regs=[]
    for sign in (-1,1):
        near=w.thickness_mm/2+40
        far=w.thickness_mm/2+distance_mm
        regs.append(Polygon([(a[0]+sign*nx*near,a[1]+sign*ny*near),
            (b[0]+sign*nx*near,b[1]+sign*ny*near),
            (b[0]+sign*nx*far,b[1]+sign*ny*far),
            (a[0]+sign*nx*far,a[1]+sign*ny*far)]))
    return regs

def _room_for_object(obj, rooms):
    # Full footprint containment is checked separately; a centre alone is not enough.
    if obj.space_id:return rooms.get(obj.space_id)
    c=SPoint(obj.center.x,obj.center.y)
    fits=[(r,s) for r,s in rooms.values() if s.covers(c)]
    return fits[0] if len(fits)==1 else None

def _components(g):
    if g.is_empty:return []
    if g.geom_type=='Polygon':return [g]
    return [p for p in getattr(g,'geoms',[]) if p.geom_type=='Polygon' and p.area>80000]

def _point_in_components(p,components):
    return {i for i,comp in enumerate(components) if comp.buffer(15).covers(p)}

def audit_functional(plan: FloorPlan, config: DesignConstraints | None=None) -> list[Issue]:
    config=config or DesignConstraints(require_exterior_entrance=False)
    findings=[]
    def add(severity,code,message,path):
        findings.append(Issue(severity=severity,code=code,message=message,path=path))
    all_level_ids={lv.id for lv in plan.levels}
    for li,level in enumerate(plan.levels):
        prefix=f'levels[{li}]'
        try: footprint=polygon(level.footprint,level.footprint_holes)
        except (ValueError,GEOSException):
            add('error','INVALID_FOOTPRINT_HOLES','Footprint holes cannot be constructed',prefix+'.footprint_holes');continue
        if not footprint.is_valid or footprint.area<=0:
            add('error','INVALID_FOOTPRINT_HOLES','Footprint/holes have invalid topology',prefix+'.footprint_holes');continue
        rooms={}
        for i,r in enumerate(level.spaces):
            path=f'{prefix}.spaces[{i}]'
            try: shp=polygon(r.polygon,r.holes)
            except (ValueError,GEOSException):
                add('error','INVALID_ROOM_HOLES',f'{r.name} holes invalid',path);continue
            if not shp.is_valid or shp.area<=0:
                add('error','INVALID_ROOM_HOLES',f'{r.name} hole or boundary self-intersects',path);continue
            if shp.difference(footprint.buffer(.1)).area>100:
                add('error','ROOM_CROSSES_FOOTPRINT_HOLE',f'{r.name} occupies a site void or footprint hole',path)
            rooms[r.id]=(r,shp)
        for i,a in enumerate(level.spaces):
            if a.id not in rooms:continue
            for b in level.spaces[i+1:]:
                if b.id in rooms and rooms[a.id][1].intersection(rooms[b.id][1]).area>4000:
                    add('error','ROOM_HOLE_OVERLAP',f'{a.name} and {b.name} have overlapping floor space',prefix)
        ids=[x.id for x in level.built_elements]+[x.id for x in level.vertical_connectors]
        ids += [x.id for seq in (level.spaces,level.walls,level.openings,level.objects,level.annotations,level.dimensions) for x in seq]
        if len(ids)!=len(set(ids)):
            add('error','DUPLICATE_V3_ID','A built element / connector has an ID already in use',prefix)
        obstacles=[]
        for i,b in enumerate(level.built_elements):
            path=f'{prefix}.built_elements[{i}]'
            g=polygon(b.polygon)
            if not g.is_valid or g.area<100:
                add('error','BAD_BUILT_GEOMETRY',f'{b.id} has an invalid polygon',path);continue
            if g.difference(footprint.buffer(1)).area>100:
                add('error','BUILT_OUTSIDE_ENVELOPE',f'{b.id} lies outside the usable footprint',path)
            if b.kind in ('column','pier'):
                if min(g.minimum_rotated_rectangle.bounds[2]-g.bounds[0],g.bounds[3]-g.bounds[1])<80:
                    add('warning','SLENDER_STRUCTURE',f'{b.id} seems exceptionally thin; check modeled geometry',path)
            obstacles.append((b.id,b.kind,g))
        for i,c in enumerate(level.vertical_connectors):
            path=f'{prefix}.vertical_connectors[{i}]'
            g=polygon(c.polygon)
            if not g.is_valid or g.area<100:
                add('error','BAD_CORE_GEOMETRY',f'{c.id} has invalid core geometry',path);continue
            if g.difference(footprint.buffer(1)).area>100:
                add('error','CORE_OUTSIDE_ENVELOPE',f'{c.id} lies outside the usable floor polygon',path)
            for id in c.serves_level_ids:
                if id not in all_level_ids:add('error','UNKNOWN_CONNECTED_LEVEL',f'{c.id} references missing level {id}',path)
            if c.door_opening_id is not None and c.door_opening_id not in {o.id for o in level.openings}:
                add('error','LIFT_DOOR_NOT_HOSTED',f'{c.id} references nonexistent opening {c.door_opening_id}',path)
            if c.kind=='stair':
                if not (c.step_count and c.rise_mm and c.going_mm):
                    add('warning','STAIR_FLIGHT_UNSPECIFIED',f'{c.id} is missing step count/riser/going; no stair feasibility can be inferred',path)
                if len(c.serves_level_ids)>=2 and c.step_count and c.rise_mm:
                    heights=sorted(plan.levels[[v.id for v in plan.levels].index(s)].elevation_mm for s in c.serves_level_ids if s in all_level_ids)
                    if len(heights)>=2 and abs((heights[1]-heights[0])-c.step_count*c.rise_mm)>150:
                        add('error','STAIR_ELEVATION_MISMATCH',f'{c.id}: steps × rise does not reach the connected floor elevation',path)
                for landing in c.landings:
                    land=polygon(landing)
                    if not land.is_valid or land.difference(g.buffer(1)).area>100:
                        add('error','STAIR_LANDING_OUTSIDE',f'{c.id} contains an invalid/outside landing',path)
            if c.kind=='stair' and c.landings:
                # Entry must open to a landing, not directly into a run of treads.
                stair_solid=g.difference(unary_union([polygon(ring) for ring in c.landings]))
                wall_idx_local={w.id:w for w in level.walls}
                for op in level.openings:
                    if op.kind not in PASSABLE or op.host_wall_id not in wall_idx_local:continue
                    for approach in door_approaches(wall_idx_local[op.host_wall_id],op):
                        if approach.intersection(g).area<6000:continue
                        if approach.intersection(stair_solid).area>65000:
                            add('error','STAIR_DOOR_ON_TREADS',f'{op.id} opens into the stair run {c.id} instead of a modeled landing',path)
            if c.kind=='lift':
                if c.cabin_width_mm is None or c.cabin_depth_mm is None:
                    add('warning','LIFT_CABIN_UNSPECIFIED',f'{c.id} is missing cabin dimensions',path)
                elif c.cabin_width_mm*c.cabin_depth_mm > g.area*1.1:
                    add('error','LIFT_CABIN_TOO_LARGE',f'{c.id} cabin is larger than enclosing footprint',path)
            obstacles.append((c.id,c.kind,g))
        wall_idx={w.id:w for w in level.walls}
        obj_geoms={obj.id:object_polygon(obj) for obj in level.objects}
        room_objs=defaultdict(list)
        for oi,obj in enumerate(level.objects):
            path=f'{prefix}.objects[{oi}]'
            if obj.kind in NO_BODY:continue
            p=obj_geoms[obj.id]
            r=_room_for_object(obj,rooms)
            if obj.space_id and obj.space_id not in rooms:
                add('error','UNKNOWN_OBJECT_SPACE',f'{obj.id} references unknown room {obj.space_id}',path)
            if r is None:
                add('error','UNASSIGNED_OBJECT',f'{obj.id} is not clearly inside a named room; assign space_id',path);continue
            room,roomshape=r
            room_objs[room.id].append(obj)
            # Allow half wall thickness at room perimeter for fitted cabinetry; not arbitrary crossing.
            protrusion=p.difference(roomshape.buffer(125)).area
            if protrusion>max(7000,p.area*.018):
                add('error','OBJECT_OUTSIDE_ROOM',f'{obj.id} extends {protrusion/1e6:.2f} m² beyond {room.name}',path)
            for bid,kind,solid in obstacles:
                if p.intersection(solid).area>8000 and kind not in ('stair','lift','ramp','escalator'):
                    add('error','OBJECT_HITS_BUILT_ELEMENT',f'{obj.id} overlaps {kind} {bid}',path)
            # A tall object blocks real glazing/ventilation if it occupies the
            # zone directly inside the opening at the window's vertical elevation.
            for win in level.openings:
                if win.kind not in ('window','vent'):continue
                ww=next((w for w in level.walls if w.id==win.host_wall_id),None)
                if ww is None or win.offset_mm+win.width_mm>wall_length(ww):continue
                if obj.base_z_mm+obj.height_mm<=win.sill_mm+20 or obj.base_z_mm>=win.sill_mm+win.height_mm-20:continue
                aperture=LineString([at_wall(ww,win.offset_mm),at_wall(ww,win.offset_mm+win.width_mm)])
                if p.intersection(aperture.buffer(450)).area>max(20000,p.area*.08):
                    add('error','FURNITURE_BLOCKS_WINDOW',f'{obj.id} blocks window {win.id} at its sill/glazing height',path)
            if obj.kind=='bed' and config.quality_profile=='residential' and config.require_bed_headwall:
                edge=back_edge(obj)
                in_near=edge.intersection(roomshape.boundary.buffer(260)).length
                dist=edge.distance(roomshape.boundary)
                if dist>260 or in_near<obj.width_mm*.6:
                    add('error','BED_NO_HEADWALL',f'{obj.id} has no properly aligned headboard at a wall (distance {dist:.0f} mm)',path)
                else:
                    # Do not set beds against a doorway or window at floor height.
                    for opening in level.openings:
                        if opening.kind not in PASSABLE or opening.host_wall_id not in wall_idx:continue
                        wall=wall_idx[opening.host_wall_id]
                        if opening.offset_mm+opening.width_mm>wall_length(wall):continue
                        gateway=LineString([at_wall(wall,opening.offset_mm),at_wall(wall,opening.offset_mm+opening.width_mm)])
                        if edge.distance(gateway)<230 and edge.intersection(gateway.buffer(230)).length>obj.width_mm*.25:
                            add('error','BED_BLOCKS_OPENING',f'{obj.id} is anchored across door {opening.id}',path)
            if obj.kind=='wardrobe' and config.quality_profile=='residential':
                edge=back_edge(obj)
                aligned=edge.intersection(roomshape.boundary.buffer(320)).length
                if edge.distance(roomshape.boundary)>320 or aligned<obj.width_mm*.55:
                    add('warning','WARDROBE_NOT_WALL_ANCHORED',f'{obj.id} should normally be fitted against a room wall',path)
        if config.enforce_furniture_clearances and config.quality_profile=='residential':
            for roomid,objs in room_objs.items():
                room,roomshape=rooms[roomid]
                for bed in (o for o in objs if o.kind=='bed'):
                    bedshape=obj_geoms[bed.id]
                    front=front_zone(bed,570)
                    blockers=[obj_geoms[o.id] for o in objs if o.id!=bed.id and o.kind not in NO_BODY]
                    column_polys=[g for _,kind,g in obstacles if kind in ('column','pier','shaft','duct','void','lightwell')]
                    if front.difference(roomshape).area>front.area*.12 or any(front.intersection(b).area>42000 for b in blockers+column_polys):
                        add('error','BED_FOOT_ACCESS_BLOCKED',f'{bed.id}: front/foot access cannot be used',prefix)
                    free_sides=0
                    for side in (-1,1):
                        zone=bed_side_zone(bed,side)
                        inside=zone.difference(roomshape).area<=zone.area*.12
                        clear=not any(zone.intersection(b).area>42000 for b in blockers+column_polys)
                        if inside and clear:free_sides+=1
                    if free_sides==0:
                        add('error','BED_NO_SIDE_ACCESS',f'{bed.id}: neither side has sufficient ordinary access space',prefix)
                    elif free_sides==1 and bed.width_mm>=1400:
                        add('warning','BED_SINGLE_SIDE_ACCESS',f'{bed.id}: only one side of a double bed is readily usable',prefix)

        # Strict doorway approach zones: a cabinet behind a door must be rejected even
        # if the door swings outward or is sliding and has no sector.
        access_points=defaultdict(list)
        for op in level.openings:
            if op.kind not in PASSABLE:continue
            wall=wall_idx.get(op.host_wall_id)
            if not wall or op.offset_mm+op.width_mm>wall_length(wall):continue
            for approach in door_approaches(wall,op):
                centre=approach.centroid
                host_rooms=[(rid,rp) for rid,(room,rp) in rooms.items() if rp.buffer(10).covers(centre)]
                if len(host_rooms)!=1:continue
                rid,rp=host_rooms[0]
                # Test door approach at least partially in the room. This can overlap
                # a corridor junction (valid) but it cannot overlap fixed objects.
                access_points[rid].append((op.id,centre))
                for obj in room_objs[rid]:
                    if obj.kind not in PHYSICAL:continue
                    overlap=approach.intersection(obj_geoms[obj.id]).area
                    if overlap>35000:
                        add('error','DOOR_APPROACH_BLOCKED',
                            f'{obj.id} obstructs the approach to {op.id} by {overlap/1e6:.2f} m²',
                            f'{prefix}.openings.{op.id}')
                for bid,kind,shape in obstacles:
                    if kind in ('column','pier','shaft','duct','void','lightwell') and approach.intersection(shape).area>35000:
                        add('error','DOOR_APPROACH_HITS_CORE',f'{op.id} approach intersects {kind} {bid}',prefix)
        # Furniture access zones have to be spatially available, not just non-overlapping outlines.
        if config.enforce_furniture_clearances and config.quality_profile!='unfurnished':
            for rid,objs in room_objs.items():
                room,roomshape=rooms[rid]
                for obj in objs:
                    depth=(obj.front_clearance_mm if obj.front_clearance_mm is not None else {
                        'wardrobe':700,'cabinet':600,'desk':650,'fridge':650,'wc':500}.get(obj.kind,0))
                    if obj.kind=='cabinet' and max(obj.width_mm,obj.depth_mm)<700: depth=0
                    if depth<=0:continue
                    zone=front_zone(obj,depth)
                    meaningful=zone.area
                    outside=zone.difference(roomshape).area
                    if outside>meaningful*.12:
                        add('error','FURNITURE_ACCESS_OUTSIDE_ROOM',f'{obj.id} has no room for {depth:.0f} mm of front access',prefix)
                    for other in objs:
                        if obj.id==other.id or other.kind in NO_BODY:continue
                        if obj.kind=='desk' and other.kind=='chair':continue  # a desk chair is intended to occupy desk access space
                        # Built-in counter assemblies explicitly share surface footprint.
                        if other.kind in ('sink','hob','floor_drain') and obj.kind=='counter':continue
                        overlap=zone.intersection(obj_geoms[other.id]).area
                        if overlap>max(35000,zone.area*.08):
                            add('error','FURNITURE_ACCESS_BLOCKED',
                                f'{other.id} blocks working/access space in front of {obj.id}',prefix)
                            break
                    for bid,kind,solid in obstacles:
                        if zone.intersection(solid).area>45000:
                            add('error','FURNITURE_ACCESS_HITS_CORE',f'{obj.id} front access intersects {kind} {bid}',prefix)
                            break
        # For each usable room, compute whether multiple door portals are in a single
        # walkable region with the requested nominal width, after physical obstacles.
        # This is an advisory geometric test, NOT an evacuation/accessibility analysis.
        width=config.min_practical_clear_path_mm
        for rid,doors in access_points.items():
            if len(doors)<2 or rid not in rooms:continue
            room,roomshape=rooms[rid]
            if room.kind in ('shaft','stairwell','lift_lobby'):continue
            blockers=[obj_geoms[o.id] for o in room_objs[rid] if o.kind in PHYSICAL and o.kind not in ('counter',)]
            blockers += [g for _,kind,g in obstacles if kind in ('column','pier','shaft','duct','lightwell','void') and roomshape.intersects(g)]
            try:
                walk=roomshape.buffer(-width/2)
                if blockers:walk=walk.difference(unary_union([g.buffer(width/2) for g in blockers]))
                comps=_components(walk)
                choices=[]
                for doorid,at in doors:
                    # Valid free-space portals may be 300 mm deeper than the approach centroid.
                    nearby=SPoint(at.x,at.y)
                    possible=_point_in_components(nearby,comps)
                    if not possible:
                        possible={i for i,c in enumerate(comps) if c.distance(nearby)<width*.70}
                    choices.append((doorid,possible))
                if choices and any(not ids for _,ids in choices):
                    add('warning','NARROW_PORTAL_REGION',f'{room.name}: nominal {width:.0f} mm clear-width circulation is questionable',prefix)
                elif choices and not set.intersection(*(opts for _,opts in choices)):
                    add('error','ROOM_CIRCULATION_BLOCKED',f'{room.name}: doors are disconnected by physical obstacles',prefix)
            except GEOSException:
                add('error','WALKABILITY_GEOMETRY_FAILED',f'Could not compute walkable zone of {room.name}',prefix)
    return findings
