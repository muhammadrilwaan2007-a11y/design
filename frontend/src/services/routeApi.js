/**
 * routeApi.js
 * Frontend service for the RouteGuard AI routing API.
 *
 * Calls POST /api/routes on the FastAPI backend.
 * The frontend never calls OSRM directly.
 *
 * Architecture:
 *  React → routeApi.js → FastAPI /api/routes → OSRM
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Request candidate driving routes from the backend.
 *
 * @param {{ latitude: number, longitude: number }} source
 * @param {{ latitude: number, longitude: number }} destination
 * @returns {Promise<{
 *  routes: Array<{
 *   id: string,
 *   distance_meters: number,
 *   duration_seconds: number,
 *   geometry: { type: string, coordinates: number[][] },
 *   steps: Array<object>
 *  }>,
 *  source: object,
 *  destination: object
 * }>}
 */
export async function getRoutes(source, destination) {
 if (!source?.latitude || !source?.longitude) {
  throw new Error('Source coordinates are missing.');
 }
 if (!destination?.latitude || !destination?.longitude) {
  throw new Error('Destination coordinates are missing.');
 }

 const body = {
  source:   { latitude: source.latitude,   longitude: source.longitude },
  destination: { latitude: destination.latitude, longitude: destination.longitude },
 };

 let response;
 try {
  response = await fetch(`${API_BASE}/api/routes`, {
   method: 'POST',
   headers: { 'Content-Type': 'application/json' },
   body:  JSON.stringify(body),
   signal: AbortSignal.timeout(20_000),
  });
 } catch (err) {
  if (err?.name === 'TimeoutError' || err?.name === 'AbortError') {
   throw new Error('The routing request timed out. Please try again.');
  }
  if (!navigator.onLine) {
   throw new Error('No internet connection. Please check your network.');
  }
  throw new Error('Could not reach the routing server. Is the backend running?');
 }

 // ── Parse error detail from FastAPI ──────────────────────────────────────
 if (!response.ok) {
  let detail = null;
  try {
   const errBody = await response.json();
   detail = errBody?.detail;
  } catch { /* ignore */ }

  // 422 = NoRoute (well-known, friendly message)
  if (response.status === 422 && detail?.code === 'NO_ROUTE') {
   throw new NoRouteError(detail.message || 'No route could be found between these locations.');
  }

  // 503 = routing/OSRM error
  const message =
   detail?.message ||
   `Routing service error (HTTP ${response.status}). Please try again.`;
  throw new Error(message);
 }

 let data;
 try {
  data = await response.json();
 } catch {
  throw new Error('The routing server returned an unreadable response.');
 }

 if (!Array.isArray(data?.routes)) {
  throw new Error('Unexpected response from the routing server.');
 }

 return data;
}

/**
 * Sentinel error class for "no route found" — lets the UI show a distinct
 * message rather than a generic error banner.
 */
export class NoRouteError extends Error {
 constructor(message) {
  super(message);
  this.name = 'NoRouteError';
 }
}
