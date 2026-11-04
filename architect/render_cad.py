"""2D DXF drafting from the same canonical plan model used by the SVG renderer.

Unlike converting SVG paths into CAD, this keeps numeric millimetre geometry and
entity layers in model space. This remains a concept CAD export, not a BIM file.
"""
from __future__ import annotations
from io import StringIO
from collections import defaultdict
import math
import ezdxf
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import Polygon
from .models import FloorPlan
from .validate import poly, at_wall, wall_length
from .render_pro import wall_cuts


def render_dxf(plan: FloorPlan, level_id: str | None=None) -> bytes:
    lv=next((l for l in plan.levels if l.id==level_id),None) if level_id else plan.levels[0]
    if lv is None:raise ValueError(f'Unknown level: {level_id}')
    doc=ezdxf.new('R2013')
    doc.header['$INSUNITS']=4
    doc.header['$MEASUREMENT']=1
    for name,color in [('A-ROOM',9),('A-WALL-EXT',7),('A-WALL-INT',8),('A-WALL-HATCH',9),
         ('A-DOOR',30),('A-WINDOW',10),('A-FURN',4),('A-SAN',6),('A-ELEC',5),
         ('A-STRUCT',1),('A-CORE',3),('A-SHAFT',6),('A-DIMS',5),('A-TEXT',7),('A-SHEET',8)]:
        doc.layers.add(name,color=color)
    m=doc.modelspace()
    def pt(x,y):return (float(x),-float(y))
    def li(a,b,layer):m.add_line(pt(*a),pt(*b),dxfattribs={'layer':layer})
    def rect(x,y,w,h,layer):
        polyline([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],layer)
    def polyline(pts,layer,closed=True):
        m.add_lwpolyline([pt(*p) for p in pts],close=closed,dxfattribs={'layer':layer})
    def cir(x,y,r,layer):m.add_circle(pt(x,y),float(r),dxfattribs={'layer':layer})
    def txt(x,y,s,layer='A-TEXT',h=140,align=TextEntityAlignment.MIDDLE_CENTER):
        t=m.add_text(str(s),dxfattribs={'layer':layer,'height':h})
        t.set_placement(pt(x,y),align=align)
    def oval(x,y,rx,ry,layer):
        m.add_ellipse(pt(x,y),major_axis=(float(rx),0),ratio=float(ry)/max(float(rx),.001),
                      dxfattribs={'layer':layer})
    # Local object rotation, then Y flip into CAD world model space.
    def transform(o,u,v):
        angle=math.radians(o.rotation_degrees)
        return (o.center.x+u*math.cos(angle)-v*math.sin(angle),
                o.center.y+u*math.sin(angle)+v*math.cos(angle))
    def local_line(o,u,v,x,y,layer):li(transform(o,u,v),transform(o,x,y),layer)
    def local_rect(o,x,y,w,d,layer):
        polyline([transform(o,*p) for p in ((x,y),(x+w,y),(x+w,y+d),(x,y+d))],layer)
    def local_circle(o,x,y,r,layer):cir(*transform(o,x,y),r,layer)

    wallhosts=defaultdict(list)
    for op in lv.openings:wallhosts[op.host_wall_id].append(op)
    for w in lv.walls:
        layer='A-WALL-EXT' if w.kind in ('exterior','existing') else 'A-WALL-INT'
        for solid in wall_cuts(w,wallhosts[w.id]):
            coords=list(solid.exterior.coords)[:-1]
            polyline(coords,layer)
            # User-space ANSI pattern on bounded fill, visible in CAD with hatch enabled.
            try:
                hatch=m.add_hatch(color=8,dxfattribs={'layer':'A-WALL-HATCH'})
                hatch.set_pattern_fill('ANSI31',scale=2 if w.kind in ('exterior','existing') else 3)
                hatch.paths.add_polyline_path([pt(*xy) for xy in coords],is_closed=True)
            except (ValueError,TypeError):
                # CAD outline remains intact if an unsupported hatch API is encountered.
                pass
    # Structural and circulation cores are modeled in native CAD layers, not flattened SVG.
    for el in lv.built_elements:
        coords=[(p.x,p.y) for p in el.polygon]
        layer='A-STRUCT' if el.kind in ('column','pier') else 'A-SHAFT'
        polyline(coords,layer)
        shape=Polygon(coords)
        cp=shape.representative_point()
        if el.kind in ('column','pier'):
            x0,y0,x1,y1=shape.bounds
            li((x0,y0),(x1,y1),layer);li((x1,y0),(x0,y1),layer)
        else:txt(cp.x,cp.y,el.kind.upper(),layer,95)
    for core in lv.vertical_connectors:
        coords=[(p.x,p.y) for p in core.polygon]
        polyline(coords,'A-CORE')
        shape=Polygon(coords)
        x0,y0,x1,y1=shape.bounds
        if core.kind=='stair':
            steps=max(3,min(14,(core.step_count or 18)//2))
            for k in range(1,steps):
                y=y0+(y1-y0)*k/steps
                li((x0+130,y),(x0+(x1-x0)*.44,y),'A-CORE')
                li((x0+(x1-x0)*.56,y),(x1-130,y),'A-CORE')
            txt((x0+x1)/2,(y0+y1)/2,'UP','A-CORE',135)
        elif core.kind=='lift':
            li((x0+150,y0+150),(x1-150,y1-150),'A-CORE')
            li((x1-150,y0+150),(x0+150,y1-150),'A-CORE')
            txt((x0+x1)/2,(y0+y1)/2,'LIFT','A-CORE',125)
        else:
            rp=shape.representative_point();txt(rp.x,rp.y,core.kind.upper(),'A-CORE',125)
    index={w.id:w for w in lv.walls}
    for op in lv.openings:
        w=index.get(op.host_wall_id)
        if not w or op.offset_mm+op.width_mm>wall_length(w):continue
        a=at_wall(w,op.offset_mm);b=at_wall(w,op.offset_mm+op.width_mm)
        ux,uy=(b[0]-a[0])/op.width_mm,(b[1]-a[1])/op.width_mm
        nx,ny=-uy,ux
        cx,cy=(a[0]+b[0])/2,(a[1]+b[1])/2
        if op.kind in ('window','vent'):
            for shift in (-w.thickness_mm*.32,0,w.thickness_mm*.32):
                li((a[0]+nx*shift,a[1]+ny*shift),
                   (b[0]+nx*shift,b[1]+ny*shift),'A-WINDOW')
            for x,y in (a,b):
                li((x-nx*w.thickness_mm*.46,y-ny*w.thickness_mm*.46),
                   (x+nx*w.thickness_mm*.46,y+ny*w.thickness_mm*.46),'A-WINDOW')
            txt(cx+nx*160,cy+ny*160,op.id,'A-WINDOW',95)
        elif op.kind in ('door','sliding_door'):
            if op.kind=='sliding_door':
                li((a[0]-nx*75,a[1]-ny*75),(b[0]-nx*75,b[1]-ny*75),'A-DOOR')
                li((a[0]+nx*75,a[1]+ny*75),(b[0]+nx*75,b[1]+ny*75),'A-DOOR')
                continue
            px,py=(b if op.hinge=='end' else a)
            dx,dy=(-ux,-uy) if op.hinge=='end' else (ux,uy)
            side=-1 if op.swing=='left' else 1
            ex,ey=px+nx*side*op.width_mm,py+ny*side*op.width_mm
            sx,sy=px+dx*op.width_mm,py+dy*op.width_mm
            li((px,py),(ex,ey),'A-DOOR')
            cir(px,py,22,'A-DOOR')
            # Translate arc angles after Y flip: DXF arcs progress CCW.
            th0=math.degrees(math.atan2(-(sy-py),sx-px))%360
            th1=math.degrees(math.atan2(-(ey-py),ex-px))%360
            if (th1-th0)%360<=180:st,en=th0,th1
            else:st,en=th1,th0
            m.add_arc(pt(px,py),op.width_mm,start_angle=st,end_angle=en,
                      dxfattribs={'layer':'A-DOOR'})
            if op.width_mm>1000:txt(cx,cy,op.id,'A-DOOR',95)
        else:
            li(a,b,'A-DOOR')

    # Each 2D furniture symbol is a group of CAD entities with deterministic geometry.
    for o in lv.objects:
        w,d=o.width_mm,o.depth_mm;a,b=-w/2,-d/2
        layer='A-SAN' if o.kind in ('wc','sink','shower','bathtub','floor_drain') else ('A-ELEC' if o.kind in ('light','socket','switch') else 'A-FURN')
        local_rect(o,a,b,w,d,layer)
        kind=o.kind
        if kind=='bed':
            local_rect(o,a+70,b+105,w-140,d-210,layer)
            for x in (a+105,a+w/2+20):local_rect(o,x,b+145,w/2-135,min(440,d*.23),layer)
            local_line(o,a+80,b+d*.53,a+w-80,b+d*.53,layer)
        elif kind=='sofa':
            local_rect(o,a+90,b+80,w-180,d-160,layer)
            n=max(1,round(w/560))
            for j in range(1,n):
                x=a+w*j/n;local_line(o,x,b+120,x,b+d-95,layer)
        elif kind in ('wardrobe','cabinet','counter'):
            local_rect(o,a+45,b+45,w-90,d-90,layer)
            count=max(1,int(max(w,d)/520))
            for i in range(1,count):
                if w>=d: local_line(o,a+w*i/count,b+40,a+w*i/count,b+d-40,layer)
                else: local_line(o,a+40,b+d*i/count,a+w-40,b+d*i/count,layer)
        elif kind=='hob':
            for x in (a+w*.28,a+w*.72):
                for y in (b+d*.28,b+d*.72):local_circle(o,x,y,min(w,d)*.12,layer)
        elif kind=='wc':
            local_rect(o,a+60,b+15,w-120,min(d*.24,160),layer)
            # ellipse with rotation approximated by a closed 24-segment polyline.
            xy=[transform(o,w*.33*math.cos(2*math.pi*i/32),d*.22+d*.28*math.sin(2*math.pi*i/32)) for i in range(32)]
            polyline(xy,layer)
        elif kind in ('sink','bathtub'):
            xy=[transform(o,(w*.30)*math.cos(2*math.pi*i/36),(d*.32)*math.sin(2*math.pi*i/36)) for i in range(36)]
            polyline(xy,layer)
        elif kind=='shower':
            local_line(o,a+50,b+50,a+w-50,b+d-50,layer)
            local_line(o,a+w-50,b+50,a+50,b+d-50,layer)
            local_circle(o,0,0,45,layer)
        elif kind=='washing_machine':local_circle(o,0,0,min(w,d)*.34,layer)
        elif kind=='chair':local_rect(o,a+55,b+85,w-110,d-150,layer)
        elif kind=='stair':
            for i in range(1,max(2,int(d/260))):local_line(o,a,b+i*260,a+w,b+i*260,layer)
        elif kind=='light':
            local_circle(o,0,0,min(w,d)*.4,layer)
            local_line(o,a,b,a+w,b+d,layer)
            local_line(o,a+w,b,a,b+d,layer)
    # Room annotations preserve editable text instead of being converted to vector outlines.
    for room in lv.spaces:
        if room.kind in ('shaft','stairwell'):continue
        p=poly(room.polygon,room.holes)
        q=p.representative_point()
        txt(q.x,q.y-130,room.name.upper(),'A-TEXT',155)
        txt(q.x,q.y+100,f'{p.area/1e6:.2f} m2','A-TEXT',120)
    for a in lv.annotations:txt(a.at.x,a.at.y,a.text,'A-TEXT',130)

    x0,y0,x1,y1=poly(lv.footprint).bounds
    def dh(xa,xb,base,off):
        if xb<=xa:return
        y=base+off
        li((xa,base),(xa,y+65),'A-DIMS');li((xb,base),(xb,y+65),'A-DIMS')
        li((xa,y),(xb,y),'A-DIMS')
        for x in (xa,xb):li((x-55,y+55),(x+55,y-55),'A-DIMS')
        txt((xa+xb)/2,y-112,f'{xb-xa:,.0f}'.replace(',',' '),'A-DIMS',140)
    def dv(ya,yb,base,off):
        if yb<=ya:return
        x=base+off
        li((base,ya),(x-65,ya),'A-DIMS');li((base,yb),(x-65,yb),'A-DIMS')
        li((x,ya),(x,yb),'A-DIMS')
        for y in (ya,yb):li((x-55,y+55),(x+55,y-55),'A-DIMS')
        t=m.add_text(f'{yb-ya:,.0f}'.replace(',',' '),dxfattribs={'layer':'A-DIMS','height':145,'rotation':90})
        t.set_placement(pt(x-90,(ya+yb)/2),align=TextEntityAlignment.MIDDLE_CENTER)
    xs=sorted({x0,x1,*[w.start.x for w in lv.walls if abs(w.start.x-w.end.x)<.1 and wall_length(w)>2000]})
    for a,b in zip(xs,xs[1:]):
        if b-a>=750:dh(a,b,y1,450)
    dh(x0,x1,y1,980)
    dv(y0,y1,x0,-950)
    dv(y0,y1,x1,750)
    for dm in lv.dimensions:
        if abs(dm.start.y-dm.end.y)<1:
            dh(min(dm.start.x,dm.end.x),max(dm.start.x,dm.end.x),dm.start.y,dm.offset_mm)
    # Title block model-space drawing notes.
    li((x0-300,y1+1750),(x1+1100,y1+1750),'A-SHEET')
    txt(x0,y1+1990,plan.project.name.upper(),'A-TEXT',250,TextEntityAlignment.MIDDLE_LEFT)
    txt(x0,y1+2350,f'{lv.name}  |  A-101  |  REV {plan.project.revision}  |  UNITS mm','A-TEXT',155,TextEntityAlignment.MIDDLE_LEFT)
    txt(x1+850,y1+2350,'SCHEMATIC / NOT FOR CONSTRUCTION','A-TEXT',125,TextEntityAlignment.MIDDLE_RIGHT)
    # DXF text is native and walls are real polylines with optional native hatch.
    stream=StringIO();doc.write(stream)
    return stream.getvalue().encode('utf-8')
