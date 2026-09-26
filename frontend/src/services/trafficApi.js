const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Analyzes traffic for a given candidate route.
 * @param {string} routeId - The identifier for the route
 * @param {object} geometry - GeoJSON LineString geometry
 * @returns {Promise<object>} The traffic analysis response
 */
export async function analyzeRouteTraffic(routeId, geometry) {
 try {
  const response = await fetch(`${API_BASE_URL}/api/traffic/analyze`, {
   method: 'POST',
   headers: {
    'Content-Type': 'application/json',
   },
   body: JSON.stringify({
    route_id: routeId,
    geometry: geometry
   })
  });

  if (!response.ok) {
   throw new Error(`Traffic API error: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();
  return data;
 } catch (err) {
  console.error(`Traffic analysis failed for route ${routeId}:`, err);
  throw err;
 }
}
