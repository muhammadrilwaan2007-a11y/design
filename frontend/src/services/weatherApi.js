/**
 * frontend/src/services/weatherApi.js
 * Module 5 — Weather & Time Analysis
 *
 * Calls the backend POST /api/weather/current.
 * The OpenWeather API key never leaves the backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Fetch current weather and time features for a coordinate.
 *
 * @param {number} latitude
 * @param {number} longitude
 * @returns {Promise<WeatherResponse>}
 */
export async function getCurrentWeather(latitude, longitude) {
 const response = await fetch(`${API_BASE_URL}/api/weather/current`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ latitude, longitude }),
 });

 if (!response.ok) {
  throw new Error(`Weather API error: ${response.status} ${response.statusText}`);
 }

 return response.json();
}
