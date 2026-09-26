"""
SafeRoute AI — Backend (FastAPI)
Module 2: Route Generation via OSRM.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import get_settings
from app.api.routing import router as routing_router
from app.api.traffic import router as traffic_router
from app.api.incidents import router as incidents_router
from app.api.weather import router as weather_router
from app.api.features import router as features_router
from app.api.live_snapshot import router as live_snapshot_router
from app.api.ai_assistant import router as ai_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)

settings = get_settings()

app = FastAPI(
    title="SafeRoute AI API",
    description="Safety-focused navigation backend for Bengaluru, India.",
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(routing_router)
app.include_router(traffic_router)
app.include_router(incidents_router)
app.include_router(weather_router)
app.include_router(features_router)
app.include_router(live_snapshot_router)
app.include_router(ai_router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
async def health_check():
    from app.risk_engine import get_risk_engine
    from app.services.llm_service import get_llm_service
    try:
        engine = get_risk_engine()
        risk_engine_status = "active" if engine.is_ready else "model_not_loaded"
    except Exception as e:
        risk_engine_status = f"error: {e}"

    llm_service = get_llm_service()
    llm_status = f"active ({llm_service.model_name})" if llm_service.is_available else "fallback_mode"

    return {
        "status": "ok",
        "modules": "1-8 + AI Assistant (Location, Routing, Traffic, Incidents, Weather, Historical Accidents, Feature Engineering, Live Snapshot, Risk Engine, AI Safety Assistant)",
        "routing_provider": "tomtom",
        "module7": "active",
        "module8_risk_engine": risk_engine_status,
        "ai_safety_assistant": llm_status,
        "snapshot_system": "active",
        "storage": "supabase",
    }
