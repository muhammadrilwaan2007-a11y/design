/**
 * frontend/src/hooks/useIncidents.js
 * Module 4 — Live Incident Detection
 *
 * Manages incident state, fetches via incidentApi, and provides
 * an optional auto-refresh every 90 seconds.
 *
 * Returns:
 *  incidentData — { [routeId]: RouteIncidentAnalysis }
 *  loading    — boolean
 *  error     — string | null
 *  analyzeIncidentsForRoutes(routes) — initial fetch
 *  refreshIncidents()        — manual refresh
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { analyzeIncidents } from '../services/incidentApi';

const AUTO_REFRESH_MS = 90_000; // 90 seconds

export default function useIncidents() {
 const [incidentData, setIncidentData] = useState({});
 const [loading, setLoading]      = useState(false);
 const [error, setError]        = useState(null);

 // Keep the current routes available for the auto-refresh interval
 const routesRef  = useRef([]);
 const intervalRef = useRef(null);

 const _doFetch = useCallback(async (routes) => {
  if (!routes || routes.length === 0) return;
  setLoading(true);
  setError(null);
  try {
   const response = await analyzeIncidents(routes);
   // Key results by route_id for O(1) lookup in components
   const byRoute = {};
   for (const ra of response.routes) {
    byRoute[ra.route_id] = ra;
   }
   setIncidentData(byRoute);
  } catch (err) {
   console.error('[useIncidents] fetch failed:', err);
   setError('Live incident data unavailable.');
  } finally {
   setLoading(false);
  }
 }, []);

 /** Initial fetch triggered after routes are generated. */
 const analyzeIncidentsForRoutes = useCallback(
  async (routes) => {
   routesRef.current = routes;
   setIncidentData({});
   await _doFetch(routes);
  },
  [_doFetch],
 );

 /** Manual refresh — re-uses the routes from the last call. */
 const refreshIncidents = useCallback(async () => {
  await _doFetch(routesRef.current);
 }, [_doFetch]);

 // ── Auto-refresh every 90 s while routes are loaded ──────────────────────
 useEffect(() => {
  // Start interval only when we have routes
  if (routesRef.current.length > 0) {
   intervalRef.current = setInterval(() => {
    if (routesRef.current.length > 0) {
     console.info('[useIncidents] Auto-refreshing incident data…');
     _doFetch(routesRef.current);
    }
   }, AUTO_REFRESH_MS);
  }

  return () => {
   if (intervalRef.current) {
    clearInterval(intervalRef.current);
    intervalRef.current = null;
   }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [incidentData]); // Re-subscribe when data changes (i.e. after first fetch)

 return {
  incidentData,
  loading,
  error,
  analyzeIncidentsForRoutes,
  refreshIncidents,
 };
}
