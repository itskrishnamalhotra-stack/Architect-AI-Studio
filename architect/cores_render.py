"""Architectural SVG symbol helper for arbitrary-shaped structural/service cores."""
from __future__ import annotations
from xml.etree import ElementTree as ET
from math import cos,sin,pi
from .validate import poly
from .render_pro import n, f, P, L, T, polygon, R


def render_cores(root, level, defs):
    g=n(root,'g',{'id':'layer-structure'})
    for el in level.built_elements:
        pg=poly(el.polygon)
        if not pg.is_valid:continue
        group=n(g,'g',{'data-built-id':el.id,'data-kind':el.kind})
        cl={'column':'core-column','pier':'core-column','shaft':'core-shaft',
            'duct':'core-shaft','lightwell':'core-void','atrium':'core-void','void':'core-void'}.get(el.kind,'core-shaft')
        polygon(group,pg,cl)
        if el.kind in ('column','pier'):
            x0,y0,x1,y1=pg.bounds
            L(group,x0+30,y0+30,x1-30,y1-30,'core-cross')
            L(group,x1-30,y0+30,x0+30,y1-30,'core-cross')
        else:
            centre=pg.representative_point()
            T(group,centre.x,centre.y-55,'SHAFT' if el.kind in ('shaft','duct') else el.kind.upper(),'core-label')
            T(group,centre.x,centre.y+100,el.id,'core-sub')
    for conn in level.vertical_connectors:
        pg=poly(conn.polygon)
        if not pg.is_valid:continue
        group=n(g,'g',{'data-core-id':conn.id,'data-kind':conn.kind})
        polygon(group,pg,'core-outline')
        minx,miny,maxx,maxy=pg.bounds
        w=maxx-minx;h=maxy-miny
        midx=(minx+maxx)*.5;midy=(miny+maxy)*.5
        if conn.kind=='stair':
            # Split the flight representation into two runs, tied to true core bounds.
            inset=min(180,w*.08,h*.06)
            a=minx+inset;b=maxx-inset;y0=miny+inset+min(750,(maxy-miny)*.24);y1=maxy-inset-min(710,(maxy-miny)*.22)
            runwidth=(b-a)*.45
            risers=max(3,min(16,(conn.step_count or 18)//2))
            for startx,endx in ((a,a+runwidth),(b-runwidth,b)):
                R(group,startx,y0,endx-startx,y1-y0,'core-flight')
                for k in range(1,risers):
                    y=y0+(y1-y0)*k/risers
                    L(group,startx,y,endx,y,'core-tread')
            L(group,midx,y0+120,midx,y1-120,'core-arrow')
            P(group,f'M {f(midx-100)} {f(y0+280)} L {f(midx)} {f(y0+100)} L {f(midx+100)} {f(y0+280)}','core-arrow')
            T(group,midx,midy,'UP','core-label')
            for landing in conn.landings:
                land=poly(landing)
                if land.is_valid:polygon(group,land,'core-landing')
        elif conn.kind=='lift':
            inset=min(180,w*.08,h*.08)
            R(group,minx+inset,miny+inset,w-2*inset,h-2*inset,'core-lift')
            L(group,minx+inset,miny+inset,maxx-inset,maxy-inset,'core-lift-diag')
            L(group,maxx-inset,miny+inset,minx+inset,maxy-inset,'core-lift-diag')
            T(group,midx,midy,'LIFT','core-label')
            T(group,midx,midy+170,conn.id,'core-sub')
        else:
            T(group,midx,midy,conn.kind.upper(),'core-label')
    return g
