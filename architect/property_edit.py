"""Bounded, validation-first furniture placement for V4 interactive workspace.

This is a candidate search, not an architectural furnishing optimizer.  It never
returns a changed project until the full property validation accepts it.
"""
from __future__ import annotations
from copy import deepcopy
from itertools import product
from math import isfinite
from shapely.geometry import Polygon, box
from shapely.affinity import rotate
from .property_models import PropertyProject
from .property_validate import audit_property


def suggest_furniture_placement(project: PropertyProject, building_id: str,
                                level_id: str, space_id: str, kind: str,
                                width_mm: float, depth_mm: float, height_mm: float,
                                name: str | None = None):
    if kind not in {'bed','sofa','table','desk','chair','counter','cabinet','wardrobe','fridge','furniture'}:
        raise ValueError('Auto-placement supports common furniture only; use manual placement for other objects')
    if not all(isfinite(n) and 80 <= n <= 6000 for n in (width_mm, depth_mm, height_mm)):
        raise ValueError('Furniture dimensions must be between 80 and 6000 mm')
    building=next((b for b in project.buildings if b.id==building_id), None)
    if not building:raise ValueError('Unknown building')
    level=next((l for l in building.plan.levels if l.id==level_id), None)
    if not level:raise ValueError('Unknown level')
    space=next((s for s in level.spaces if s.id==space_id), None)
    if not space:raise ValueError('Unknown room')
    room=Polygon([(p.x,p.y) for p in space.polygon],
                 holes=[[(p.x,p.y) for p in h] for h in space.holes])
    if not room.is_valid or room.area<=0:raise ValueError('Room polygon is invalid')
    if len(level.objects)>=600:raise ValueError('Object limit reached for this floor')
    existing=[]
    for ob in level.objects:
        q=rotate(box(-ob.width_mm/2,-ob.depth_mm/2,ob.width_mm/2,ob.depth_mm/2),ob.rotation_degrees,origin=(0,0),use_radians=False)
        from shapely.affinity import translate
        existing.append(translate(q,xoff=ob.center.x,yoff=ob.center.y).buffer(90))
    minx,miny,maxx,maxy=room.bounds
    positions=[]
    # Symmetric sample-grid, including points near the edges for anchored furniture.
    for ax,ay in product(range(1,10),range(1,10)):
        positions.append((minx+(maxx-minx)*ax/10,miny+(maxy-miny)*ay/10))
    positions.sort(key=lambda pt:(pt[0]-(minx+maxx)/2)**2+(pt[1]-(miny+maxy)/2)**2)
    rotations=[0,90,180,270]
    placement='wall_anchored' if kind in {'bed','wardrobe','cabinet','counter'} else 'freestanding'
    uid=f'USR_{kind.upper()}_{len(level.objects)+1:03d}'
    ids={o.id for o in level.objects}
    while uid in ids:uid=f'{uid}_X'
    tested=0
    best=None
    for rotation in rotations:
        shape=rotate(box(-width_mm/2,-depth_mm/2,width_mm/2,depth_mm/2),rotation,origin=(0,0),use_radians=False)
        for x,y in positions:
            from shapely.affinity import translate
            footprint=translate(shape,xoff=x,yoff=y)
            if not room.buffer(-65).contains(footprint):continue
            if any(footprint.intersects(ob) for ob in existing):continue
            tested+=1
            if tested>90:break
            prop=deepcopy(project)
            target=next(b for b in prop.buildings if b.id==building_id)
            lev=next(l for l in target.plan.levels if l.id==level_id)
            from .models import PlacedObject,Point
            lev.objects.append(PlacedObject(
                id=uid,name=name or kind.replace('_',' ').title(),kind=kind,
                center=Point(x=round(x),y=round(y)),width_mm=width_mm,depth_mm=depth_mm,
                height_mm=height_mm,rotation_degrees=rotation,space_id=space_id,
                placement=placement))
            report=audit_property(prop)
            if report.valid:
                if best is None or report.warnings<best[1].warnings:
                    best=(prop,report)
                # Good feasible candidate. Don't over-search once warnings are clean.
                if report.warnings==0:break
        if best and best[1].warnings==0:break
    if best:
        return {'accepted':True,'project':best[0].model_dump(mode='json'),
                'report':best[1].model_dump(mode='json'),'new_id':uid,
                'tested':tested,'note':'Geometrically validated candidate. Furniture usability still needs review.'}
    return {'accepted':False,'project':None,'new_id':None,'tested':tested,
            'reason':'No modeled-valid placement found within the limited search. Try smaller furniture, another room, or manual coordinates.'}
