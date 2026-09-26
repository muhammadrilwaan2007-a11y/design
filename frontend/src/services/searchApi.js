/**
 * searchApi.js
 * TomTom Search API wrapper for SafeRoute AI.
 *
 * Docs: https://developer.tomtom.com/search-api/documentation/search-service/fuzzy-search
 *
 * Environment variable required:
 *  VITE_TOMTOM_API_KEY — set in frontend/.env
 */

const TOMTOM_BASE_URL = 'https://api.tomtom.com/search/2/search';

// Bengaluru city centre — used as bias when no user coords are provided.
const BENGALURU_LAT = 12.9716;
const BENGALURU_LON = 77.5946;

/**
 * Normalise a raw TomTom result entry into the shape consumed by the UI.
 * @param {object} result — single entry from TomTom results array
 * @returns {{ id, name, address, latitude, longitude, type }}
 */
function normaliseResult(result) {
 const poi  = result.poi  || {};
 const addr = result.address || {};
 const pos  = result.position || {};

 // Prefer POI name, fall back to free-form address
 const name =
  poi.name ||
  addr.freeformAddress ||
  addr.streetName ||
  'Unknown place';

 // Build a concise display address
 const addressParts = [
  addr.streetName,
  addr.municipalitySubdivision,
  addr.municipality,
 ].filter(Boolean);

 const address =
  addressParts.length > 0
   ? addressParts.join(', ')
   : addr.freeformAddress || '';

 return {
  id:    result.id || `${pos.lat}-${pos.lon}`,
  name,
  address,
  latitude: pos.lat,
  longitude: pos.lon,
  type:   result.type || poi.categories?.[0] || 'place',
 };
}

/**
 * Search for places using TomTom Fuzzy Search (supports typeahead / autocomplete).
 *
 * @param {string} query     — user input text
 * @param {number} [lat]     — optional latitude to bias results (defaults to Bengaluru)
 * @param {number} [lon]     — optional longitude to bias results (defaults to Bengaluru)
 * @param {object} [options]
 * @param {number} [options.radius=50000]  — search radius in metres
 * @param {number} [options.limit=8]     — max results
 * @param {boolean}[options.typeahead=true] — enable autocomplete mode
 * @returns {Promise<Array<{id, name, address, latitude, longitude, type}>>}
 */
export async function searchPlaces(query, lat, lon, options = {}) {
 const apiKey = import.meta.env.VITE_TOMTOM_API_KEY;

 if (!apiKey || apiKey === 'YOUR_KEY_HERE') {
  throw new Error(
   'TomTom API key is missing. Set VITE_TOMTOM_API_KEY in frontend/.env',
  );
 }

 const trimmed = query?.trim();
 if (!trimmed) return [];

 const {
  radius  = 50_000,  // 50 km — covers all of Greater Bengaluru
  limit   = 8,
  typeahead = true,
 } = options;

 const biasLat = lat ?? BENGALURU_LAT;
 const biasLon = lon ?? BENGALURU_LON;

 const params = new URLSearchParams({
  key:    apiKey,
  query:   trimmed,
  lat:    biasLat,
  lon:    biasLon,
  radius,
  limit,
  countrySet: 'IN',
  typeahead,
  language:  'en-GB',
  view:    'IN',    // India-specific view
 });

 const url = `${TOMTOM_BASE_URL}/${encodeURIComponent(trimmed)}.json?${params}`;

 const response = await fetch(url, {
  method: 'GET',
  headers: { Accept: 'application/json' },
  signal: AbortSignal.timeout(8000), // 8-second timeout
 });

 if (!response.ok) {
  const text = await response.text().catch(() => '');
  throw new Error(
   `TomTom API error ${response.status}: ${text || response.statusText}`,
  );
 }

 const data = await response.json();
 const results = data.results ?? [];

 return results.map(normaliseResult);
}

/**
 * Reverse-geocode coordinates to a human-readable place name.
 * Used when the user selects their current GPS location.
 *
 * @param {number} lat
 * @param {number} lon
 * @returns {Promise<string>} — display label for the position
 */
export async function reverseGeocode(lat, lon) {
 const apiKey = import.meta.env.VITE_TOMTOM_API_KEY;

 if (!apiKey || apiKey === 'YOUR_KEY_HERE') {
  // Gracefully degrade — show coordinates instead of a name
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
 }

 try {
  const params = new URLSearchParams({
   key:   apiKey,
   language: 'en-GB',
  });

  const url = `https://api.tomtom.com/search/2/reverseGeocode/${lat},${lon}.json?${params}`;
  const response = await fetch(url, {
   signal: AbortSignal.timeout(6000),
  });

  if (!response.ok) return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;

  const data = await response.json();
  const addr = data.addresses?.[0]?.address;
  if (!addr) return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;

  // Prefer street / area name over full address for compactness
  return (
   addr.streetName ||
   addr.municipalitySubdivision ||
   addr.municipality ||
   addr.freeformAddress ||
   `${lat.toFixed(5)}, ${lon.toFixed(5)}`
  );
 } catch {
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
 }
}
