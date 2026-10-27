/**
 * frontend/src/services/aiApi.js
 * ===============================
 * API client for the RouteGuard AI Safety Assistant (FastAPI backend).
 * Calls the backend /api/ai endpoints.
 *
 * CRITICAL SECURITY RULE:
 * The Groq API key is NEVER stored or referenced here.
 * All calls are proxied through the FastAPI backend.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Fetch "Why This Section?" explanation from the backend.
 *
 * @param {Object} params
 * @param {number} [params.osm_edge_id]
 * @param {string} [params.segment_id]
 * @param {string} [params.route_id]
 * @param {Array<Array<number>>} [params.segment_coords]
 * @param {string} [params.question]
 * @returns {Promise<Object>} ExplainSectionResponse
 */
export async function explainSection({
  osm_edge_id = null,
  segment_id = null,
  route_id = null,
  segment_coords = null,
  question = null,
} = {}) {
  const payload = {};
  if (osm_edge_id != null) payload.osm_edge_id = Number(osm_edge_id);
  if (segment_id) payload.segment_id = segment_id;
  if (route_id) payload.route_id = route_id;
  if (segment_coords) payload.segment_coords = segment_coords;
  if (question) payload.question = question;

  const response = await fetch(`${API_BASE}/api/ai/explain-section`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new Error(errorBody.detail?.message || `AI Section Explanation failed (${response.status})`);
  }

  return response.json();
}

/**
 * Fetch AI Route Summary.
 *
 * @param {Object} params
 * @param {string} params.route_id
 * @param {number} [params.distance_km]
 * @param {number} [params.duration_minutes]
 * @param {number} [params.safety_score]
 * @param {number} [params.calibrated_historical_risk]
 * @param {Array<Object>} [params.alternative_routes]
 * @param {string} [params.question]
 * @returns {Promise<Object>} ExplainRouteResponse
 */
export async function explainRoute({
  route_id,
  distance_km = null,
  duration_minutes = null,
  safety_score = null,
  calibrated_historical_risk = null,
  alternative_routes = null,
  question = null,
} = {}) {
  const payload = { route_id };
  if (distance_km != null) payload.distance_km = distance_km;
  if (duration_minutes != null) payload.duration_minutes = duration_minutes;
  if (safety_score != null) payload.safety_score = safety_score;
  if (calibrated_historical_risk != null) payload.calibrated_historical_risk = calibrated_historical_risk;
  if (alternative_routes != null) payload.alternative_routes = alternative_routes;
  if (question) payload.question = question;

  const response = await fetch(`${API_BASE}/api/ai/explain-route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new Error(errorBody.detail?.message || `AI Route Summary failed (${response.status})`);
  }

  return response.json();
}

/**
 * Ask a custom question to the AI Safety Assistant.
 *
 * @param {Object} params
 * @param {string} params.question
 * @param {number} [params.osm_edge_id]
 * @param {string} [params.segment_id]
 * @param {string} [params.route_id]
 * @param {Array<Object>} [params.alternative_routes]
 * @returns {Promise<Object>} AskQuestionResponse
 */
export async function askAiAssistant({
  question,
  osm_edge_id = null,
  segment_id = null,
  route_id = null,
  alternative_routes = null,
}) {
  const payload = { question };
  if (osm_edge_id != null) payload.osm_edge_id = Number(osm_edge_id);
  if (segment_id) payload.segment_id = segment_id;
  if (route_id) payload.route_id = route_id;
  if (alternative_routes != null) payload.alternative_routes = alternative_routes;

  const response = await fetch(`${API_BASE}/api/ai/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new Error(errorBody.detail?.message || `AI query failed (${response.status})`);
  }

  return response.json();
}
