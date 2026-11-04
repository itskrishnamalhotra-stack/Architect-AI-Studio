"""Measured property site plan and optional presentation styling for detailed V3 floor drawings."""
from __future__ import annotations
import math, random
from xml.etree import ElementTree as ET
from shapely.affinity import translate
from .property_models import PropertyProject
from .validate import poly
from .render import render_svg,render_dxf

NS='http://www.w3.org/2000/svg';ET.register_namespace('',NS)
def e(parent,tag,**attrs):return ET.SubElement(parent,'{%s}%s'%(NS,tag),{k.replace('_','-'):str(v) for k,v in attrs.items()})
def txt(parent,x,y,value,klass='text',**kwargs):
    t=e(parent,'text',x=f'{x:.2f}',y=f'{y:.2f}',**{'class':klass},**kwargs);t.text=str(value);return t

def pts(pg):return ' '.join(f'{x:.2f},{y:.2f}' for x,y in list(pg.exterior.coords)[:-1])

def render_site_svg(project:PropertyProject):
    site=poly(project.site.boundary);x0,y0,x1,y1=site.bounds
    pw=x1-x0;ph=y1-y0
    pad=3000;footer=4900;ww=pw+2*pad;hh=ph+2*pad+footer
    root=ET.Element('{%s}svg'%NS,{'viewBox':f'{x0-pad} {y0-pad} {ww} {hh}',
                 'width':'1400','height':str(round(1400*hh/ww)),
                 'role':'img','aria-label':'Architectural landscape and site concept drawing'})
    defs=e(root,'defs');css='''
    text{font-family:Arial,Helvetica,sans-serif}.canvas{fill:#fbfcfa}
    .plot{fill:#fbfbf7;stroke:#333f46;stroke-width:90}
    .street{fill:#e8ebef;stroke:#aab5bf;stroke-width:24}
    .building{fill:#e3ebf1;stroke:#263d4e;stroke-width:95;stroke-linejoin:round}
    .building-inner{fill:none;stroke:#fff;stroke-width:85;stroke-linejoin:round}
    .green{fill:#d8eace;stroke:#7f9e71;stroke-width:35}
    .drive{fill:#e5e7e6;stroke:#92999b;stroke-width:35}
    .park{fill:#f5f5f2;stroke:#b7a79b;stroke-width:30}
    .walk{fill:#e8ddcd;stroke:#b9a991;stroke-width:30}
    .gate{fill:#fff;stroke:#315e71;stroke-width:45}
    .title{fill:#163245;font-weight:700;font-size:450px;letter-spacing:10px}
    .sub{fill:#5a7380;font-size:240px;letter-spacing:8px}
    .name{fill:#163245;font-weight:700;font-size:220px;text-anchor:middle}
    .label{fill:#466978;font-size:165px;text-anchor:middle}
    .small{fill:#42616d;font-size:160px}.dim{fill:#2a7092;font-size:175px}
    .line{stroke:#6c8da0;stroke-width:22;fill:none}
    .trees{fill:#b3d5a7;stroke:#6a9971;stroke-width:31}
    .car{fill:#eff6fa;stroke:#47788a;stroke-width:40}
    .roadmark{stroke:#fff;stroke-width:70;stroke-dasharray:450 380;fill:none}
    '''
    st=e(defs,'style');st.text=css
    hatch=e(defs,'pattern',id='rooflines',patternUnits='userSpaceOnUse',width='340',height='340',patternTransform='rotate(35)')
    e(hatch,'path',d='M 0 0 L 0 340',stroke='#b6c8d2',stroke_width='45')
    e(root,'rect',x=x0-pad,y=y0-pad,width=ww,height=hh,**{'class':'canvas'})
    # Road occupies an actual strip outside the plot, not invented land within it.
    e(root,'rect',x=x0-pad+80,y=y1+210,width=ww-160,height=1200,**{'class':'street'})
    e(root,'line',x1=x0-pad+150,y1=y1+790,x2=x1+pad-150,y2=y1+790,**{'class':'roadmark'})
    txt(root,(x0+x1)/2,y1+1200,'ROAD FRONTAGE  /  SOUTH', 'sub',text_anchor='middle')
    e(root,'polygon',points=pts(site),**{'class':'plot'})
    for area in project.site_areas:
        pg=poly(area.polygon)
        cls={'lawn':'green','garden':'green','tree':'trees','parking_bay':'park','driveway':'drive',
             'walkway':'walk','gate':'gate','courtyard':'green'}.get(area.kind,'walk')
        e(root,'polygon',points=pts(pg),**{'class':cls},id=f'site_{area.id}')
        cx,cy=pg.representative_point().coords[0]
        if area.kind=='lawn':
            rng=random.Random(26)
            bx0,by0,bx1,by1=pg.bounds
            for i in range(18):
                tx=rng.uniform(bx0+230,bx1-230);ty=rng.uniform(by0+230,by1-230)
                if pg.buffer(-300).covers(__import__('shapely').geometry.Point(tx,ty)):
                    e(root,'circle',cx=round(tx),cy=round(ty),r=rng.randint(80,220),**{'class':'trees'},opacity='.7')
            txt(root,cx,cy,area.label,'name')
        elif area.kind=='parking_bay':
            x,y,xx,yy=pg.bounds
            e(root,'rect',x=x+500,y=y+620,width=min(1550,xx-x-900),height=min(3000,yy-y-1200),rx=280,**{'class':'car'})
            e(root,'rect',x=x+690,y=y+1400,width=850,height=750,rx=140,fill='#cde3eb',stroke='#7396a6',stroke_width=25)
            txt(root,cx,by0 if False else y+450,area.label,'label')
        elif area.kind in ('driveway','walkway'):
            if pg.area>3e6:txt(root,cx,cy,area.label,'label')
        elif area.kind=='gate':
            e(root,'line',x1=pg.bounds[0],y1=pg.bounds[1],x2=pg.bounds[2],y2=pg.bounds[1],stroke='#315e71',stroke_width=60,stroke_dasharray='200 120')
    # Building footprints rendered in actual plot coordinates (not scaled doodles).
    for block in project.buildings:
        fp=translate(poly(block.plan.levels[0].footprint),xoff=block.site_origin.x,yoff=block.site_origin.y)
        e(root,'polygon',points=pts(fp),**{'class':'building'})
        e(root,'polygon',points=pts(fp),fill='url(#rooflines)',stroke='none')
        e(root,'polygon',points=pts(fp),**{'class':'building-inner'})
        cx,cy=fp.representative_point().coords[0]
        label='GARAGE' if block.id=='garage_block' else block.name.upper()
        txt(root,cx,cy-250,label,'name')
        txt(root,cx,cy+110,f'{len(block.plan.levels)} LEVEL(S)  ·  {len(block.units)} UNIT(S)','label')
    # Plot real overall dimension lines in millimetres.
    yline=y0-850;xline=x0-950
    for x in (x0,x1):e(root,'line',x1=x,y1=y0,x2=x,y2=yline-140,**{'class':'line'})
    e(root,'line',x1=x0,y1=yline,x2=x1,y2=yline,**{'class':'line'})
    txt(root,(x0+x1)/2,yline-190,f'{pw:,.0f} mm  /  {pw/1000:.1f} m','dim',text_anchor='middle')
    for y in (y0,y1):e(root,'line',x1=x0,y1=y,x2=xline-90,y2=y,**{'class':'line'})
    e(root,'line',x1=xline,y1=y0,x2=xline,y2=y1,**{'class':'line'})
    txt(root,xline-170,(y0+y1)/2,f'{ph/1000:.1f} m','dim',text_anchor='middle',transform=f'rotate(-90 {xline-170} {(y0+y1)/2})')
    # North marker and legend, anchored outside parcel boundary.
    nx=x1+1450;ny=y0+1000
    e(root,'path',d=f'M {nx} {ny-620} l -230 700 l 230 -140 l 230 140 Z',fill='#285b72')
    txt(root,nx,ny-840,'N','title',text_anchor='middle')
    legend=y1+2060
    e(root,'line',x1=x0,y1=legend-420,x2=x1,y2=legend-420,stroke='#617989',stroke_width=35)
    txt(root,x0,legend,'PROPERTY MASTER PLAN  /  V4','title')
    txt(root,x0,legend+480,f'{project.request.property_type.upper()}  |  PLOT {pw/1000:.1f} × {ph/1000:.1f} m  |  CONCEPT SCHEME','sub')
    txt(root,x0,legend+950,'Architectural feasibility illustration · Site geometry in millimetres','sub')
    txt(root,x0,legend+1280,'NOT A SURVEY · NOT REGULATORY/STRUCTURAL APPROVAL · NOT FOR CONSTRUCTION','small')
    return ET.tostring(root,encoding='unicode')

def render_floor_svg(project:PropertyProject,building_id='main',level_id=None,style='technical'):
    block=next((b for b in project.buildings if b.id==building_id),None)
    if not block:raise ValueError('Unknown building_id')
    svg=render_svg(block.plan,level_id)
    if style=='presentation':
        root=ET.fromstring(svg)
        extra='''
          .roomfill{fill:#f8f5ee!important}.wetfill{fill:#edf7fb!important}.utilityfill{fill:#f2f4f4!important}
          .furniture-heavy{fill:#e6ecea!important;stroke:#317f8c!important}
          .furniture-medium{fill:#f2e9e1!important;stroke:#4d9295!important}
          .sanitary{fill:#f5ecf8!important;stroke:#98689e!important}
          .wall-hatch{stroke:#253746!important}.room-name{fill:#233b43!important}
        '''
        # Put overrides at end so original drawing remains measured and dimensioned.
        defs=root.find('{%s}defs'%NS)
        node=e(defs,'style');node.text=extra
        return ET.tostring(root,encoding='unicode')
    if style!='technical':raise ValueError('style must be technical or presentation')
    return svg

def render_floor_dxf(project:PropertyProject,building_id='main',level_id=None):
    block=next((b for b in project.buildings if b.id==building_id),None)
    if not block:raise ValueError('Unknown building_id')
    return render_dxf(block.plan,level_id)
