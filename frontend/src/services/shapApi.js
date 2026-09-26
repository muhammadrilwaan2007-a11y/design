/**
 * frontend/src/services/shapApi.js
 * ====================================
 * API service for Local SHAP explanations.
 *
 * Calls GET /api/features/roads/{edge_id}/explanation
 *
 * IMPORTANT:
 *  SHAP explanations are an interpretation layer ONLY.
 *  They do NOT affect the Safety Score, raw_risk_prob, or calibrated_risk_prob.
 *  SHAP values are in model log-odds space — they are NOT percentage-point changes.
 *
 * Architecture:
 *  User clicks road on heatmap
 *    ↓
 *  shapApi.getEdgeExplanation(edge_id)
 *    ↓
 *  GET /api/features/roads/{edge_id}/explanation
 *    ↓
 *  ShapExplanationPanel renders the explanation
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Fetch the Local SHAP explanation for a specific OSM road edge.
 *
 * @param {number} edgeId - The unique_edge_id of an OSM road edge
 * @returns {Promise<object>} - ShapExplanation dict from the backend
 * @throws {Error} if the request fails or the edge is not found
 */
export async function getEdgeExplanation(edgeId) {
 if (edgeId == null || isNaN(edgeId)) {
  throw new Error('Invalid edge ID provided to SHAP explanation service.');
 }

 let response;
 try {
  response = await fetch(`${API_BASE}/api/features/roads/${edgeId}/explanation`, {
   method: 'GET',
   headers: { 'Accept': 'application/json' },
   signal: AbortSignal.timeout(15_000),
  });
 } catch (err) {
  if (err?.name === 'TimeoutError' || err?.name === 'AbortError') {
   throw new Error('SHAP explanation request timed out.');
  }
  throw new Error('Could not reach the SHAP explanation service.');
 }

 if (response.status === 404) {
  throw new Error(`Edge ${edgeId} not found in road network.`);
 }

 if (response.status === 503) {
  throw new Error('SHAP explainer not ready — model may still be loading.');
 }

 if (!response.ok) {
  let detail = null;
  try {
   const errBody = await response.json();
   detail = errBody?.detail;
  } catch { /* ignore */ }
  throw new Error(detail?.message || `Explanation request failed (HTTP ${response.status}).`);
 }

 let data;
 try {
  data = await response.json();
 } catch {
  throw new Error('SHAP explanation returned an unreadable response.');
 }

 return data;
}
