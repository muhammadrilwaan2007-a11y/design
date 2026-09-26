"""
backend/app/schemas/ai.py
=========================
Pydantic schemas for the LLM-powered AI Safety Assistant (Groq / GPT-OSS 120B).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ShapFactorSummary(BaseModel):
    """Summarized SHAP factor for UI display."""
    feature: str = Field(..., description="Feature display label (e.g. 'Road type')")
    raw_feature: Optional[str] = Field(default=None, description="Underlying model feature name")
    direction: str = Field(..., description="'higher_risk' | 'lower_risk' | 'neutral'")
    shap_value: float = Field(..., description="SHAP value in model log-odds space")
    statement: str = Field(..., description="Human-readable non-percentage explanation statement")


class LiveConditionsSummary(BaseModel):
    """Summary of live road conditions separate from historical score."""
    traffic: str = Field(default="Normal flowing traffic", description="Traffic condition summary")
    incidents: List[Dict[str, Any]] = Field(default_factory=list, description="Active incidents or closures near section")
    weather: Dict[str, Any] = Field(default_factory=dict, description="Live weather condition")


class ExplainSectionRequest(BaseModel):
    """
    Request body for POST /api/ai/explain-section.
    Backend gathers the authoritative data itself using osm_edge_id or segment_id.
    """
    osm_edge_id: Optional[int] = Field(default=None, description="Unique OSM road edge ID")
    segment_id: Optional[str] = Field(default=None, description="UI segment ID (e.g. route_1_seg_002)")
    route_id: Optional[str] = Field(default=None, description="Route identifier")
    segment_coords: Optional[List[List[float]]] = Field(default=None, description="Coordinates [[lon, lat], ...] of segment if resolving on demand")
    question: Optional[str] = Field(default=None, description="Optional user question about this section")


class ExplainSectionResponse(BaseModel):
    """
    Response body for POST /api/ai/explain-section.
    Safety Score and SHAP values come directly from backend models.
    """
    answer: str = Field(..., description="Natural-language explanation from GPT-OSS 120B")
    safety_score: Optional[int] = Field(None, description="Authoritative historical Safety Score [0, 100]")
    calibrated_historical_risk: Optional[float] = Field(None, description="Bayes-calibrated historical risk probability")
    raw_risk_prob: Optional[float] = Field(None, description="Raw XGBoost risk probability")
    road_type: Optional[str] = Field(None, description="Road functional classification")
    top_factors: List[ShapFactorSummary] = Field(default_factory=list, description="Top SHAP model factors")
    live_conditions: LiveConditionsSummary = Field(default_factory=LiveConditionsSummary, description="Live conditions (traffic/incidents/weather)")
    osm_edge_id: Optional[int] = Field(None, description="Matched OSM edge ID")
    status: str = Field(default="ok", description="'ok' | 'fallback'")


class ExplainRouteRequest(BaseModel):
    """Request body for POST /api/ai/explain-route."""
    route_id: str = Field(..., description="Route identifier (e.g. 'route_1')")
    distance_km: Optional[float] = Field(default=None, description="Distance in km")
    duration_minutes: Optional[float] = Field(default=None, description="Duration in minutes")
    safety_score: Optional[int] = Field(default=None, description="Route safety score if already calculated")
    calibrated_historical_risk: Optional[float] = Field(default=None, description="Route calibrated risk probability")
    alternative_routes: Optional[List[Dict[str, Any]]] = Field(default=None, description="Other candidate routes for comparison")
    question: Optional[str] = Field(default=None, description="Optional user question about the route")


class ExplainRouteResponse(BaseModel):
    """Response body for POST /api/ai/explain-route."""
    answer: str = Field(..., description="Natural-language route summary from GPT-OSS 120B")
    route_id: str = Field(..., description="Route identifier")
    safety_score: Optional[int] = Field(None, description="Route historical Safety Score")
    calibrated_historical_risk: Optional[float] = Field(None, description="Route calibrated risk probability")
    top_factors: List[ShapFactorSummary] = Field(default_factory=list, description="Dominant model factors along route")
    live_conditions: LiveConditionsSummary = Field(default_factory=LiveConditionsSummary, description="Live route conditions")
    notable_segments: List[Dict[str, Any]] = Field(default_factory=list, description="Notable high-risk sections")
    status: str = Field(default="ok", description="'ok' | 'fallback'")


class AskQuestionRequest(BaseModel):
    """Request body for POST /api/ai/ask."""
    question: str = Field(..., description="User's query about the route or section")
    osm_edge_id: Optional[int] = Field(default=None, description="Optional edge context")
    segment_id: Optional[str] = Field(default=None, description="Optional segment context")
    route_id: Optional[str] = Field(default=None, description="Optional route context")
    alternative_routes: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional alternative candidate routes")


class AskQuestionResponse(BaseModel):
    """Response body for POST /api/ai/ask."""
    answer: str = Field(..., description="Answer grounded strictly in SafeRoute evidence")
    safety_score: Optional[int] = Field(None, description="Referenced Safety Score")
    status: str = Field(default="ok", description="'ok' | 'fallback'")
