"""Architectural drafting renderer: SVG is a deterministic view of canonical geometry.

Units: all model coordinates and SVG user units are millimetres. This module doesn't
invent plan geometry: symbols come from typed objects, openings from their host walls,
and dimensions from coordinates. It deliberately does NOT certify building-code fitness.
"""
from __future__ import annotations
from collections import defaultdict
from xml.etree import ElementTree as ET
from shapely.geometry import Polygon, LineString, box as shapely_box
from shapely.ops import unary_union
import math
from .models import FloorPlan
from .validate import poly, wall_length, at_wall, object_polygon

NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)
def n(parent,tag,attrs=None,text=None):
    v=ET.SubElement(parent,f'{{{NS}}}{tag}',{str(k):str(v) for k,v in (attrs or {}).items()})
    if text is not None:v.text=str(text)
    return v
def f(x):return f'{float(x):.2f}'.rstrip('0').rstrip('.') if isinstance(x,(float,int)) else str(x)
def L(parent,x1,y1,x2,y2,cls='detail',extra=None):
    attrs={'x1':f(x1),'y1':f(y1),'x2':f(x2),'y2':f(y2),'class':cls}
    if extra:attrs.update(extra)
    return n(parent,'line',attrs)
def R(parent,x,y,w,h,cls='detail',extra=None,rx=None):
    attrs={'x':f(x),'y':f(y),'width':f(w),'height':f(h),'class':cls}
    if rx:attrs['rx']=f(rx)
    if extra:attrs.update(extra)
    return n(parent,'rect',attrs)
def C(parent,x,y,r,cls='detail',extra=None):
    a={'cx':f(x),'cy':f(y),'r':f(r),'class':cls}
    if extra:a.update(extra)
    return n(parent,'circle',a)
def ellipse(parent,x,y,rx,ry,cls='detail'):
    return n(parent,'ellipse',{'cx':f(x),'cy':f(y),'rx':f(rx),'ry':f(ry),'class':cls})
def T(parent,x,y,text,cls='small',extra=None):
    a={'x':f(x),'y':f(y),'class':cls}
    if extra:a.update(extra)
    return n(parent,'text',a,text)
def P(parent,path,cls='detail',extra=None):
    a={'d':path,'class':cls}
    if extra:a.update(extra)
    return n(parent,'path',a)
def polygon(parent,shape,cls='detail',extra=None):
    if shape.interiors:
        rings=[shape.exterior]+list(shape.interiors)
        d=' '.join('M '+' L '.join(f'{f(x)} {f(y)}' for x,y in ring.coords)+' Z' for ring in rings)
        return P(parent,d,cls,{'fill-rule':'evenodd',**(extra or {})})
    coords=' '.join(f'{f(x)},{f(y)}' for x,y in list(shape.exterior.coords)[:-1])
    a={'points':coords,'class':cls}
    if extra:a.update(extra)
    return n(parent,'polygon',a)

def symbol(g,o):
    """Deterministic symbol library with real-world width/depth, oriented via group transform."""
    w,d=o.width_mm,o.depth_mm
    a,b=-w/2,-d/2
    kind=o.kind
    base={'data-object-id':o.id,'data-kind':kind,'aria-label':o.name}
    group=n(g,'g',{'transform':f'translate({f(o.center.x)} {f(o.center.y)}) rotate({f(o.rotation_degrees)})',**base})
    # Coordinates local to the object, not arbitrary display pixels.
    if kind=='bed':
        R(group,a,b,w,d,'furniture-heavy',rx=45)
        R(group,a+55,b+90,w-110,d-150,'furniture-light',rx=22)
        R(group,a+90,b+125,w-180,max(350,d*.28),'furniture-light',rx=28)
        half=(w-240)/2
        for x in [a+110,a+120+half]:
            R(group,x,b+150,half-25,max(260,d*.20),'furniture-medium',rx=40)
        L(group,a+95,b+d*.52,a+w-95,b+d*.52,'furniture-medium')
        L(group,a+95,b+d*.60,a+w-95,b+d*.60,'furniture-light')
    elif kind=='sofa':
        R(group,a,b,w,d,'furniture-heavy',rx=45)
        R(group,a+80,b+80,w-160,d-145,'furniture-light',rx=34)
        R(group,a+10,b+10,125,d-20,'furniture-medium',rx=28)
        R(group,a+w-135,b+10,125,d-20,'furniture-medium',rx=28)
        seats=max(1,round(w/560))
        for j in range(1,seats):L(group,a+110+(w-220)*j/seats,b+110,a+110+(w-220)*j/seats,b+d-95,'furniture-light')
        L(group,a+130,b+155,a+w-130,b+155,'furniture-light')
    elif kind in ('table','desk'):
        R(group,a,b,w,d,'furniture-heavy',rx=20)
        R(group,a+50,b+50,w-100,d-100,'furniture-light',rx=12)
        if kind=='desk':
            R(group,a+80,b+90,min(w*.45,550),min(d*.43,260),'furniture-light')
            C(group,a+w*.20,b+d*.78,22,'furniture-medium')
    elif kind=='chair':
        R(group,a,b,w,d,'furniture-medium',rx=45)
        R(group,a+65,b+100,w-130,d-160,'furniture-light',rx=15)
        L(group,a+55,b+75,a+w-55,b+75,'furniture-heavy')
    elif kind in ('wardrobe','cabinet'):
        R(group,a,b,w,d,'furniture-heavy')
        R(group,a+35,b+35,w-70,d-70,'furniture-light')
        count=max(1,round(max(w,d)/540))
        if w>=d:
            for i in range(1,count):L(group,a+w*i/count,b+35,a+w*i/count,b+d-35,'furniture-medium')
            for i in range(count):C(group,a+w*(i+.5)/count,b+d*.58,18,'furniture-medium')
        else:
            for i in range(1,count):L(group,a+35,b+d*i/count,a+w-35,b+d*i/count,'furniture-medium')
            for i in range(count):C(group,a+w*.58,b+d*(i+.5)/count,18,'furniture-medium')
    elif kind=='counter':
        R(group,a,b,w,d,'furniture-medium')
        R(group,a+45,b+45,w-90,d-90,'furniture-light')
        if w>=d:
            for i in range(1,max(2,int(w/650))):L(group,a+w*i/max(2,int(w/650)),b+d-90,a+w*i/max(2,int(w/650)),b+d-45,'furniture-light')
        else:
            for i in range(1,max(2,int(d/650))):L(group,a+w-90,b+d*i/max(2,int(d/650)),a+w-45,b+d*i/max(2,int(d/650)),'furniture-light')
    elif kind=='hob':
        R(group,a,b,w,d,'furniture-medium')
        for x in [a+w*.28,a+w*.72]:
            for y in [b+d*.28,b+d*.72]:
                C(group,x,y,min(w,d)*.12,'furniture-medium')
                C(group,x,y,min(w,d)*.07,'furniture-light')
    elif kind=='sink':
        R(group,a,b,w,d,'plumbing',rx=36)
        dual=w>740
        if dual:
            for x in [a+w*.27,a+w*.73]:ellipse(group,x,b+d*.53,w*.17,d*.34,'plumbing')
        else:ellipse(group,0,b+d*.54,w*.32,d*.29,'plumbing')
        C(group,0,b+d*.12,20,'plumbing')
        L(group,0,b+d*.12,0,b+d*.31,'plumbing')
    elif kind=='wc':
        R(group,a+60,b+15,w-120,min(155,d*.23),'sanitary',rx=16)
        ellipse(group,0,b+d*.18,w*.33,d*.30,'sanitary')
        ellipse(group,0,b+d*.18,w*.22,d*.21,'sanitary-light')
        C(group,0,b-d*.03,18,'sanitary')
    elif kind=='bathtub':
        R(group,a,b,w,d,'sanitary',rx=115)
        R(group,a+85,b+85,w-170,d-170,'sanitary-light',rx=155)
        C(group,0,b+d*.35,32,'sanitary')
    elif kind=='shower':
        R(group,a,b,w,d,'sanitary-light')
        L(group,a+70,b+70,a+w-70,b+d-70,'sanitary-light')
        L(group,a+w-70,b+70,a+70,b+d-70,'sanitary-light')
        C(group,0,0,40,'sanitary')
        C(group,a+w*.28,b+d*.28,55,'sanitary')
    elif kind=='floor_drain':
        R(group,a,b,w,d,'sanitary')
        L(group,a,b,a+w,b+d,'sanitary')
        L(group,a+w,b,a,b+d,'sanitary')
    elif kind=='fridge':
        R(group,a,b,w,d,'furniture-heavy')
        R(group,a+45,b+45,w-90,d-90,'furniture-light')
        L(group,a+50,b+d*.40,a+w-50,b+d*.40,'furniture-medium')
        L(group,a+w-120,b+d*.1,a+w-120,b+d*.3,'furniture-medium')
    elif kind=='washing_machine':
        R(group,a,b,w,d,'furniture-heavy',rx=10)
        C(group,0,0,min(w,d)*.36,'furniture-medium')
        C(group,0,0,min(w,d)*.25,'furniture-light')
        L(group,a+45,b+95,a+w-45,b+95,'furniture-medium')
        for x in (a+90,a+170):C(group,x,b+52,13,'furniture-light')
    elif kind=='column':
        R(group,a,b,w,d,'column')
        L(group,a,b,a+w,b+d,'column-cross')
        L(group,a+w,b,a,b+d,'column-cross')
    elif kind=='stair':
        R(group,a,b,w,d,'furniture-medium')
        count=max(3,min(28,round(d/260)))
        for i in range(1,count):L(group,a,b+i*d/count,a+w,b+i*d/count,'furniture-light')
        P(group,f'M 0 {f(b+d-180)} V {f(b+180)} l -90 140 m 90 -140 l 90 140','symbol-arrow')
        T(group,130,0,'UP','obj-small')
    elif kind in ('light','electrical','socket','switch'):
        C(group,0,0,min(w,d)*.33,'electrical')
        L(group,-w*.2,-d*.2,w*.2,d*.2,'electrical')
        L(group,-w*.2,d*.2,w*.2,-d*.2,'electrical')
        if kind=='socket':T(group,0,-d*.35,'SO','obj-small')
    else:
        R(group,a,b,w,d,'furniture-medium',rx=15)
        R(group,a+35,b+35,w-70,d-70,'furniture-light')
    return group

def wall_cuts(w, openings):
    total=wall_length(w)
    if total<1:return []
    intervals=sorted((max(0,o.offset_mm),min(total,o.offset_mm+o.width_mm)) for o in openings)
    sections=[];cursor=0
    for start,end in intervals:
        if start>cursor+.01:sections.append((cursor,start))
        cursor=max(cursor,end)
    if cursor<total:sections.append((cursor,total))
    return [(LineString([at_wall(w,start),at_wall(w,end)]).buffer(w.thickness_mm/2,cap_style=2,join_style=2))
            for start,end in sections if end-start>.1]

def dim_horizontal(g,xx,yy,label=None,y_dim=None):
    x1,x2=xx; y1,y2=yy
    if x2<=x1+1:return
    y=y_dim if y_dim is not None else max(y1,y2)+450
    gap=55 if y>max(y1,y2) else -55
    L(g,x1,y1,x1,y+gap,'dim-ext');L(g,x2,y2,x2,y+gap,'dim-ext')
    L(g,x1,y,x2,y,'dim')
    for x in (x1,x2):L(g,x-65,y+65,x+65,y-65,'dim')
    T(g,(x1+x2)/2,y-88,label or f'{round(x2-x1):,}'.replace(',',' '),'dim-label')

def dim_vertical(g,ys,xx,label=None,x_dim=None):
    y1,y2=ys;x1,x2=xx
    if y2<=y1+1:return
    x=x_dim if x_dim is not None else min(x1,x2)-450
    gap=-55 if x<min(x1,x2) else 55
    L(g,x1,y1,x+gap,y1,'dim-ext');L(g,x2,y2,x+gap,y2,'dim-ext')
    L(g,x,y1,x,y2,'dim')
    for y in (y1,y2):L(g,x-65,y+65,x+65,y-65,'dim')
    ty=(y1+y2)/2
    T(g,x-88,ty,label or f'{round(y2-y1):,}'.replace(',',' '),'dim-label',{'transform':f'rotate(-90 {f(x-88)} {f(ty)})'})

def dimension_manual(g,d):
    x1,y1=d.start.x,d.start.y;x2,y2=d.end.x,d.end.y
    if abs(y1-y2)<.01:
        dim_horizontal(g,(min(x1,x2),max(x1,x2)),(y1,y2),d.text_override,y1+d.offset_mm)
    elif abs(x1-x2)<.01:
        dim_vertical(g,(min(y1,y2),max(y1,y2)),(x1,x2),d.text_override,x1+d.offset_mm)
    else:
        dx=x2-x1;dy=y2-y1;le=math.hypot(dx,dy)
        ux,uy=dx/le,dy/le; nx,ny=-uy,ux;off=d.offset_mm
        a=(x1+nx*off,y1+ny*off);b=(x2+nx*off,y2+ny*off)
        L(g,x1,y1,a[0]+nx*80,a[1]+ny*80,'dim-ext')
        L(g,x2,y2,b[0]+nx*80,b[1]+ny*80,'dim-ext')
        L(g,*a,*b,'dim')
        for x,y in (a,b):L(g,x-60*(nx+ux),y-60*(ny+uy),x+60*(nx+ux),y+60*(ny+uy),'dim')
        T(g,(a[0]+b[0])/2+nx*90,(a[1]+b[1])/2+ny*90,d.text_override or f'{le:.0f}','dim-label')

def label_room(g,room,objs,openings):
    if room.kind in ('shaft','stairwell'):return  # specialized core has its own drafting labels
    p=poly(room.polygon,room.holes)
    area=p.area/1e6
    minx,miny,maxx,maxy=p.bounds
    lw=min(2300,max(1000,len(room.name)*130))
    sh=420
    object_shapes=[object_polygon(o).buffer(95) for o in objs]
    best=None;bestval=-1e50
    for yi in range(1,11):
        for xi in range(1,11):
            x=minx+(maxx-minx)*xi/11;y=miny+(maxy-miny)*yi/11
            box=shapely_box(x-lw/2,y-sh*.45,x+lw/2,y+sh*.55)
            if not p.buffer(-60).covers(box):continue
            intrusion=sum(box.intersection(q).area for q in object_shapes)
            dist=box.distance(p.boundary)
            # keep slightly toward room's upper-center; gaps are more important
            val=dist*.16 - intrusion/1150 - math.hypot(x-(minx+maxx)/2,y-(miny+maxy)/2)*.07
            if val>bestval:best=(x,y);bestval=val
    if best is None:
        q=p.representative_point();best=(q.x,q.y)
    x,y=best
    lg=n(g,'g',{'data-room-id':room.id})
    # Two lines with no white boxes: dimension/text remain separately editable SVG primitives.
    T(lg,x,y-52,room.name.upper(),'room-name')
    T(lg,x,y+135,f'{area:.2f} m²','room-area')

def render_svg(plan: FloorPlan, level_id: str | None=None) -> str:
    level=next((lv for lv in plan.levels if lv.id==level_id),None) if level_id else plan.levels[0]
    if level is None:raise ValueError(f'Unknown level: {level_id}')
    shape=poly(level.footprint,level.footprint_holes)
    if not shape.is_valid or shape.area<10000:raise ValueError('Cannot render invalid footprint')
    x0,y0,x1,y1=shape.bounds
    w=x1-x0;h=y1-y0
    left=1400;right=1650;top=1350;bottom=2670
    vw=w+left+right;vh=h+top+bottom
    root=ET.Element(f'{{{NS}}}svg',{'width':'1700','height':f(1700*vh/vw),
        'viewBox':f'{f(x0-left)} {f(y0-top)} {f(vw)} {f(vh)}',
        'role':'img','aria-label':f'Architectural drawing: {plan.project.name} / {level.name}'})
    n(root,'title',text=f'Architectural concept — {plan.project.name}, {level.name}')
    defs=n(root,'defs')
    css='''
    text{font-family:Arial,Helvetica,sans-serif} .sheet{fill:#fff}
    .roomfill{fill:#fff;stroke:none}.wetfill{fill:#fafcff;stroke:none}.utilityfill{fill:#f8fbfc;stroke:none}
    .wall-hatch{fill:url(#masonry);stroke:#12191b;stroke-width:20;stroke-linejoin:round}
    .wall-light{fill:url(#partitions);stroke:#1f272c;stroke-width:18;stroke-linejoin:round}
    .wall-hit{fill:none;stroke:transparent;stroke-width:180;pointer-events:stroke}
    .column{fill:#f38b9a;stroke:#151c21;stroke-width:18}.column-cross{stroke:#85152f;stroke-width:15}
    .detail{fill:none;stroke:#079eca;stroke-width:18}
    .furniture-heavy{fill:#fff;stroke:#02a2cf;stroke-width:23;stroke-linejoin:round}
    .furniture-medium{fill:#fff;stroke:#05a2ce;stroke-width:17}
    .furniture-light{fill:none;stroke:#54b7d3;stroke-width:12}
    .sanitary{fill:#fff;stroke:#a536b4;stroke-width:22}
    .sanitary-light{fill:none;stroke:#a75abd;stroke-width:14}
    .plumbing{fill:#fff;stroke:#05a2ce;stroke-width:18}
    .electrical{fill:none;stroke:#3674a2;stroke-width:14}
    .door-leaf{fill:none;stroke:#ed7041;stroke-width:30;stroke-linecap:round}
    .door-swing{fill:none;stroke:#e97543;stroke-width:18}
    .door-jamb{fill:none;stroke:#d85b2d;stroke-width:24}
    .window-frame{stroke:#e9652f;stroke-width:30;fill:none}
    .window-glass{stroke:#08a8cb;stroke-width:12;fill:none}
    .symbol-tag{font-size:112px;fill:#18558e;text-anchor:middle;font-weight:700}
    .room-name{font-size:160px;fill:#273846;text-anchor:middle;font-weight:700;letter-spacing:12px}
    .room-area{font-size:136px;fill:#52748a;text-anchor:middle}
    .obj-small{font-size:100px;fill:#24799c;text-anchor:middle}
    .dim{stroke:#1269bc;stroke-width:15;fill:none}
    .dim-ext{stroke:#3485cb;stroke-width:10;fill:none}
    .dim-label{font-size:156px;fill:#0c68b4;text-anchor:middle;font-weight:700}
    .sheet-line{fill:none;stroke:#8297a2;stroke-width:12}
    .inner-frame{fill:none;stroke:#c0cbd1;stroke-width:8;stroke-dasharray:110 75}
    .title-strong{font-size:290px;fill:#152a38;font-weight:700}
    .title-med{font-size:162px;fill:#26435a;font-weight:700}
    .title-small{font-size:118px;fill:#486172}
    .note{font-size:132px;fill:#364c5e}
    .symbol-arrow{fill:none;stroke:#067fac;stroke-width:20}
    .core-column{fill:#fa8d9b;stroke:#681f32;stroke-width:20}
    .core-cross{stroke:#681f32;stroke-width:14}
    .core-shaft{fill:#f1f0f5;stroke:#8465a5;stroke-width:21;stroke-dasharray:70 40}
    .core-void{fill:#fff;stroke:#6f8f98;stroke-width:22;stroke-dasharray:95 50}
    .core-outline{fill:none;stroke:#434e5c;stroke-width:24}
    .core-flight{fill:#fbfbfb;stroke:#52626f;stroke-width:16}
    .core-tread{stroke:#4d6370;stroke-width:12}
    .core-arrow{fill:none;stroke:#1481a5;stroke-width:23}
    .core-landing{fill:#eff1f3;fill-opacity:.65;stroke:#566a77;stroke-width:14}
    .core-lift{fill:#f4f5f5;stroke:#354c5f;stroke-width:26}
    .core-lift-diag{stroke:#91a1ac;stroke-width:12}
    .core-label{font-size:156px;fill:#29415a;text-anchor:middle;font-weight:700}
    .core-sub{font-size:104px;fill:#687d8c;text-anchor:middle}
    '''
    n(defs,'style',text=css)
    pattern=n(defs,'pattern',{'id':'masonry','patternUnits':'userSpaceOnUse','width':'128','height':'128'})
    R(pattern,0,0,128,128,'',{'fill':'#fff','stroke':'none'})
    P(pattern,'M 0 0 L 128 128 M 128 0 L 0 128','',{'fill':'none','stroke':'#67757a','stroke-width':'12'})
    pattern2=n(defs,'pattern',{'id':'partitions','patternUnits':'userSpaceOnUse','width':'135','height':'135',
                           'patternTransform':'rotate(45)'})
    R(pattern2,0,0,135,135,'',{'fill':'#fff','stroke':'none'})
    L(pattern2,0,0,0,135,'',{'stroke':'#a6b1b2','stroke-width':'13'})
    R(root,x0-left,y0-top,vw,vh,'sheet')
    # Light drawing frame (not a plot/setback boundary).
    R(root,x0-left+100,y0-top+110,vw-200,vh-220,'inner-frame')
    rooms=n(root,'g',{'id':'layer-spaces'})
    for s in level.spaces:
        g=poly(s.polygon,s.holes)
        if g.is_valid:
            clazz='wetfill' if s.kind in ('bathroom','toilet') else ('utilityfill' if s.kind in ('utility','storage') else 'roomfill')
            polygon(rooms,g,clazz,{'data-room-id':s.id})
    wall_group=n(root,'g',{'id':'layer-walls'})
    holes=defaultdict(list)
    for o in level.openings:holes[o.host_wall_id].append(o)
    bytype=defaultdict(list)
    for wa in level.walls:
        for piece in wall_cuts(wa,holes[wa.id]):
            if not piece.is_empty:
                bytype['heavy' if wa.kind in ('exterior','existing') else 'light'].append(piece)
    # Merge common same-kind segments at junctions to avoid disjoint overlapping hatches.
    for type_ in ('light','heavy'):
        geoms=bytype[type_]
        if not geoms:continue
        merged=unary_union(geoms)
        polys=[merged] if merged.geom_type=='Polygon' else list(getattr(merged,'geoms',[]))
        for pg in polys:
            if pg.geom_type=='Polygon':
                # Full path retains holes; polygon element would fill a hole.
                rings=[pg.exterior]+list(pg.interiors)
                d=' '.join('M '+' L '.join(f'{f(x)} {f(y)}' for x,y in ring.coords)+' Z' for ring in rings)
                P(wall_group,d,'wall-hatch' if type_=='heavy' else 'wall-light',{'fill-rule':'evenodd'})
    # Transparent centerline hit geometry allows selection of authoritative wall IDs
    # without changing the displayed wall hatch polygons.
    for wa in level.walls:
        L(wall_group,wa.start.x,wa.start.y,wa.end.x,wa.end.y,'wall-hit',{'data-wall-id':wa.id})
    # Structural columns / shafts / stairs / lifts are independent semantic entities.
    from .cores_render import render_cores
    render_cores(root,level,defs)
    # Openings are drawn on top of their exact removed wall intervals.
    glaz=n(root,'g',{'id':'layer-openings'})
    walls={wa.id:wa for wa in level.walls}
    for op in level.openings:
        wa=walls.get(op.host_wall_id)
        if wa is None or op.offset_mm+op.width_mm>wall_length(wa):continue
        og=n(glaz,'g',{'data-opening-id':op.id,'data-kind':op.kind})
        n(og,'title',text=f'{op.kind}: {op.id}, {f(op.width_mm)} x {f(op.height_mm)} mm, sill {f(op.sill_mm)} mm')
        a=at_wall(wa,op.offset_mm);b=at_wall(wa,op.offset_mm+op.width_mm)
        dx=(b[0]-a[0])/op.width_mm;dy=(b[1]-a[1])/op.width_mm
        nx,ny=-dy,dx
        cx=(a[0]+b[0])/2;cy=(a[1]+b[1])/2
        if op.kind in ('window','vent'):
            for shift in (-wa.thickness_mm*.32,wa.thickness_mm*.32):
                L(og,a[0]+nx*shift,a[1]+ny*shift,b[0]+nx*shift,b[1]+ny*shift,'window-frame')
            L(og,*a,*b,'window-glass')
            for x,y in (a,b):
                L(og,x-nx*wa.thickness_mm*.48,y-ny*wa.thickness_mm*.48,
                  x+nx*wa.thickness_mm*.48,y+ny*wa.thickness_mm*.48,'window-frame')
            if op.width_mm>=950:
                T(og,cx+nx*235,cy+ny*235,op.id.upper()[:12],'symbol-tag')
        elif op.kind in ('door','sliding_door'):
            if op.kind=='sliding_door':
                L(og,a[0]-nx*80,a[1]-ny*80,b[0]-nx*80,b[1]-ny*80,'door-leaf')
                L(og,a[0]+nx*80,a[1]+ny*80,b[0]+nx*80,b[1]+ny*80,'door-leaf')
                L(og,a[0]-nx*150,a[1]-ny*150,a[0]+nx*150,a[1]+ny*150,'door-jamb')
                L(og,b[0]-nx*150,b[1]-ny*150,b[0]+nx*150,b[1]+ny*150,'door-jamb')
            else:
                if op.hinge=='end':
                    px,py=b; ux,uy=-dx,-dy
                else:
                    px,py=a;ux,uy=dx,dy
                side=-1 if op.swing=='left' else 1
                ex,ey=px+nx*side*op.width_mm,py+ny*side*op.width_mm
                sx,sy=px+ux*op.width_mm,py+uy*op.width_mm
                L(og,px,py,ex,ey,'door-leaf')
                cross=ux*(ny*side)-uy*(nx*side)
                sweep=1 if cross>0 else 0
                P(og,f'M {f(sx)} {f(sy)} A {f(op.width_mm)} {f(op.width_mm)} 0 0 {sweep} {f(ex)} {f(ey)}','door-swing')
                C(og,px,py,33,'door-jamb')
                L(og,px-nx*75,py-ny*75,px+nx*75,py+ny*75,'door-jamb')
            if op.width_mm>1000:T(og,cx+nx*135,cy+ny*135,op.id.upper()[:12],'symbol-tag')
        elif op.kind in ('arch','opening'):
            L(og,*a,*b,'window-glass',{'stroke-dasharray':'65 35'})
    # Objects intentionally sit in front of floor hatch, behind labels and dimensions.
    furnishings=n(root,'g',{'id':'layer-objects'})
    for o in level.objects:symbol(furnishings,o)
    labels=n(root,'g',{'id':'layer-labels'})
    for room in level.spaces:label_room(labels,room,level.objects,level.openings)
    # Dimensions: split chains + overall, all computed, never guessed.
    dims=n(root,'g',{'id':'layer-dimensions'})
    bx=sorted({x0,x1,*[wa.start.x for wa in level.walls if abs(wa.start.x-wa.end.x)<.1 and wall_length(wa)>2000]})
    bx=[v for i,v in enumerate(bx) if i==0 or v-bx[i-1]>=650] # avoid unreadable slivers
    if bx[-1]!=x1:bx.append(x1)
    for aa,bb in zip(bx,bx[1:]):dim_horizontal(dims,(aa,bb),(y1,y1),y_dim=y1+400)
    dim_horizontal(dims,(x0,x1),(y1,y1),y_dim=y1+930)
    by=sorted({y0,y1,*[wa.start.y for wa in level.walls if abs(wa.start.y-wa.end.y)<.1 and wall_length(wa)>1800]})
    by=[v for i,v in enumerate(by) if i==0 or v-by[i-1]>=650]
    if by[-1]!=y1:by.append(y1)
    for aa,bb in zip(by,by[1:]):dim_vertical(dims,(aa,bb),(x0,x0),x_dim=x0-450)
    dim_vertical(dims,(y0,y1),(x0,x0),x_dim=x0-1010)
    dim_vertical(dims,(y0,y1),(x1,x1),x_dim=x1+680)
    # Upper wall divisions: ensure not over-dimensioning empty exterior notch.
    if x1-x0>4800:
        tx=sorted({x0,x1,*[wa.start.x for wa in level.walls if abs(wa.start.x-wa.end.x)<.1 and wall_length(wa)>2200]})
        for aa,bb in zip(tx,tx[1:]):
            if bb-aa>=750:dim_horizontal(dims,(aa,bb),(y0,y0),y_dim=y0-435)
    for d in level.dimensions:dimension_manual(dims,d)
    # Supplied annotations, no fabricated fixture specification.
    notes=n(root,'g',{'id':'layer-annotations'})
    for a in level.annotations:
        T(notes,a.at.x,a.at.y,a.text,'note',{'transform':f'rotate({f(a.rotation_degrees)} {f(a.at.x)} {f(a.at.y)})'})
    ng=n(root,'g',{'id':'layer-north',
      'transform':f'translate({f(x1+1040)} {f(y0+600)}) rotate({f(plan.project.north_degrees_clockwise_from_page_up)})'})
    P(ng,'M 0 -290 L -100 50 L 0 -15 L 100 50 Z','',{'fill':'#166ca4','stroke':'#166ca4','stroke-width':'10'})
    L(ng,0,0,0,280,'dim')
    T(ng,0,-380,'N','title-med',{'text-anchor':'middle'})
    # Scale bar (real unit reference; SVG may be printed at arbitrary scale).
    scale=n(root,'g',{'id':'layer-scalebar'})
    startx=x0+180; starty=y1+1420
    for i in range(4):
        R(scale,startx+i*500,starty,500,95,'',{'fill':'#193d53' if i%2==0 else '#fff','stroke':'#193d53','stroke-width':'10'})
    for i in range(5):T(scale,startx+i*500,starty-75,str(i*.5).rstrip('0').rstrip('.'),'title-small',{'text-anchor':'middle'})
    T(scale,startx+2200,starty+85,'m','title-small')
    # Drafting sheet title block
    block=n(root,'g',{'id':'layer-titleblock'})
    ty=y1+1715
    L(block,x0-350,ty-70,x1+1000,ty-70,'sheet-line')
    L(block,x1-370,ty-70,x1-370,ty+630,'sheet-line')
    T(block,x0-200,ty+235,plan.project.name.upper(),'title-strong')
    T(block,x0-200,ty+495,f'{level.name.upper()}  |  ARCHITECTURAL FLOOR PLAN','title-med')
    T(block,x1+920,ty+200,'A-101  |  DRAWING NO.','title-med',{'text-anchor':'end'})
    T(block,x1+920,ty+400,f'REVISION {plan.project.revision}   /   UNITS: mm','title-small',{'text-anchor':'end'})
    T(block,x1+920,ty+570,'CONCEPT — NOT FOR CONSTRUCTION','title-small',{'text-anchor':'end'})
    # Separate concise discipline / output note along frame footer.
    T(block,x0-160,y1+2490,'AI-ASSISTED SCHEMATIC DRAFT  /  STRUCTURED GEOMETRY  /  PROFESSIONAL REVIEW REQUIRED','title-small')
    return ET.tostring(root,encoding='unicode',xml_declaration=False)
