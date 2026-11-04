"""The canonical, forward-compatible 2D/3D architectural data contract."""
from __future__ import annotations
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import math

MM = Annotated[float, Field(ge=-2_000_000, le=2_000_000, allow_inf_nan=False)]
Size = Annotated[float, Field(gt=0, le=2_000_000, allow_inf_nan=False)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

class Point(StrictModel):
    x: MM
    y: MM

class ProjectInfo(StrictModel):
    name: str = Field(min_length=1, max_length=140)
    description: str = Field(default="", max_length=2000)
    location: str = Field(default="", max_length=200)
    building_use: str = Field(default="residential", max_length=60)
    design_stage: Literal["concept", "schematic", "design_development"] = "concept"
    author: str = Field(default="AI-assisted concept", max_length=120)
    revision: str = Field(default="A", max_length=30)
    north_degrees_clockwise_from_page_up: float = Field(default=0, ge=-360, le=360)

class Material(StrictModel):
    id: str = Field(min_length=1, max_length=72)
    name: str = Field(min_length=1, max_length=120)
    category: Literal["wall", "floor", "ceiling", "glass", "metal", "wood", "finish", "other"] = "other"
    color_hex: str = Field(default="#c4c4c4", pattern=r"^#[0-9A-Fa-f]{6}$")
    texture_uri: str | None = Field(default=None, max_length=512)
    properties: dict[str, str | int | float | bool] = Field(default_factory=dict)

class Space(StrictModel):
    id: str = Field(min_length=1, max_length=72)
    name: str = Field(min_length=1, max_length=90)
    kind: Literal["living", "bedroom", "kitchen", "bathroom", "toilet", "dining", "hall", "corridor", "entry", "utility", "storage", "balcony", "stairwell", "lift_lobby", "shaft", "garage", "office", "study", "terrace", "other"]
    polygon: list[Point] = Field(min_length=3, max_length=120)
    holes: list[list[Point]] = Field(default_factory=list, max_length=15)
    floor_material_id: str | None = None
    wall_finish_id: str | None = None
    ceiling_material_id: str | None = None
    ceiling_height_mm: Size | None = None
    occupancy: int | None = Field(default=None, ge=0, le=10000)
    is_habitable: bool = True
    tags: list[str] = Field(default_factory=list, max_length=20)

class Wall(StrictModel):
    id: str = Field(min_length=1, max_length=72)
    start: Point
    end: Point
    thickness_mm: float = Field(ge=50, le=1000)
    height_mm: float = Field(default=3000, ge=300, le=20000)
    kind: Literal["exterior", "interior", "partition", "parapet", "existing"] = "interior"
    structural: bool = False
    material_id: str | None = None
    base_z_mm: MM = 0
    fire_rating_min: int | None = Field(default=None, ge=0, le=600)

class Opening(StrictModel):
    id: str = Field(min_length=1, max_length=72)
    host_wall_id: str
    kind: Literal["door", "sliding_door", "window", "arch", "opening", "vent"]
    offset_mm: float = Field(ge=0, le=2_000_000)
    width_mm: Size
    height_mm: Size = 2100
    sill_mm: float = Field(default=0, ge=0, le=20000)
    hinge: Literal["start", "end", "none"] = "start"
    swing: Literal["left", "right", "none"] = "left"
    frame_material_id: str | None = None
    glazing_material_id: str | None = None
    fire_rating_min: int | None = Field(default=None, ge=0, le=600)
    accessible: bool | None = None

class PlacedObject(StrictModel):
    id: str = Field(min_length=1, max_length=72)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["bed", "sofa", "table", "desk", "chair", "counter", "cabinet", "wardrobe", "sink", "wc", "shower", "bathtub", "hob", "fridge", "washing_machine", "doorbell", "electrical", "light", "switch", "socket", "plumbing", "floor_drain", "stair", "elevator", "column", "beam", "shaft", "railing", "appliance", "furniture", "fixture", "other"]
    center: Point
    width_mm: Size
    depth_mm: Size
    height_mm: Size
    rotation_degrees: float = Field(default=0, ge=-360, le=360)
    base_z_mm: MM = 0
    material_id: str | None = None
    asset_uri: str | None = Field(default=None, max_length=512)
    texture_uri: str | None = Field(default=None, max_length=512)
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)
    # A placement assertion is distinct from geometry. AI must explicitly state intent.
    space_id: str | None = None
    placement: Literal["freestanding", "wall_anchored", "built_in", "fixture"] = "freestanding"
    # Local -Y = back/headboard; local +Y = front/access side.
    front_clearance_mm: float | None = Field(default=None, ge=0, le=3000)

class BuiltElement(StrictModel):
    """Solid column/pier or dedicated service/atrium void, with arbitrary footprint."""
    id: str = Field(min_length=1, max_length=72)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["column", "pier", "shaft", "duct", "lightwell", "atrium", "void"]
    polygon: list[Point] = Field(min_length=3, max_length=120)
    base_z_mm: MM = 0
    height_mm: Size = 3000
    material_id: str | None = None
    load_bearing_assumed: bool = False
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)

class VerticalConnector(StrictModel):
    """Concept representation: does not certify stair/lift safety or engineering."""
    id: str = Field(min_length=1, max_length=72)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["stair", "lift", "ramp", "escalator"]
    polygon: list[Point] = Field(min_length=3, max_length=100)
    serves_level_ids: list[str] = Field(min_length=1, max_length=15)
    orientation_degrees: float = Field(default=0, ge=-360, le=360)
    step_count: int | None = Field(default=None, ge=1, le=300)
    rise_mm: float | None = Field(default=None, gt=0, le=1000)
    going_mm: float | None = Field(default=None, gt=0, le=2000)
    landings: list[list[Point]] = Field(default_factory=list, max_length=30)
    cabin_width_mm: float | None = Field(default=None, gt=0, le=10000)
    cabin_depth_mm: float | None = Field(default=None, gt=0, le=10000)
    door_opening_id: str | None = None
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)

class Annotation(StrictModel):
    id: str
    text: str = Field(min_length=1, max_length=800)
    at: Point
    rotation_degrees: float = 0
    layer: Literal["notes", "structure", "mep", "furniture", "other"] = "notes"

class Dimension(StrictModel):
    id: str
    start: Point
    end: Point
    offset_mm: float = Field(default=350, ge=-10000, le=10000)
    text_override: str | None = Field(default=None, max_length=50)

class Level(StrictModel):
    id: str = Field(min_length=1, max_length=72)
    name: str = Field(min_length=1, max_length=80)
    elevation_mm: MM = 0
    default_clear_height_mm: Size = 3000
    slab_thickness_mm: Size = 150
    footprint: list[Point] = Field(min_length=3, max_length=120)
    footprint_holes: list[list[Point]] = Field(default_factory=list, max_length=20)
    spaces: list[Space] = Field(min_length=1, max_length=180)
    walls: list[Wall] = Field(min_length=1, max_length=500)
    openings: list[Opening] = Field(default_factory=list, max_length=450)
    objects: list[PlacedObject] = Field(default_factory=list, max_length=600)
    built_elements: list[BuiltElement] = Field(default_factory=list, max_length=350)
    vertical_connectors: list[VerticalConnector] = Field(default_factory=list, max_length=80)
    annotations: list[Annotation] = Field(default_factory=list, max_length=300)
    dimensions: list[Dimension] = Field(default_factory=list, max_length=350)

class FloorPlan(StrictModel):
    schema_version: Literal["1.0.0", "1.1.0"] = "1.1.0"
    unit: Literal["mm"] = "mm"
    origin: Literal["top_left"] = "top_left"
    x_positive: Literal["right"] = "right"
    y_positive: Literal["down"] = "down"
    project: ProjectInfo
    materials: list[Material] = Field(default_factory=list, max_length=200)
    levels: list[Level] = Field(min_length=1, max_length=15)
    assumptions: list[str] = Field(default_factory=list, max_length=40)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=40)

class RoomNeed(StrictModel):
    kind: str
    count: int = Field(ge=0, le=100)
    min_area_m2: float | None = Field(default=None, gt=0, le=5000)

class DesignConstraints(StrictModel):
    envelope_width_mm: float | None = Field(default=None, gt=1000, le=200000)
    envelope_depth_mm: float | None = Field(default=None, gt=1000, le=200000)
    room_needs: list[RoomNeed] = Field(default_factory=list, max_length=30)
    require_exterior_entrance: bool = True
    require_wall_boundary_coverage: bool = True
    notes: str = Field(default="", max_length=3000)
    # Physical planning targets are configurable, NOT jurisdictional code limits.
    quality_profile: Literal["residential", "office", "general", "unfurnished"] = "residential"
    require_bed_headwall: bool = True
    enforce_furniture_clearances: bool = True
    min_practical_clear_path_mm: float = Field(default=550, ge=300, le=1500)

class Issue(StrictModel):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    path: str = ""

class ValidationReport(StrictModel):
    valid: bool
    errors: int
    warnings: int
    issues: list[Issue]
    level_summaries: list[dict[str, Any]] = Field(default_factory=list)

