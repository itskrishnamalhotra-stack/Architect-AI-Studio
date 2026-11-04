"""Deterministic SVG technical drawing and DXF export; model coordinates remain mm."""
from __future__ import annotations
from collections import defaultdict
from io import StringIO
from xml.etree import ElementTree as ET
import math
from shapely.geometry import Polygon, LineString, box as sbox
from .models import FloorPlan
from .validate import poly, wall_length, at_wall, object_polygon

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

def e(parent, tag, attrib=None, text=None, **kwargs):
    node=ET.SubElement(parent, f"{{{SVG_NS}}}{tag}", {k:str(v) for k,v in (attrib or {}).items()})
    for k,v in kwargs.items(): node.set(k.replace("_","-"),str(v))
    if text is not None: node.text=str(text)
    return node


def fmt(v): return f"{v:.3f}".rstrip('0').rstrip('.') if isinstance(v,float) else str(v)

def xy(p): return f"{fmt(p.x)},{fmt(p.y)}"

def polygon_points(g): return " ".join(f"{fmt(x)},{fmt(y)}" for x,y in list(g.exterior.coords)[:-1])

def wall_parts(w, openings):
    """Exact openings cut out of wall's centerline; wall strokes are polygons."""
    length=wall_length(w)
    if length < 1: return []
    intervals=sorted((max(0,o.offset_mm),min(length,o.offset_mm+o.width_mm)) for o in openings)
    cursor=0
    pieces=[]
    for start,end in intervals:
        if start > cursor + 0.01: pieces.append((cursor,start))
        cursor=max(cursor,end)
    if cursor<length: pieces.append((cursor,length))
    ans=[]
    for start,end in pieces:
        if end-start < 0.1: continue
        a=at_wall(w,start);b=at_wall(w,end)
        ans.append(LineString([a,b]).buffer(w.thickness_mm/2,cap_style=2,join_style=2))
    return ans


def _dimension(parent, x1,y1,x2,y2, offset=400, text=None):
    vx,vy=x2-x1,y2-y1
    length=math.hypot(vx,vy)
    if length<1:return
    nx,ny=-vy/length, vx/length
    ax,ay=x1+nx*offset,y1+ny*offset
    bx,by=x2+nx*offset,y2+ny*offset
    for a,b,c,d in [(x1,y1,ax+nx*110,ay+ny*110),(x2,y2,bx+nx*110,by+ny*110),(ax,ay,bx,by)]:
        e(parent,"line",{"x1":fmt(a),"y1":fmt(b),"x2":fmt(c),"y2":fmt(d),"class":"dim-line"})
    for x,y in [(ax,ay),(bx,by)]:
        e(parent,"line",{"x1":fmt(x-75*nx-50*vx/length),"y1":fmt(y-75*ny-50*vy/length),
                         "x2":fmt(x+75*nx+50*vx/length),"y2":fmt(y+75*ny+50*vy/length),"class":"dim-line"})
    label = text if text else f"{int(round(length)):,} mm"
    x,y=(ax+bx)/2+nx*135,(ay+by)/2+ny*135
    attrib={"x":fmt(x),"y":fmt(y),"class":"dim-text","text-anchor":"middle"}
    if abs(vy)>abs(vx)*2:
        attrib["transform"]=f"rotate(-90 {fmt(x)} {fmt(y)})"
    e(parent,"text",attrib,label)


def render_svg(plan:FloorPlan, level_id:str|None=None) -> str:
    level=next((l for l in plan.levels if l.id==level_id),None) if level_id else plan.levels[0]
    if level is None: raise ValueError(f"Unknown level: {level_id}")
    footprint=poly(level.footprint)
    if not footprint.is_valid: raise ValueError("Invalid footprint")
    xmin,ymin,xmax,ymax=footprint.bounds
    w,h=xmax-xmin,ymax-ymin
    if w<1 or h<1:raise ValueError("Empty footprint")
    pad=max(1250, min(w,h)*0.13)
    # Need sufficient bottom for titleblock and left/bottom dimensions.
    root=ET.Element(f"{{{SVG_NS}}}svg",{"viewBox":f"{fmt(xmin-pad)} {fmt(ymin-pad)} {fmt(w+pad*2)} {fmt(h+pad*2.7)}",
                                            "width":"1400", "height":fmt(1400*(h+pad*2.7)/(w+pad*2)),
                                            "role":"img","aria-label":f"Architectural concept floor plan: {plan.project.name}"})
    e(root,"title",text=f"{plan.project.name} — {level.name}")
    defs=e(root,"defs")
    style='''
      .sheet{fill:#fff}.room{stroke:#ddd8cf;stroke-width:10}
      .wall-exterior{fill:#252e39;stroke:#121a23;stroke-width:9}
      .wall-interior{fill:#53616d;stroke:#273440;stroke-width:6}
      .room-label{fill:#202934;font-weight:600;font-size:165px;font-family:Arial,sans-serif;text-anchor:middle}
      .room-area{fill:#74808b;font-size:120px;font-family:Arial,sans-serif;text-anchor:middle}
      .object{fill:#d8e3df;stroke:#497168;stroke-width:20}
      .object-fixture{fill:#e1e7ed;stroke:#697d91;stroke-width:17}
      .object-text{font-size:85px;font-family:Arial,sans-serif;fill:#42565e;text-anchor:middle}
      .opening{stroke:#2b7d9d;fill:none;stroke-width:27}
      .door{stroke:#b07649;fill:none;stroke-width:27}
      .swing{stroke:#ae835e;stroke-width:14;fill:none;stroke-dasharray:45 35}
      .window{stroke:#1688b6;stroke-width:25;fill:none}
      .dim-line{stroke:#89929c;stroke-width:9;fill:none}
      .dim-text{fill:#697786;font-size:135px;font-family:Arial,sans-serif}
      .note{fill:#596571;font-size:140px;font-family:Arial,sans-serif}
      .border{stroke:#233e54;stroke-width:16;fill:none}
      .north{stroke:#215c7d;fill:none;stroke-width:20}
    '''
    e(defs,"style",text=style)
    e(root,"rect",{"x":fmt(xmin-pad),"y":fmt(ymin-pad),"width":fmt(w+pad*2),"height":fmt(h+pad*2.7),"class":"sheet"})
    rooms_g=e(root,"g",{"id":"layer-spaces"})
    room_colors={"living":"#eef3f2","bedroom":"#f5f0ed","kitchen":"#f4f1e6","bathroom":"#e8f1f6",
                 "toilet":"#e8f1f6","dining":"#f6f0e5","corridor":"#f0f1f3","hall":"#f0f1f3", "utility":"#edf0e8", "balcony":"#eaf5eb"}
    for room in level.spaces:
        p=poly(room.polygon)
        if not p.is_valid:continue
        e(rooms_g,"polygon",{"points":polygon_points(p),"class":"room","fill":room_colors.get(room.kind,"#f4f5f4")})
    walls_g=e(root,"g",{"id":"layer-walls"})
    openings_by_wall=defaultdict(list)
    for o in level.openings:openings_by_wall[o.host_wall_id].append(o)
    for wall in level.walls:
        for wall_poly in wall_parts(wall,openings_by_wall.get(wall.id,[])):
            if wall_poly.is_empty or wall_poly.geom_type!="Polygon":continue
            e(walls_g,"polygon",{"points":polygon_points(wall_poly),
                                 "class":"wall-exterior" if wall.kind=="exterior" else "wall-interior",
                                 "data-wall-id":wall.id})
    opening_g=e(root,"g",{"id":"layer-openings"})
    wall_index={w.id:w for w in level.walls}
    for o in level.openings:
        wall=wall_index.get(o.host_wall_id)
        if not wall or wall_length(wall)<1:continue
        length=wall_length(wall)
        if o.offset_mm+o.width_mm>length:continue
        ax,ay=at_wall(wall,o.offset_mm)
        bx,by=at_wall(wall,o.offset_mm+o.width_mm)
        dx,dy=(bx-ax)/o.width_mm,(by-ay)/o.width_mm
        if o.kind in ("window","vent"):
            # Double thin glazing lines within an opening.
            nx,ny=-dy,dx
            for sign in (-1,1):
                shift=sign*min(35,wall.thickness_mm/5)
                e(opening_g,"line",{"x1":fmt(ax+nx*shift),"y1":fmt(ay+ny*shift),
                                     "x2":fmt(bx+nx*shift),"y2":fmt(by+ny*shift),"class":"window"})
        elif o.kind in ("door","sliding_door"):
            if o.kind == "sliding_door":
                e(opening_g,"line",{"x1":fmt(ax),"y1":fmt(ay),"x2":fmt(bx),"y2":fmt(by),"class":"door"})
                continue
            pivot_x,pivot_y=(ax,ay) if o.hinge!="end" else (bx,by)
            ux,uy=(dx,dy) if o.hinge!="end" else (-dx,-dy)
            side=1 if o.swing=="left" else -1
            leaf_x,leaf_y=pivot_x-side*uy*o.width_mm,pivot_y+side*ux*o.width_mm
            e(opening_g,"line",{"x1":fmt(pivot_x),"y1":fmt(pivot_y),"x2":fmt(leaf_x),"y2":fmt(leaf_y),"class":"door"})
            # Quadratic curve approximates a 90° swing, not an envelope/clearance study.
            control_x=pivot_x + (ux-side*uy)*o.width_mm*.7
            control_y=pivot_y + (uy+side*ux)*o.width_mm*.7
            end_x,end_y=pivot_x+ux*o.width_mm,pivot_y+uy*o.width_mm
            e(opening_g,"path",{"d":f"M {fmt(end_x)} {fmt(end_y)} Q {fmt(control_x)} {fmt(control_y)} {fmt(leaf_x)} {fmt(leaf_y)}","class":"swing"})
            e(opening_g,"circle",{"cx":fmt(pivot_x),"cy":fmt(pivot_y),"r":"35","fill":"#ae835e"})
        else:
            e(opening_g,"line",{"x1":fmt(ax),"y1":fmt(ay),"x2":fmt(bx),"y2":fmt(by),"class":"opening"})

    objs=e(root,"g",{"id":"layer-objects"})
    special_fixture={"sink","wc","shower","bathtub","floor_drain","light","socket","switch","electrical","plumbing","hob","fridge"}
    for o in level.objects:
        g=e(objs,"g",{"transform":f"translate({fmt(o.center.x)} {fmt(o.center.y)}) rotate({fmt(o.rotation_degrees)})","data-object-id":o.id})
        klass="object-fixture" if o.kind in special_fixture else "object"
        e(g,"rect",{"x":fmt(-o.width_mm/2),"y":fmt(-o.depth_mm/2),"width":fmt(o.width_mm),"height":fmt(o.depth_mm),"rx":"30","class":klass})
        if o.kind == "bed":
            for sign in (-1,1):
                e(g,"rect",{"x":fmt(-o.width_mm*.37 if sign==-1 else 0),"y":fmt(-o.depth_mm*.4),
                            "width":fmt(o.width_mm*.34),"height":fmt(o.depth_mm*.22),"rx":"24","fill":"#fff","stroke":"#9db5ad","stroke-width":"12"})
        if o.kind in ("sink","wc","hob","table","light"):
            e(g,"ellipse",{"cx":"0","cy":"0","rx":fmt(o.width_mm*.3),"ry":fmt(o.depth_mm*.3),"fill":"none","stroke":"#718892","stroke-width":"17"})
        if o.kind == "stair":
            steps=max(2,min(25,int(o.depth_mm/250)))
            for i in range(1,steps):
                y=-o.depth_mm/2+o.depth_mm*i/steps
                e(g,"line",{"x1":fmt(-o.width_mm/2),"y1":fmt(y),"x2":fmt(o.width_mm/2),"y2":fmt(y),"stroke":"#8d9ba8","stroke-width":"14"})
        if o.width_mm>550 and o.depth_mm>400:
            e(g,"text",{"x":"0","y":fmt(o.depth_mm*.36),"class":"object-text"},o.name[:28])
    labels=e(root,"g",{"id":"layer-labels"})
    object_shapes=[object_polygon(o).buffer(80) for o in level.objects]
    for room in level.spaces:
        p=poly(room.polygon)
        if not p.is_valid:continue
        l,b,r,t=p.bounds
        label_w=max(700,len(room.name)*162)
        # Try several positions and choose the most legible free area, rather than
        # blindly writing room names over beds/counters and sanitary fixtures.
        candidates=[(l+(r-l)*fx,b+(t-b)*fy) for fy in (.35,.55,.75,.2,.88) for fx in (.5,.32,.68,.18,.82)]
        best=None;best_score=-1e99
        for x,y in candidates:
            label_box=sbox(x-label_w/2,y-320,x+label_w/2,y+230)
            if not p.buffer(-30).covers(label_box):continue
            conflicts=sum(label_box.intersection(ob).area for ob in object_shapes)
            safe=p.boundary.distance(label_box)
            center_penalty=((x-(l+r)/2)**2+(y-(b+t)/2)**2)**.5*.04
            score=safe*.12-center_penalty-conflicts/200
            if score>best_score:best_score=score;best=(x,y)
        if best is None:
            point=p.representative_point();best=(point.x,point.y)
        x,y=best
        e(labels,"text",{"x":fmt(x),"y":fmt(y-45),"class":"room-label"},room.name)
        e(labels,"text",{"x":fmt(x),"y":fmt(y+155),"class":"room-area"},f"{p.area/1e6:.1f} m²")
    note_g=e(root,"g",{"id":"layer-annotations"})
    for note in level.annotations:
        e(note_g,"text",{"x":fmt(note.at.x),"y":fmt(note.at.y),"transform":f"rotate({fmt(note.rotation_degrees)} {fmt(note.at.x)} {fmt(note.at.y)})","class":"note"},note.text)
    dims=e(root,"g",{"id":"layer-dimensions"})
    _dimension(dims,xmin,ymax,xmax,ymax,620)
    _dimension(dims,xmin,ymin,xmin,ymax,-620)
    for d in level.dimensions:
        _dimension(dims,d.start.x,d.start.y,d.end.x,d.end.y,d.offset_mm,d.text_override)
    # north marker: angle of 0 degrees points upwards.
    ng=e(root,"g",{"id":"layer-north","transform":f"translate({fmt(xmax+pad*.46)} {fmt(ymin+pad*.4)}) rotate({fmt(plan.project.north_degrees_clockwise_from_page_up)})"})
    e(ng,"path",{"d":"M 0 -350 L -90 -70 L 0 -125 L 90 -70 Z","fill":"#215c7d"})
    e(ng,"line",{"x1":"0","y1":"-120","x2":"0","y2":"210","class":"north"})
    e(ng,"text",{"x":"0","y":"-450","text-anchor":"middle","class":"note","font-weight":"700"},"N")
    tb=e(root,"g",{"id":"layer-titleblock"})
    ytb=ymax+pad*.93
    e(tb,"line",{"x1":fmt(xmin),"y1":fmt(ytb-240),"x2":fmt(xmax),"y2":fmt(ytb-240),"stroke":"#28465b","stroke-width":"18"})
    e(tb,"text",{"x":fmt(xmin),"y":fmt(ytb),"fill":"#202934","text-anchor":"start","font-family":"Arial, sans-serif","font-size":"220","font-weight":"700"},plan.project.name)
    e(tb,"text",{"x":fmt(xmin),"y":fmt(ytb+270),"class":"note"},f"{level.name}   •   Elevation {level.elevation_mm:g} mm   •   Rev {plan.project.revision}")
    e(tb,"text",{"x":fmt(xmax),"y":fmt(ytb+270),"text-anchor":"end","class":"note"},"CONCEPT / NOT FOR CONSTRUCTION")
    return ET.tostring(root,encoding="unicode",xml_declaration=False)


def render_dxf(plan:FloorPlan, level_id:str|None=None) -> bytes:
    import ezdxf
    level=next((l for l in plan.levels if l.id==level_id),None) if level_id else plan.levels[0]
    if level is None:raise ValueError("Unknown level")
    doc=ezdxf.new("R2013")
    doc.header["$INSUNITS"]=4  # millimeters
    for name,color in [("A-FOOTPRINT",8),("A-SPACES",9),("A-WALL",7),("A-DOOR",30),("A-WINDOW",4),("A-FURN",3),("A-TEXT",7),("A-DIMS",8)]:
        doc.layers.add(name,color=color)
    msp=doc.modelspace()
    msp.add_lwpolyline([(p.x,-p.y) for p in level.footprint],close=True,dxfattribs={"layer":"A-FOOTPRINT"})
    for r in level.spaces:
        msp.add_lwpolyline([(p.x,-p.y) for p in r.polygon],close=True,dxfattribs={"layer":"A-SPACES"})
        p=poly(r.polygon).representative_point()
        msp.add_text(f"{r.name} ({poly(r.polygon).area/1e6:.1f}m2)",dxfattribs={"height":160,"layer":"A-TEXT","insert":(p.x,-p.y)})
    openings_by_wall=defaultdict(list)
    for o in level.openings: openings_by_wall[o.host_wall_id].append(o)
    for w in level.walls:
        for piece in wall_parts(w,openings_by_wall.get(w.id,[])):
            if piece.geom_type=="Polygon":
                msp.add_lwpolyline([(x,-y) for x,y in list(piece.exterior.coords)[:-1]],close=True,dxfattribs={"layer":"A-WALL"})
    wi={w.id:w for w in level.walls}
    for o in level.openings:
        w=wi.get(o.host_wall_id)
        if not w or o.offset_mm+o.width_mm>wall_length(w):continue
        a,b=at_wall(w,o.offset_mm),at_wall(w,o.offset_mm+o.width_mm)
        msp.add_line((a[0],-a[1]),(b[0],-b[1]),dxfattribs={"layer":"A-WINDOW" if o.kind in ("window","vent") else "A-DOOR"})
    for o in level.objects:
        p=object_polygon(o)
        msp.add_lwpolyline([(x,-y) for x,y in list(p.exterior.coords)[:-1]],close=True,dxfattribs={"layer":"A-FURN"})
    for a in level.annotations:
        msp.add_text(a.text,dxfattribs={"height":140,"layer":"A-TEXT","insert":(a.at.x,-a.at.y)})
    stream=StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")

# Version 2 replaces the schematic SVG view with detailed architectural drafting.
# The canonical data model and DXF API remain backwards compatible.
render_svg_schematic = render_svg
from .render_pro import render_svg

# CAD export in v2 uses native DXF entities for opening arcs, object families,
# dimension chains and wall hatch in real millimetres.
render_dxf_schematic = render_dxf
from .render_cad import render_dxf
