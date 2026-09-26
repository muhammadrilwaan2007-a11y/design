/**
 * frontend/src/hooks/useWeather.js
 * Module 5 — Weather & Time Analysis
 *
 * Manages weather state with a 10-minute auto-refresh.
 *
 * Usage:
 *  const { weather, loading, error, fetchWeather, refreshWeather } = useWeather();
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { getCurrentWeather } from '../services/weatherApi';

const AUTO_REFRESH_MS = 10 * 60 * 1000; // 10 minutes

export default function useWeather() {
 const [weather, setWeather]  = useState(null);
 const [loading, setLoading]  = useState(false);
 const [error, setError]    = useState(null);

 // Store last coords for refresh
 const coordsRef  = useRef(null);
 const intervalRef = useRef(null);

 const _doFetch = useCallback(async (lat, lon) => {
  setLoading(true);
  setError(null);
  try {
   const data = await getCurrentWeather(lat, lon);
   setWeather(data);
   // If backend returned available=false, surface the error message
   if (!data.available) {
    setError(data.error || 'Weather data unavailable.');
   }
  } catch (err) {
   console.error('[useWeather] fetch failed:', err);
   setError('Weather data unavailable.');
   setWeather({ available: false });
  } finally {
   setLoading(false);
  }
 }, []);

 /** Fetch weather for a coordinate. Called after routes are generated. */
 const fetchWeather = useCallback(
  async (latitude, longitude) => {
   coordsRef.current = { latitude, longitude };
   await _doFetch(latitude, longitude);
  },
  [_doFetch],
 );

 /** Manual refresh using the last coordinates. */
 const refreshWeather = useCallback(async () => {
  if (coordsRef.current) {
   await _doFetch(coordsRef.current.latitude, coordsRef.current.longitude);
  }
 }, [_doFetch]);

 // ── Auto-refresh every 10 minutes while coords are set ───────────────────
 useEffect(() => {
  if (!coordsRef.current) return;

  intervalRef.current = setInterval(() => {
   if (coordsRef.current) {
    console.info('[useWeather] Auto-refreshing weather data…');
    _doFetch(coordsRef.current.latitude, coordsRef.current.longitude);
   }
  }, AUTO_REFRESH_MS);

  return () => {
   if (intervalRef.current) {
    clearInterval(intervalRef.current);
    intervalRef.current = null;
   }
  };
 }, [weather, _doFetch]); // Re-subscribe after each fetch to reset the timer

 return { weather, loading, error, fetchWeather, refreshWeather };
}
