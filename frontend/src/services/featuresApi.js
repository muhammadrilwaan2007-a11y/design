/**
 * frontend/src/services/featuresApi.js
 * Service layer for POST /api/features/analyze (Module 7 + 8).
 *
 * Returns per-route safety scores as a map keyed by route_id:
 *  {
 *   [route_id]: {
 *    route_safety_score: number | null,
 *    route_risk_category: string | null,  // "low" | "medium" | "high"
 *    segments: SegmentFeatureVector[]
 *   }
 *  }
 *
 * Architecture:
 *  React → featuresApi.js → FastAPI /api/features/analyze → Module 7 + 8
 *
 * Safety Score values are passed through verbatim from the backend.
 * No calculation, rounding, or interpretation is performed here.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Fetch safety features + risk scores for a set of candidate routes.
 *
 * @param {Array<{ id: string, geometry: { type: string, coordinates: number[][] } }>} routes
 * @returns {Promise<Record<string, { route_safety_score: number|null, route_risk_category: string|null, segments: object[] }>>}
 */
export async function getRouteFeatures(routes) {
 if (!routes || routes.length === 0) {
  throw new Error('No routes provided to features analysis.');
 }

 // Build request body — match MultiRouteFeatureRequest schema exactly
 const body = {
  routes: routes.map((r) => ({
   route_id: r.id,
   geometry: r.geometry,
  })),
 };

 let response;
 try {
  response = await fetch(`${API_BASE}/api/features/analyze`, {
   method: 'POST',
   headers: { 'Content-Type': 'application/json' },
   body: JSON.stringify(body),
   signal: AbortSignal.timeout(30_000), // Features pipeline can take up to 30s
  });
 } catch (err) {
  if (err?.name === 'TimeoutError' || err?.name === 'AbortError') {
   throw new Error('Safety analysis timed out. Scores will be unavailable.');
  }
  if (!navigator.onLine) {
   throw new Error('No internet connection. Safety scores unavailable.');
  }
  throw new Error('Could not reach the safety analysis service.');
 }

 if (!response.ok) {
  let detail = null;
  try {
   const errBody = await response.json();
   detail = errBody?.detail;
  } catch { /* ignore */ }
  const message =
   detail?.message ||
   `Safety analysis failed (HTTP ${response.status}).`;
  throw new Error(message);
 }

 let data;
 try {
  data = await response.json();
 } catch {
  throw new Error('Safety analysis returned an unreadable response.');
 }

 if (!Array.isArray(data?.routes)) {
  throw new Error('Unexpected response shape from safety analysis service.');
 }

 // Normalise into a map keyed by route_id for O(1) lookup in components
 const featureMap = {};
 for (const routeResult of data.routes) {
  featureMap[routeResult.route_id] = {
   route_safety_score:     routeResult.route_safety_score    ?? null,
   route_risk_category:    routeResult.route_risk_category    ?? null,
   route_raw_risk_prob:    routeResult.route_raw_risk_prob    ?? null,
   route_calibrated_risk_prob: routeResult.route_calibrated_risk_prob ?? null,
   segments:          routeResult.segments          ?? [],
   heatmap_edges:       routeResult.heatmap_edges       ?? [],
  };
 }

 return featureMap;
}

/**
 * Fetch standalone risk heatmap edges for Bengaluru road network or bbox.
 *
 * @param {object} params - Optional { min_lat, min_lon, max_lat, max_lon, limit }
 * @returns {Promise<Array<object>>} - List of OSM heatmap edges with geometry and risk
 */
export async function getHistoricalRiskHeatmap(params = {}) {
 const query = new URLSearchParams();
 if (params.min_lat != null) query.append('min_lat', params.min_lat);
 if (params.min_lon != null) query.append('min_lon', params.min_lon);
 if (params.max_lat != null) query.append('max_lat', params.max_lat);
 if (params.max_lon != null) query.append('max_lon', params.max_lon);
 if (params.limit != null) query.append('limit', params.limit);

 const url = `${API_BASE}/api/features/heatmap${query.toString() ? `?${query.toString()}` : ''}`;
 try {
  const response = await fetch(url, {
   method: 'GET',
   headers: { 'Accept': 'application/json' },
   signal: AbortSignal.timeout(15_000),
  });

  if (!response.ok) {
   throw new Error(`Heatmap request failed with HTTP ${response.status}`);
  }

  const data = await response.json();
  return data?.edges ?? [];
 } catch (err) {
  console.warn('[featuresApi] Failed to fetch risk heatmap:', err);
  return [];
 }
}
