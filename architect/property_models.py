"""V4 property-scale contract. Old V3 level geometry remains the single CAD source."""
from __future__ import annotations
from typing import Literal
from pydantic import Field, model_validator
from .models import StrictModel, Point, FloorPlan, Size

Feature = Literal['auto','required','forbidden']
Typology = Literal['villa','apartment','duplex','mixed_use']

class PropertyRequest(StrictModel):
    property_type: Typology = 'villa'
    plot_width_mm: int = Field(default=23500, ge=12000, le=120000)
    plot_depth_mm: int = Field(default=24500, ge=12500, le=120000)
    floors: int = Field(default=1, ge=1, le=6)
    units_per_floor: int = Field(default=1, ge=1, le=4)
    bedrooms_per_unit: int = Field(default=2, ge=1, le=4)
    layout_strategy: Literal['auto','linear','opposed','wing','irregular'] = 'auto'
    stairs: Feature = 'auto'
    lift: Feature = 'auto'
    garage: Feature = 'auto'
    lawn: Feature = 'auto'
    shaft: Feature = 'auto'
    parking_spaces: int = Field(default=0, ge=0, le=12)
    accessibility_priority: bool = False
    seed: int = Field(default=42, ge=0, le=1000000)
    alternatives: int = Field(default=3, ge=1, le=5)
    # This is an indicative design preference, NOT a legal setback rule.
    concept_margin_mm: int = Field(default=800, ge=0, le=5000)

    @model_validator(mode='after')
    def check_scope(self):
        if self.property_type in ('villa','duplex') and self.units_per_floor!=1:
            raise ValueError('Villas/duplexes have one private residence per level; use apartment for multiple homes')
        if self.property_type=='duplex' and self.floors<2:
            raise ValueError('Duplex needs at least two levels')
        if self.floors>1 and self.stairs=='forbidden':
            raise ValueError('Multiple occupied floors cannot be generated with stairs forbidden (no alternate vertical egress modeled)')
        if self.property_type=='mixed_use' and self.floors<2:
            raise ValueError('Mixed-use example requires commercial ground floor and residential levels above')
        return self

class FeatureDecision(StrictModel):
    name: str
    requested: Feature
    included: bool
    reason: str

class ParcelSite(StrictModel):
    id: str = 'site'
    name: str = 'Concept property'
    boundary: list[Point] = Field(min_length=3)
    road_edge: Literal['south'] = 'south'
    north_degrees_clockwise_from_page_up: float = 0
    assumptions: list[str] = Field(default_factory=list)

class SiteArea(StrictModel):
    id: str
    kind: Literal['lawn','driveway','parking_bay','walkway','garden','tree','gate','setback','courtyard','other']
    label: str
    polygon: list[Point] = Field(min_length=3)
    material_id: str | None = None
    attributes: dict[str,str|int|float|bool] = Field(default_factory=dict)

class UnitRecord(StrictModel):
    id: str
    name: str
    level_id: str
    kind: Literal['residence','retail','office'] = 'residence'
    space_ids: list[str] = Field(min_length=1)
    entrance_opening_id: str
    dwelling_id: str | None = None  # joins one duplex/villa residence across levels

class PropertyBuilding(StrictModel):
    id: str
    name: str
    site_origin: Point
    plan: FloorPlan
    units: list[UnitRecord] = Field(default_factory=list)
    common_space_ids: dict[str,list[str]] = Field(default_factory=dict)
    summary: str = ''

class PropertyProject(StrictModel):
    schema_version: Literal['2.0.0'] = '2.0.0'
    request: PropertyRequest
    site: ParcelSite
    site_areas: list[SiteArea] = Field(default_factory=list)
    buildings: list[PropertyBuilding] = Field(min_length=1)
    feature_decisions: list[FeatureDecision]
    heuristic_score: float = 0
    design_notes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

class PropertyIssue(StrictModel):
    severity: Literal['error','warning','info']
    code: str
    message: str
    path: str = ''

class PropertyReport(StrictModel):
    valid: bool
    errors: int
    warnings: int
    issues: list[PropertyIssue]
    base_reports: dict[str,dict]
    metrics: dict[str,float|int|str]
