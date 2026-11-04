"""Gemini architect -> deterministic critic -> bounded repair -> optional design reviewer.

Requires an explicitly configured API key; no call is made when one is absent.
"""
from __future__ import annotations
import json, os
from pathlib import Path
from pydantic import ValidationError
from .models import FloorPlan, DesignConstraints
from .validate import validate_plan
from .procedural import suggest_bedroom_repair

ROOT = Path(__file__).resolve().parents[1]

class AIConfigurationError(Exception): pass
class AIUpstreamError(Exception): pass


def _schema_for_gemini(obj):
    # Google's JSON Schema subset does not accept all Pydantic validation keywords.
    allowed = {"$defs","$ref","type","properties","items","required","additionalProperties",
               "anyOf","enum","minimum","maximum","minItems","maxItems","description","title","format"}
    def walk(x):
        if isinstance(x,list):return [walk(a) for a in x]
        if isinstance(x,dict):
            # Dictionary entries under 'properties' and '$defs' represent user field names, not schema keys.
            def asmap(k,v):
                if k in ("properties","$defs") and isinstance(v,dict): return {name:walk(sch) for name,sch in v.items()}
                return walk(v)
            return {k:asmap(k,v) for k,v in x.items() if k in allowed}
        return x
    return walk(obj)


FLOORPLAN_SCHEMA = _schema_for_gemini(FloorPlan.model_json_schema())
REVIEW_SCHEMA = {"type":"object","properties":{
    "needs_revision":{"type":"boolean"},
    "critical_findings":{"type":"array","items":{"type":"string"},"maxItems":8},
    "improvements":{"type":"array","items":{"type":"string"},"maxItems":8},
    "positive_features":{"type":"array","items":{"type":"string"},"maxItems":8}},
    "required":["needs_revision","critical_findings","improvements","positive_features"],
    "additionalProperties":False}


def _ask(client, model, prompt, schema, temperature):
    from google.genai import types
    try:
        res=client.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=schema,
                                               temperature=temperature, max_output_tokens=24000))
    except Exception as exc:
        # Do not expose API keys, auth headers, or raw provider error bodies to clients.
        raise AIUpstreamError(f"Provider request failed ({type(exc).__name__}). Check model, quota, credentials, and connectivity.") from exc
    if not res.text:
        raise AIUpstreamError("Provider returned an empty response (possibly a token/safety limit).")
    try:
        return json.loads(res.text)
    except ValueError as exc:
        raise AIUpstreamError("Provider returned non-JSON text despite structured-output request") from exc


def generate_plan(brief: str, constraints: DesignConstraints, *, model: str | None=None,
                  max_revisions:int=2, perform_design_review:bool=True):
    api_key=os.getenv("GEMINI_API_KEY")
    if not api_key: raise AIConfigurationError("GEMINI_API_KEY is missing. Set it in your environment to enable AI generation; demo and manual editing work without it.")
    from google import genai
    client=genai.Client(api_key=api_key)
    model=model or os.getenv("GEMINI_MODEL","gemini-2.5-flash")
    blueprint=(ROOT/"ARCHITECTURE_BLUEPRINT.md").read_text(encoding="utf-8")
    constraints_json=constraints.model_dump_json(indent=2)
    instruction=(f"You are a multidisciplinary ARCHITECTURAL SPACE PLANNER producing a technical concept model, not a sketch.\n"
       "Follow the normative model contract below. Use exact millimetres and carefully calculate every coordinate.\n"
       "Never label construction/code compliance as established. Never invent site regulations.\n"
       "Include every required room type, a usable circulation route, exterior entrance, and plausible daylight, privacy, furniture, doors and sanitary fixtures.\n"
       "Plan arbitrary concave polygons and inner holes as actual polygon boundaries. Model each column, pier, shaft, duct, lift and stair as an EXPLICIT independently typed entity, never as invisible prose.\n"
       "Use 1.1.0 output schema fields. Keep levels and vertical connector references consistent. Stair flights must reach the next floor level by step_count × rise_mm.\n"
       "Bed HEADBOARD must be geometrically aligned within 260mm of a solid room wall, with usable side and foot access. Never center a bed free-floating without a design-specific exception approved by the user.\n"
       "Storage MUST NOT block door threshold approaches, full door-swing sectors, windows at the vertical height of furniture, or circulation.\n"
       "For each wardrobe/desk/fridge/WC, leave realistic space directly in FRONT of its operating side and model 'front' as local +Y.\n"
       "Do not open a staircase door onto a flight of treads: provide an actual landing. Do not put furniture inside a shaft/lift footprint.\n"
       "If constraints cannot fit on the plot, preserve honest unresolved questions and report limitations instead of squeezing through geometry.\n"
       "Plan shared walls as one wall ID per continuous straight path; no duplicate centerlines.\n"
       "Every room polygon edge should lie on a wall or be intentionally open to an adjacent room.\n"
       "Create detailed, typed furniture objects, not generic rectangles: each bedroom should have a bed and storage, kitchens have sinks and hobs, toilets have WC and wash basin.\n"
       "Check wall penetrations and the COMPLETE 90-degree door-sweep envelope against all furniture before returning JSON.\n"
       "Avoid implausible crossings, false exterior windows, overlapping chair/table geometry and inaccessible wet areas.\n"
       "Model sensible doors/windows with offsets from WALL START, never an arbitrary global offset.\n"
       "Exterior walls should track the outer footprint boundary by centerline; internal walls track space boundaries.\n"
       "Include realistic dimensions and enough typed objects and heights for later 3D modeling.\n"
       "For design quality, distinguish usable room areas, avoid overlapping objects, provide adequate practical circulation, daylight, plumbing adjacency and privacy.\n"
       "All IDs must be globally unique within each level. Express missing information in assumptions/unresolved_questions.\n"
       "Obey this exact data contract:\n" + blueprint +
       "\nUser's requirements (source of truth):\n" + brief +
       "\nNon-negotiable structured constraints:\n" + constraints_json +
       "\nRETURN ONLY THE SCHEMA-DEFINED JSON MODEL.")
    previous=None; problems=[]; last_plan=None; last_report=None; last_schema_errors=[]; attempts=[]
    quality_codes={"ROOM_FIXTURE_MISSING","DOOR_SWING_OBJECT_CONFLICT","OBJECT_INTERSECTS_WALL",
                   "OBJECT_COLLISION","SPACE_UNREACHABLE","NO_EXTERNAL_WINDOW",
                   "BED_SINGLE_SIDE_ACCESS","NARROW_PORTAL_REGION","WARDROBE_NOT_WALL_ANCHORED"}
    best_valid=None  # preserve the best usable candidate if a later repair goes backwards
    def quality_count(report):
        return sum(i.severity=="warning" and i.code in quality_codes for i in report.issues)
    # Strict, bounded error-driven repair: no invalid geometry is silently changed by renderer.
    for round_no in range(max_revisions+1):
        if round_no==0:
            prompt=instruction
        else:
            prompt=(instruction + "\nREPAIR THE LAST MODEL without losing design intent. This is a new complete replacement, not a patch.\n"
                    + "PREVIOUS MODEL:\n" + json.dumps(previous,ensure_ascii=False)[:95000]
                    + "\nVALIDATION FINDINGS TO FIX:\n"+json.dumps(problems,ensure_ascii=False)[:14000])
        response=_ask(client,model,prompt,FLOORPLAN_SCHEMA,temperature=0.35 if round_no==0 else 0.15)
        previous=response
        try:
            candidate=FloorPlan.model_validate(response)
            report=validate_plan(candidate,constraints)
            # Deterministic furniture improvement is a separate transparent proposal,
            # never a magic auto-fix of walls/doors or a claim of compliance.
            bedroom_codes={'BED_NO_HEADWALL','BED_NO_SIDE_ACCESS','BED_FOOT_ACCESS_BLOCKED',
                           'DOOR_APPROACH_BLOCKED','FURNITURE_BLOCKS_WINDOW'}
            if not report.valid and any(i.code in bedroom_codes for i in report.issues):
                suggested=suggest_bedroom_repair(candidate,seed=round_no+17)
                adjusted=suggested['plan']
                adjusted_report=validate_plan(adjusted,constraints)
                if (adjusted_report.errors,adjusted_report.warnings)<(report.errors,report.warnings):
                    candidate,report=adjusted,adjusted_report
                    attempts.append({'round':round_no+1,'stage':'deterministic-bedroom-repair',
                                     'changes':suggested['changes'],
                                     'errors':report.errors,'warnings':report.warnings})
            last_plan=candidate;last_report=report
            problems=[{"severity":i.severity,"code":i.code,"message":i.message,"path":i.path} for i in report.issues
                      if i.severity=="error" or (i.severity=="warning" and i.code in quality_codes)]
            attempts.append({"round":round_no+1,"schema_valid":True,"errors":report.errors,"warnings":report.warnings,
                             "functional_warnings":quality_count(report)})
            if report.valid:
                if best_valid is None or (quality_count(report),report.warnings)<(quality_count(best_valid[1]),best_valid[1].warnings):
                    best_valid=(candidate,report)
                if quality_count(report)==0:break
        except ValidationError as exc:
            problems=[{"path":"/".join(map(str,e.get("loc",()))), "code":e.get("type"),"message":str(e.get("msg"))} for e in exc.errors()[:35]]
            last_schema_errors=problems
            attempts.append({"round":round_no+1,"schema_valid":False,"errors":len(exc.errors())})

    if best_valid and (last_report is None or not last_report.valid or
                       (quality_count(best_valid[1]),best_valid[1].warnings)<(quality_count(last_report),last_report.warnings)):
        last_plan,last_report=best_valid
        attempts.append({"round":"fallback-best-valid","accepted":True,
                         "errors":last_report.errors,"warnings":last_report.warnings})

    design_review=None
    if last_plan and last_report and last_report.valid and perform_design_review:
        def critique(plan):
            review_prompt=("You are a SECOND independent architectural concept design reviewer. Point out only tangible "
              "functional/architectural problems in the ACTUAL coordinates, rooms, access graph and furniture locations. "
              "Check privacy, daylight, sanitary/plumbing arrangements, space efficiency, practicality, furniture fit, "
              "door swings, access routes, wet-area adjacency and unrealistic assumptions. "
              "Never invent regulations or assert legal/structural compliance. "
              "Mark needs_revision true only when a material fix is advisable. Return concise JSON findings.\n"
              "USER BRIEF:\n"+brief+"\nDETERMINISTIC CHECKS:\n"+last_report.model_dump_json()+
              "\nDESIGN:\n"+plan.model_dump_json())
            return _ask(client,model,review_prompt,REVIEW_SCHEMA,temperature=0.1)
        try:
            design_review=critique(last_plan)
            # Optional 'review -> improve -> revalidate' loop. An AI critic's
            # subjective judgement never overrides the deterministic validator.
            if design_review.get("needs_revision") and design_review.get("critical_findings"):
                existing=last_plan.model_dump(mode="json")
                quality_prompt=(instruction+
                    "\nINDEPENDENT DESIGN REVIEW FOUND THESE CONCRETE PROBLEMS. IMPROVE THE DESIGN WHILE KEEPING THE "
                    "USER'S ORIGINAL REQUIREMENTS, ALL MACHINE CONSTRAINTS AND EVERY GEOMETRIC INVARIANT. "
                    "Return one COMPLETE replacement JSON plan, not a patch.\n"
                    "PRIOR VALID PLAN:\n"+json.dumps(existing,ensure_ascii=False)[:95000]+
                    "\nDESIGN CRITIQUE:\n"+json.dumps(design_review,ensure_ascii=False)[:14000])
                improved_raw=_ask(client,model,quality_prompt,FLOORPLAN_SCHEMA,temperature=0.15)
                try:
                    improved=FloorPlan.model_validate(improved_raw)
                    improved_report=validate_plan(improved,constraints)
                    if improved_report.valid and quality_count(improved_report)<=quality_count(last_report) and improved_report.warnings<=last_report.warnings+1:
                        last_plan,last_report=improved,improved_report
                        attempts.append({"round":"design-improvement","schema_valid":True,
                                         "errors":improved_report.errors,"warnings":improved_report.warnings,"accepted":True})
                        # Review the accepted revision, rather than showing stale critique.
                        try:design_review=critique(last_plan)
                        except AIUpstreamError:
                            design_review={"needs_revision":None,"critical_findings":[],
                                "improvements":["Revision accepted, but final re-review was unavailable."],
                                "positive_features":[]}
                    else:
                        attempts.append({"round":"design-improvement","schema_valid":True,
                                         "errors":improved_report.errors,"warnings":improved_report.warnings,"accepted":False})
                        design_review["improvements"].append("A proposed revision did not pass geometric checks; original valid design retained.")
                except ValidationError:
                    attempts.append({"round":"design-improvement","schema_valid":False,"accepted":False})
                    design_review["improvements"].append("Proposed revision did not satisfy data schema; original valid design retained.")
        except AIUpstreamError as exc:
            design_review={"needs_revision":None,"critical_findings":["AI review unavailable: "+str(exc)],
                           "improvements":[],"positive_features":[]}
    return {"plan":last_plan.model_dump(mode="json") if last_plan else None,
            "report":last_report.model_dump(mode="json") if last_report else None,
            "attempts":attempts,"schema_errors":last_schema_errors if not last_plan else [],
            "quality_review":design_review,
            "status":"valid" if last_report and last_report.valid else "invalid"}
