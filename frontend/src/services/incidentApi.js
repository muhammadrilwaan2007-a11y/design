/**
 * frontend/src/services/incidentApi.js
 * Module 4 — Live Incident Detection
 *
 * Calls the backend POST /api/incidents/analyze endpoint.
 * The TomTom API key never leaves the backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Analyze live incidents for an array of candidate routes.
 *
 * @param {Array} routes - Array of RouteResponse objects (must have .id and .geometry)
 * @returns {Promise<object>} IncidentAnalysisResponse
 */
export async function analyzeIncidents(routes) {
 if (!routes || routes.length === 0) {
  throw new Error('No routes provided for incident analysis.');
 }

 const payload = {
  routes: routes.map((r) => ({
   route_id: r.id,
   geometry: r.geometry,
  })),
 };

 const response = await fetch(`${API_BASE_URL}/api/incidents/analyze`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
 });

 if (!response.ok) {
  throw new Error(`Incident API error: ${response.status} ${response.statusText}`);
 }

 return response.json();
}
