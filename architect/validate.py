"""Deterministic geometric and programmatic checks. These are NOT building-code approval."""
from __future__ import annotations
from collections import Counter, defaultdict, deque
import math
from shapely.geometry import Polygon, Point as SPoint, LineString
from shapely.ops import unary_union
from .models import FloorPlan, DesignConstraints, Issue, ValidationReport


PASSABLE = {"door", "sliding_door", "arch", "opening"}
EXEMPT_ACCESS = {"shaft", "stairwell"}
EXTERIOR_WINDOW_RECOMMENDED = {"bedroom", "living", "kitchen", "study", "office"}


def poly(points, holes=()):
    # Preserve arbitrary concavity and correctly subtract explicit inner void rings.
    # Never call make_valid/buffer(0): that could hide an incorrect design.
    return Polygon([(p.x, p.y) for p in points],
                   [[(p.x, p.y) for p in ring] for ring in holes])


def wall_length(w):
    return math.hypot(w.end.x - w.start.x, w.end.y - w.start.y)


def at_wall(w, offset):
    length = wall_length(w)
    ratio = offset / length if length else 0
    return (w.start.x + (w.end.x-w.start.x)*ratio, w.start.y + (w.end.y-w.start.y)*ratio)


def object_polygon(o):
    w, d = o.width_mm/2, o.depth_mm/2
    a = math.radians(o.rotation_degrees)
    c, s = math.cos(a), math.sin(a)
    return Polygon([(o.center.x + x*c-y*s, o.center.y+x*s+y*c)
                    for x,y in [(-w,-d),(w,-d),(w,d),(-w,d)]])


def validate_plan(plan: FloorPlan, constraints: DesignConstraints | None = None) -> ValidationReport:
    constraints = constraints or DesignConstraints(require_exterior_entrance=False)
    issues: list[Issue] = []
    summaries = []
    def issue(sev, code, msg, path=""):
        issues.append(Issue(severity=sev, code=code, message=msg, path=path))

    materials = {m.id for m in plan.materials}
    if len(materials) != len(plan.materials):
        issue("error", "DUPLICATE_MATERIAL_ID", "Material IDs must be unique", "materials")
    if len(set(l.id for l in plan.levels)) != len(plan.levels):
        issue("error", "DUPLICATE_LEVEL_ID", "Level IDs must be unique", "levels")

    for li, level in enumerate(plan.levels):
        prefix = f"levels[{li}]"
        footprints = poly(level.footprint, level.footprint_holes)
        if not footprints.is_valid or footprints.area <= 0:
            issue("error", "INVALID_FOOTPRINT", "Footprint has self-crossings or invalid area", f"{prefix}.footprint")
            continue
        xmin, ymin, xmax, ymax = footprints.bounds
        if constraints.envelope_width_mm and abs((xmax-xmin)-constraints.envelope_width_mm) > 30:
            issue("error", "ENVELOPE_WIDTH", f"Expected width {constraints.envelope_width_mm:g} mm, got {xmax-xmin:g} mm", prefix)
        if constraints.envelope_depth_mm and abs((ymax-ymin)-constraints.envelope_depth_mm) > 30:
            issue("error", "ENVELOPE_DEPTH", f"Expected depth {constraints.envelope_depth_mm:g} mm, got {ymax-ymin:g} mm", prefix)
        objects_by_category = {"spaces": level.spaces, "walls": level.walls, "openings": level.openings,
                               "objects": level.objects, "annotations": level.annotations, "dimensions": level.dimensions}
        ids = [o.id for seq in objects_by_category.values() for o in seq]
        for duplicate, count in Counter(ids).items():
            if count > 1: issue("error", "DUPLICATE_ELEMENT_ID", f"ID '{duplicate}' occurs {count} times", prefix)
        rooms = {}
        for idx, r in enumerate(level.spaces):
            path = f"{prefix}.spaces[{idx}]"
            p = poly(r.polygon, r.holes)
            if not p.is_valid or p.area < 10000:
                issue("error", "INVALID_SPACE", f"Space '{r.name}' has invalid / negligible polygon area", path)
                continue
            outside_area = p.difference(footprints).area
            if outside_area > 100:
                issue("error", "SPACE_OUTSIDE_FOOTPRINT", f"'{r.name}' extends {outside_area/1e6:.2f} m² beyond building footprint", path)
            rooms[r.id] = (r,p)
            if r.floor_material_id and r.floor_material_id not in materials:
                issue("warning", "UNKNOWN_MATERIAL", f"'{r.name}' floor refers to missing material '{r.floor_material_id}'", path)
            if r.ceiling_height_mm and r.ceiling_height_mm > level.default_clear_height_mm + 500:
                issue("warning", "CEILING_HEIGHT", f"'{r.name}' ceiling height exceeds default by over 500 mm", path)
            # Configurable indicative planning warnings; not asserted legal minimums.
            if r.kind in ("bedroom", "living", "kitchen", "office") and p.area < 6e6:
                issue("warning", "SMALL_HABITABLE_SPACE", f"'{r.name}' is only {p.area/1e6:.1f} m²; assess actual suitability", path)
            if r.kind == "corridor" and min(p.minimum_rotated_rectangle.bounds[2]-p.bounds[0], p.bounds[3]-p.bounds[1]) < 850:
                issue("warning", "NARROW_CORRIDOR", f"'{r.name}' may be narrower than an indicative 850 mm", path)
        room_list = list(rooms.items())
        for i in range(len(room_list)):
            for j in range(i+1, len(room_list)):
                a = room_list[i][1][1]; b = room_list[j][1][1]
                overlap = a.intersection(b).area
                if overlap > 1000:
                    issue("error", "ROOM_OVERLAP", f"Spaces '{room_list[i][1][0].name}' and '{room_list[j][1][0].name}' overlap by {overlap/1e6:.3f} m²", prefix)

        wall_map = {w.id: w for w in level.walls}
        wall_lines = []
        for wi, w in enumerate(level.walls):
            path = f"{prefix}.walls[{wi}]"
            length = wall_length(w)
            if length < 50:
                issue("error", "SHORT_WALL", f"Wall '{w.id}' is less than 50 mm long", path)
                continue
            line = LineString([(w.start.x,w.start.y),(w.end.x,w.end.y)])
            wall_lines.append(line)
            if line.difference(footprints.buffer(200)).length > 200:
                issue("warning", "WALL_BEYOND_FOOTPRINT", f"Wall '{w.id}' extends beyond the modeled footprint", path)
            if w.material_id and w.material_id not in materials:
                issue("warning", "UNKNOWN_MATERIAL", f"Wall '{w.id}' refers to missing material '{w.material_id}'", path)
        for wi in range(len(wall_lines)):
            for wj in range(wi+1,len(wall_lines)):
                intersection = wall_lines[wi].intersection(wall_lines[wj])
                if intersection.length > 100:
                    issue("error", "DUPLICATE_WALL_PATH", f"Wall centerlines overlap: '{level.walls[wi].id}' and '{level.walls[wj].id}'", prefix)
        if constraints.require_wall_boundary_coverage and wall_lines:
            covered = unary_union(wall_lines).buffer(130)
            for room_id,(room, shape) in rooms.items():
                missing = shape.boundary.difference(covered).length
                if missing > 500:
                    issue("warning", "MISSING_BOUNDARY_WALL", f"'{room.name}' has {missing/1000:.2f} m of unrepresented boundary; verify walls/intentional open-plan zones", prefix)

        openings_per_wall = defaultdict(list)
        graph = defaultdict(set)
        externally_accessed = set()
        exterior_doors = 0
        rooms_with_external_window = set()
        for oi, opening in enumerate(level.openings):
            path = f"{prefix}.openings[{oi}]"
            wall = wall_map.get(opening.host_wall_id)
            if not wall:
                issue("error", "UNKNOWN_HOST_WALL", f"Opening '{opening.id}' references missing wall '{opening.host_wall_id}'", path)
                continue
            length = wall_length(wall)
            if opening.offset_mm + opening.width_mm > length + 0.1:
                issue("error", "OPENING_OUTSIDE_WALL", f"Opening '{opening.id}' exceeds its host wall length {length:.0f} mm", path)
                continue
            if opening.height_mm+opening.sill_mm > wall.height_mm + 1:
                issue("error", "OPENING_ABOVE_WALL", f"Opening '{opening.id}' extends above host wall top", path)
            if opening.offset_mm < 75 or length-opening.offset_mm-opening.width_mm < 75:
                issue("warning", "OPENING_NEAR_CORNER", f"Opening '{opening.id}' has less than 75 mm of wall at an endpoint", path)
            if opening.kind in ("door", "sliding_door") and opening.width_mm < 750:
                issue("warning", "NARROW_DOOR", f"Door '{opening.id}' is only {opening.width_mm:g} mm; verify clear width and accessibility", path)
            if opening.kind in ("window", "vent") and opening.sill_mm == 0:
                issue("warning", "ZERO_WINDOW_SILL", f"Window/vent '{opening.id}' has zero sill elevation", path)
            openings_per_wall[wall.id].append(opening)
            if opening.kind not in PASSABLE and opening.kind not in ("window", "vent"):
                continue
            mid = at_wall(wall, opening.offset_mm+opening.width_mm/2)
            dx = (wall.end.x-wall.start.x)/length
            dy = (wall.end.y-wall.start.y)/length
            probe = max(wall.thickness_mm/2 + 180, 220)
            sides=[]
            for sign in (-1,1):
                test = SPoint(mid[0]-sign*dy*probe, mid[1]+sign*dx*probe)
                candidates=[id for id,(_,area) in rooms.items() if area.covers(test)]
                if len(candidates)>1:
                    issue("warning", "AMBIGUOUS_OPENING_SIDE", f"Opening '{opening.id}' faces multiple overlapping spaces", path)
                sides.append(candidates[0] if candidates else ("OUTSIDE" if not footprints.covers(test) else None))
            if sides[0] == sides[1]:
                issue("warning", "OPENING_NOT_CONNECTING", f"Opening '{opening.id}' does not clearly connect two distinct spaces/sides", path)
            if opening.kind in PASSABLE:
                a,b=sides
                if a and b and a!=b:
                    graph[a].add(b); graph[b].add(a)
                    if "OUTSIDE" in (a,b):
                        exterior_doors += 1
                        externally_accessed.add(b if a=="OUTSIDE" else a)
                else:
                    issue("warning", "UNCLEAR_ACCESS", f"Door/arch '{opening.id}' cannot be assigned to clear adjacent spaces", path)
            elif opening.kind in ("window", "vent") and "OUTSIDE" in sides:
                rooms_with_external_window.update(x for x in sides if x and x != "OUTSIDE")
        for wallid, items in openings_per_wall.items():
            ordered = sorted(items,key=lambda x:x.offset_mm)
            for a,b in zip(ordered,ordered[1:]):
                if a.offset_mm + a.width_mm > b.offset_mm + 1:
                    issue("error", "OVERLAPPING_OPENINGS", f"Openings '{a.id}' and '{b.id}' overlap on wall '{wallid}'",prefix)
        if constraints.require_exterior_entrance and not exterior_doors:
            issue("error", "NO_EXTERIOR_ENTRANCE", "No modeled passable opening connects an interior space to outdoors", prefix)
        reached=set(externally_accessed)
        queue=deque(externally_accessed)
        while queue:
            node=queue.popleft()
            for other in graph[node]:
                if other not in reached:
                    reached.add(other);queue.append(other)
        for id,(r,p) in rooms.items():
            if exterior_doors and id not in reached and r.kind not in EXEMPT_ACCESS:
                issue("warning", "SPACE_UNREACHABLE", f"'{r.name}' is not connected to an exterior entrance through modeled doors/arches", prefix)
            if r.kind in EXTERIOR_WINDOW_RECOMMENDED and id not in rooms_with_external_window:
                issue("warning", "NO_EXTERNAL_WINDOW", f"'{r.name}' has no modeled exterior window/vent; verify daylight and ventilation", prefix)

        geom_objects=[]
        for i,o in enumerate(level.objects):
            path=f"{prefix}.objects[{i}]"
            p=object_polygon(o)
            if not footprints.buffer(20).covers(p):
                issue("warning", "OBJECT_OUTSIDE_FOOTPRINT", f"Object '{o.name}' partially lies beyond footprint; check if intentional",path)
            geom_objects.append((o,p))
            if o.material_id and o.material_id not in materials:
                issue("warning", "UNKNOWN_MATERIAL", f"Object '{o.name}' refers to missing material '{o.material_id}'", path)
        for i,(a,pa) in enumerate(geom_objects):
            for b,pb in geom_objects[i+1:]:
                # Embedded fixtures/appliances on a counter are an intentional assembly.
                if (a.kind == "counter" and b.kind in {"hob","sink"}) or (b.kind == "counter" and a.kind in {"hob","sink"}):
                    continue
                overlap_fraction=pa.intersection(pb).area/min(pa.area,pb.area)
                if overlap_fraction > .2:
                    issue("error" if overlap_fraction>.38 else "warning", "OBJECT_COLLISION", f"Objects '{a.name}' and '{b.name}' overlap significantly", prefix)

        # Catch furniture penetrating actual solid wall thickness, not just centerlines.
        # Wall-hosted openings are subtracted from the solid intervals before testing.
        wall_solids=[]
        for ww in level.walls:
            le=wall_length(ww)
            if le < 50:continue
            intervals=sorted((max(0,op.offset_mm),min(le,op.offset_mm+op.width_mm))
                             for op in openings_per_wall.get(ww.id,[]))
            at=0
            for start,end in [*intervals,(le,le)]:
                if start>at+0.5:
                    wall_solids.append(LineString([at_wall(ww,at),at_wall(ww,start)]).buffer(
                        ww.thickness_mm/2,cap_style=2,join_style=2))
                at=max(at,end)
        wall_union=unary_union(wall_solids) if wall_solids else None
        if wall_union is not None:
            for obj,objpoly in geom_objects:
                if obj.kind in {"light","socket","switch","electrical","column","beam","railing"}:
                    continue  # these can intentionally mount into/wrap a wall
                overlap=objpoly.intersection(wall_union).area
                if overlap>max(8000, objpoly.area*.045):
                    issue("error" if overlap>50000 else "warning","OBJECT_INTERSECTS_WALL",
                          f"'{obj.name}' ({obj.id}) penetrates modeled wall solids by {overlap/1e6:.3f} m²",prefix)

        # Door-leaf clearance is a *planning heuristic*, not an accessibility/code assessment.
        # A quarter-circle sector captures all door positions, not only the leaf drawn open.
        for opening in level.openings:
            if opening.kind != "door" or opening.host_wall_id not in wall_map:
                continue
            wall = wall_map[opening.host_wall_id]
            if opening.offset_mm+opening.width_mm > wall_length(wall):continue
            ax,ay=at_wall(wall,opening.offset_mm)
            bx,by=at_wall(wall,opening.offset_mm+opening.width_mm)
            ux=(bx-ax)/opening.width_mm;uy=(by-ay)/opening.width_mm
            nx,ny=-uy,ux
            if opening.hinge=="end":
                ax,ay=bx,by;ux,uy=-ux,-uy
            side=-1 if opening.swing=="left" else 1
            start_angle=math.atan2(uy,ux)
            end_angle=math.atan2(ny*side,nx*side)
            sweep_delta=math.atan2(math.sin(end_angle-start_angle),math.cos(end_angle-start_angle))
            r=opening.width_mm
            arc=[(ax+r*math.cos(start_angle+sweep_delta*i/22),
                  ay+r*math.sin(start_angle+sweep_delta*i/22)) for i in range(23)]
            sector=Polygon([(ax,ay),*arc]).buffer(0)
            for ob,obshape in geom_objects:
                if sector.intersection(obshape).area > 9000:
                    issue("error" if sector.intersection(obshape).area>25000 else "warning",
                      "DOOR_SWING_OBJECT_CONFLICT",
                      f"Door '{opening.id}' sweep overlaps '{ob.name}' ({ob.id}); check actual door handing and clearance",prefix)

        # Functional completeness: a valid polygon can still be an unusable space.
        # These warnings encourage the AI's bounded design review, rather than inventing code rules.
        for room_id,(room,roomshape) in rooms.items():
            if room.kind not in {"bedroom","kitchen","bathroom","toilet","living"}:continue
            contained={obj.kind for obj,_ in geom_objects if roomshape.covers(SPoint(obj.center.x,obj.center.y))}
            expected={
                "bedroom": ({"bed"},"bed"),
                "kitchen": ({"sink","hob"},"sink and hob"),
                "bathroom": ({"wc","shower","bathtub"},"sanitary fixtures"),
                "toilet": ({"wc"},"WC"),
                "living": ({"sofa","chair"},"seating")}
            required,description=expected[room.kind]
            has_items=required.issubset(contained) if room.kind=="kitchen" else bool(required & contained)
            if not has_items:
                issue("warning","ROOM_FIXTURE_MISSING",
                      f"'{room.name}' has no modeled {description}; verify furnishing/service plan",prefix)

        if li == 0:
            counts = Counter(r.kind for r in level.spaces)
            for need in constraints.room_needs:
                if counts[need.kind] < need.count:
                    issue("error", "ROOM_PROGRAM_COUNT", f"Required {need.count} '{need.kind}' spaces, found {counts[need.kind]}", prefix)
                if need.min_area_m2 is not None:
                    matching = sorted((poly(r.polygon, r.holes).area/1e6 for r in level.spaces if r.kind==need.kind), reverse=True)
                    if len([a for a in matching if a >= need.min_area_m2]) < need.count:
                        issue("error", "ROOM_PROGRAM_AREA", f"Need {need.count} '{need.kind}' spaces of at least {need.min_area_m2:g} m²", prefix)
        summaries.append({"id":level.id, "name": level.name, "gross_area_m2":round(footprints.area/1e6,2),
                          "spaces":len(level.spaces), "walls":len(level.walls), "openings":len(level.openings),
                          "objects":len(level.objects),"room_areas_m2":{r.name:round(poly(r.polygon, r.holes).area/1e6,2) for r in level.spaces}})
    from .functional import audit_functional
    issues.extend(audit_functional(plan, constraints))
    return ValidationReport(valid=not any(i.severity=="error" for i in issues),
                            errors=sum(i.severity=="error" for i in issues),
                            warnings=sum(i.severity=="warning" for i in issues),
                            issues=issues, level_summaries=summaries)
