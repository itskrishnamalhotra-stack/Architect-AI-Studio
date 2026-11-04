"""Optional AI interpreter for plain-language property briefs, followed by deterministic planning.

AI chooses requirements/typology, never unvalidated construction coordinates in V4.
"""
from __future__ import annotations
import os
from .ai import AIConfigurationError,AIUpstreamError,_schema_for_gemini,_ask
from .property_models import PropertyRequest
from pydantic import ValidationError


def brief_to_request(brief:str,*,model:str|None=None):
    if not os.getenv('GEMINI_API_KEY'):
        raise AIConfigurationError('GEMINI_API_KEY is not set; use the offline property form or provide a server-side key')
    from google import genai
    default=PropertyRequest().model_dump_json(indent=2)
    prompt='''You are a property architecture programming assistant. You translate a brief into structured
property design parameters, not drawn plans. Correctly distinguish private homes, flats per floor,
indoor common lobby, garage, lawn, parking bays, lift, stair, shafts and building-level floors.
Never invent legal regulations, compliance, structural sizes or user wishes.
Use "required" for a feature only if explicitly asked; "forbidden" only if prohibited; otherwise "auto".
Where plot dimensions, floor count, or numbers of units/bedrooms are missing, choose documented
reasonable software defaults and report assumptions separately to user. Do NOT invent survey data.
Never set stairs forbidden in a multi-floor project. Lift is optional unless explicitly requested.
Interpret storeys and total units separately from units per floor.
Return ONLY a valid PropertyRequest JSON object. Defaults for missing fields:\n'''+default+'\nUSER BRIEF:\n'+brief
    obj=_ask(genai.Client(api_key=os.environ['GEMINI_API_KEY']),
         model or os.getenv('GEMINI_MODEL','gemini-2.5-flash'),prompt,
         _schema_for_gemini(PropertyRequest.model_json_schema()),temperature=.15)
    try:return PropertyRequest.model_validate(obj)
    except ValidationError as exc:
        raise AIUpstreamError('AI brief produced inconsistent property requirements: '+str(exc.errors()[0]['msg'])) from exc
