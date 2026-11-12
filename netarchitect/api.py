"""FastAPI dashboard.

The dashboard is a second view over the same ``analyze()`` result the CLI
uses.  Tabs show the overview, the decision log, the address plan, the tier
diagram, and the per-device configuration.  There is no frontend build step.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from netarchitect.core.design import analyze, safe_analyze
from netarchitect.core.errors import NetArchitectError
from netarchitect.core.spec import PRESET_NAMES, load_preset

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))

app = FastAPI(
    title="NetArchitect",
    description="Explainable network planning and Cisco IOS configuration engine",
    version="1.0.0",
)


def _diagram(plan) -> dict[str, object]:
    access = plan.topology.access_switches
    shown = min(access, 8)
    return {
        "tier": plan.topology.tier,
        "core": plan.topology.core_switches,
        "distribution": plan.topology.distribution_switches,
        "access_shown": shown,
        "access_more": max(0, access - shown),
        "access_total": access,
    }


def _scenario_for(preset: str, distance_m, endpoints, buildings, resilient):
    scenario = load_preset(preset)
    return scenario.with_overrides(
        distance_m=distance_m,
        endpoints=endpoints,
        buildings=buildings,
        resilient=resilient,
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    preset: str = Query("campus", description="campus, metro, or wan"),
    distance_m: float | None = Query(None, ge=0.001),
    endpoints: int | None = Query(None, ge=1),
    buildings: int | None = Query(None, ge=1),
    resilient: bool | None = Query(None),
    tab: str = Query("overview"),
):
    context: dict[str, object] = {
        "presets": PRESET_NAMES,
        "preset": preset if preset in PRESET_NAMES else "campus",
        "tab": tab,
        "distance_m": distance_m,
        "endpoints": endpoints,
        "buildings": buildings,
        "resilient": resilient,
        "error": None,
        "analysis": None,
        "scenario": None,
        "diagram": None,
        "configs_json": "{}",
        "device_names": [],
    }
    try:
        scenario = _scenario_for(
            context["preset"], distance_m, endpoints, buildings, resilient
        )
        analysis = analyze(scenario)
    except NetArchitectError as exc:
        context["error"] = str(exc)
        return templates.TemplateResponse(request=request, name="dashboard.html", context=context)
    except ValueError as exc:
        context["error"] = str(exc)
        return templates.TemplateResponse(request=request, name="dashboard.html", context=context)

    context.update(
        {
            "analysis": analysis,
            "scenario": scenario,
            "diagram": _diagram(analysis.selected),
            "configs_json": json.dumps(analysis.device_configs),
            "device_names": sorted(analysis.device_configs),
        }
    )
    return templates.TemplateResponse(request=request, name="dashboard.html", context=context)


@app.get("/api/design")
def design_api(
    preset: str = Query("campus"),
    distance_m: float | None = Query(None, ge=0.001),
    endpoints: int | None = Query(None, ge=1),
    buildings: int | None = Query(None, ge=1),
    resilient: bool | None = Query(None),
    include_configs: bool = Query(False),
):
    """JSON view for scripts and for the report generator."""
    try:
        scenario = _scenario_for(preset, distance_m, endpoints, buildings, resilient)
        analysis = analyze(scenario)
    except NetArchitectError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return JSONResponse(analysis.to_dict(include_configs=include_configs))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
