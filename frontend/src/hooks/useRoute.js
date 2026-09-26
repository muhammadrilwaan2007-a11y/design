/**
 * useRoute.js
 * Custom hook that manages the full routing lifecycle.
 *
 * Returns:
 *  routes    — Array<RouteResponse> | []
 *  selectedRoute — RouteResponse | null
 *  loading    — boolean
 *  error     — string | null
 *  noRoute    — boolean (OSRM returned no route — distinct from error)
 *  fetchRoutes  — (source, destination) => void
 *  selectRoute  — (route) => void
 *  clearRoutes  — () => void
 */

import { useState, useCallback } from 'react';
import { getRoutes, NoRouteError } from '../services/routeApi';

export function useRoute(initialRoutes = [], initialSelectedRoute = null) {
 const [routes,    setRoutes]    = useState(initialRoutes);
 const [selectedRoute, setSelectedRoute] = useState(initialSelectedRoute);
 const [loading,    setLoading]    = useState(false);
 const [error,     setError]     = useState(null);
 const [noRoute,    setNoRoute]    = useState(false);

 const fetchRoutes = useCallback(async (source, destination) => {
  if (!source || !destination) return;

  setLoading(true);
  setError(null);
  setNoRoute(false);
  setRoutes([]);
  setSelectedRoute(null);

  try {
   const data = await getRoutes(source, destination);
   const fetchedRoutes = data.routes ?? [];
   setRoutes(fetchedRoutes);
   // Auto-select the first route
   if (fetchedRoutes.length > 0) {
    setSelectedRoute(fetchedRoutes[0]);
   }
  } catch (err) {
   if (err instanceof NoRouteError) {
    setNoRoute(true);
   } else {
    setError(err.message || 'An unexpected routing error occurred.');
   }
  } finally {
   setLoading(false);
  }
 }, []);

 const selectRoute = useCallback((route) => {
  setSelectedRoute(route);
 }, []);

 const clearRoutes = useCallback(() => {
  setRoutes([]);
  setSelectedRoute(null);
  setError(null);
  setNoRoute(false);
 }, []);

 return {
  routes,
  selectedRoute,
  loading,
  error,
  noRoute,
  fetchRoutes,
  selectRoute,
  clearRoutes,
 };
}
