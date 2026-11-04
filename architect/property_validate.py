"""Cross-site, unit-ownership, access, and geometry checks above V3 floor validation."""
from __future__ import annotations
from collections import Counter
from shapely.geometry import Polygon,Point as SPoint,LineString
from shapely.affinity import translate
from shapely.ops import unary_union
from .property_models import PropertyProject,PropertyIssue,PropertyReport
from .validate import validate_plan,poly,at_wall,wall_length


def audit_property(project:PropertyProject) -> PropertyReport:
    issues=[];base={};metrics={'buildings':len(project.buildings),
                               'occupied_floors':0,'unit_floor_occurrences':0,'site_areas':len(project.site_areas)}
    def add(level,code,message,path=''):
        issues.append(PropertyIssue(severity=level,code=code,message=message,path=path))
    parcel=poly(project.site.boundary)
    if not parcel.is_valid or parcel.area<=0:
        add('error','INVALID_PARCEL','Plot boundary is self-intersecting or empty','site.boundary')
    seen_buildings=set();footprints=[];dwellings=set()
    for b in project.buildings:
        if b.id in seen_buildings:add('error','DUPLICATE_BUILDING_ID',f'{b.id} is duplicated','buildings')
        seen_buildings.add(b.id)
        r=validate_plan(b.plan)
        base[b.id]=r.model_dump(mode='json')
        for item in r.issues:
            if item.severity=='error':
                add('error','FLOOR_'+item.code,item.message,f'buildings.{b.id}.{item.path}')
            elif item.severity=='warning':
                add('warning','FLOOR_'+item.code,item.message,f'buildings.{b.id}.{item.path}')
        for lv in b.plan.levels:
            metrics['occupied_floors']+=1
            geom=translate(poly(lv.footprint,lv.footprint_holes),xoff=b.site_origin.x,yoff=b.site_origin.y)
            if geom.difference(parcel).area>5:
                add('error','BUILDING_OUTSIDE_PLOT',f'{b.name} / {lv.id} extends beyond plot','buildings')
            if lv==b.plan.levels[0]:footprints.append((b.id,geom))
            owned={};available={s.id:s for s in lv.spaces};openings={o.id:o for o in lv.openings}
            commons=b.common_space_ids.get(lv.id,[])
            for s in commons:
                if s not in available:add('error','UNKNOWN_COMMON_SPACE',f'{b.id}:{lv.id} references missing shared space {s}')
            if len(set(commons))!=len(commons):add('error','DUPLICATE_COMMON_SPACE',f'{b.id}:{lv.id} lists shared space twice')
            level_units=[u for u in b.units if u.level_id==lv.id]
            metrics['unit_floor_occurrences']+=len(level_units)
            for u in level_units:
                dwellings.add((b.id,u.dwelling_id or u.id))
                if not u.space_ids:add('error','EMPTY_UNIT',f'{u.name} has no rooms')
                for sid in u.space_ids:
                    if sid not in available:add('error','UNIT_ROOM_MISSING',f'{u.name} references nonexistent {sid}')
                    if sid in owned:add('error','ROOM_OWNED_TWICE',f'{sid} belongs to both {owned[sid]} and {u.id}')
                    if sid in commons:add('error','PRIVATE_COMMON_OVERLAP',f'{sid} simultaneously private and shared')
                    owned[sid]=u.id
                ent=openings.get(u.entrance_opening_id)
                if not ent:
                    add('error','UNIT_WITHOUT_ENTRY',f'{u.name} has no hosted entrance opening')
                elif ent.kind not in ('door','sliding_door','opening','arch'):
                    add('error','UNIT_ENTRY_NOT_PASSABLE',f'{u.name} entrance is not passable')
                else:
                    w=next((v for v in lv.walls if v.id==ent.host_wall_id),None)
                    if w:
                        at=at_wall(w,ent.offset_mm+ent.width_mm/2)
                        intersects_private=any(poly(available[s].polygon).boundary.distance(SPoint(at))<4 for s in u.space_ids if s in available)
                        common_adjacent=any(poly(available[s].polygon).boundary.distance(SPoint(at))<4 for s in commons if s in available)
                        outside=poly(lv.footprint).boundary.distance(SPoint(at))<4
                        if not intersects_private or not (common_adjacent or outside):
                            add('error','UNIT_ENTRY_NOT_CONNECTED',f'{u.name} entrance does not connect its private rooms to a shared hall or outside')
            extras=set(available)-set(owned)-set(commons)
            if extras and level_units:
                add('error','UNCLASSIFIED_LEVEL_SPACES',f'{b.id}:{lv.id} contains unowned/unshared spaces: {sorted(extras)[:8]}')
            # A building with multiple occupied floors must not rely on unmodeled vertical movement.
            if len(b.plan.levels)>1 and b.id!='garage_block':
                if not any(c.kind=='stair' and lv.id in c.serves_level_ids for c in lv.vertical_connectors):
                    add('error','NO_INTERLEVEL_STAIRS',f'{b.name}:{lv.id} has no stair serving this level')
            if len(level_units)>1 and not commons:
                add('error','MISSING_SHARED_CIRCULATION',f'{b.name}:{lv.id} has multiple homes and no modeled shared circulation')
    for i,(a,geom_a) in enumerate(footprints):
        for b,geom_b in footprints[i+1:]:
            if geom_a.intersection(geom_b).area>10:
                add('error','OVERLAPPING_BUILDINGS',f'{a} and {b} occupy the same plot area')
    features={f.name:f for f in project.feature_decisions}
    for name in ('garage','lawn','stairs','lift','shaft'):
        if name not in features:add('error','MISSING_FEATURE_DECISION',f'Missing explicit {name} inclusion/exclusion decision')
    kinds={a.kind for a in project.site_areas}
    actual={'garage':any(b.id=='garage_block' for b in project.buildings),
       'lawn':'lawn' in kinds,
       'stairs':any(c.kind=='stair' for b in project.buildings for lv in b.plan.levels for c in lv.vertical_connectors),
       'lift':any(c.kind=='lift' for b in project.buildings for lv in b.plan.levels for c in lv.vertical_connectors),
       'shaft':any(v.kind=='shaft' for b in project.buildings for lv in b.plan.levels for v in lv.built_elements)}
    for name,exists in actual.items():
        decision=features.get(name)
        if decision and decision.included!=exists:
            add('error','FEATURE_MODEL_MISMATCH',f'{name} feature decision included={decision.included} contradicts actual geometry exists={exists}')
        if decision and decision.requested=='forbidden' and exists:
            add('error','FORBIDDEN_FEATURE_PRESENT',f'{name} was forbidden but appears in modeled project')
        if decision and decision.requested=='required' and not exists:
            add('error','REQUIRED_FEATURE_MISSING',f'{name} was required but is missing')
    if features.get('lawn') and features['lawn'].included and 'lawn' not in kinds:
        add('error','LAWN_REQUEST_UNFULFILLED','Lawn was required but no usable garden polygon exists')
    if features.get('garage') and features['garage'].included and not any(b.id=='garage_block' for b in project.buildings):
        add('error','GARAGE_REQUEST_UNFULFILLED','Garage required but no enclosed garage building is modeled')
    if features.get('lift') and features['lift'].included and not any(c.kind=='lift' for b in project.buildings for lv in b.plan.levels for c in lv.vertical_connectors):
        add('error','LIFT_REQUEST_UNFULFILLED','Lift required but no served vertical lift exists')
    if features.get('shaft') and features['shaft'].included and not any(s.kind=='shaft' for b in project.buildings for lv in b.plan.levels for s in lv.built_elements):
        add('error','SHAFT_REQUEST_UNFULFILLED','Shaft required but not modeled')
    siteids=[]
    for a in project.site_areas:
        siteids.append(a.id);g=poly(a.polygon)
        if not g.is_valid or g.area<1:add('error','BAD_SITE_AREA',f'{a.id} is not a valid polygon');continue
        if g.difference(parcel).area>1:add('error','SITE_AREA_OUT_OF_BOUNDS',f'{a.id} leaves the plot')
        if a.kind in ('lawn','parking_bay','driveway','walkway'):
            if any(g.intersection(b).area>500 for _,b in footprints):
                add('error','SITE_AREA_OVER_BUILDING',f'{a.id} intersects a building footprint')
        if a.kind=='lawn' and any(g.intersection(poly(b.polygon)).area>500 for b in project.site_areas if b.id!=a.id and b.kind in ('driveway','parking_bay')):
            add('error','LAWN_VEHICLE_OVERLAP','Landscape incorrectly overlaps vehicle access')
    if len(set(siteids))!=len(siteids):add('error','DUPLICATE_SITE_AREA_ID','Site areas contain duplicate IDs')
    if project.request.parking_spaces>0 and not features.get('garage',None):
        add('warning','PARKING_DECISION','Parking count requested but no explicit garage decision exists')
    if project.request.parking_spaces>0 and not (any(a.kind=='parking_bay' for a in project.site_areas) or any(b.id=='garage_block' for b in project.buildings)):
        add('error','PARKING_MISSING','Required parking spaces not modeled')
    if features.get('garage') and features['garage'].included and not any(a.kind=='driveway' for a in project.site_areas):
        add('error','GARAGE_INACCESSIBLE','Garage has no vehicular route to the road')
    if any(a.kind in ('driveway','parking_bay') for a in project.site_areas):
        add('warning','VEHICLE_TRACK_UNVERIFIED','Vehicle swept paths, turning radii and road approval have not been checked')
    if any(c.kind=='lift' for b in project.buildings for lv in b.plan.levels for c in lv.vertical_connectors):
        add('warning','LIFT_ENGINEERING_UNVERIFIED','Lift machinery, clearances and accessibility are conceptual only')
    metrics['independent_units']=len(dwellings)
    metrics['gross_plot_area_m2']=round(parcel.area/1e6,1)
    metrics['building_coverage_percent']=round(sum(g.area for _,g in footprints)/parcel.area*100,1) if parcel.area else 0
    metrics['site_landscape_area_m2']=round(sum(poly(a.polygon).area for a in project.site_areas if a.kind=='lawn')/1e6,1)
    metrics['warnings_requiring_review']=sum(i.severity=='warning' for i in issues)
    return PropertyReport(valid=not any(i.severity=='error' for i in issues),
       errors=sum(i.severity=='error' for i in issues),warnings=sum(i.severity=='warning' for i in issues),
       issues=issues,base_reports=base,metrics=metrics)
