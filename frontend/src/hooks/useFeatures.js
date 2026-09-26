/**
 * frontend/src/hooks/useFeatures.js
 * Custom hook that manages the safety features + risk scores lifecycle.
 *
 * Triggered after routes are available (call analyzeFeatures(routes)).
 *
 * Returns:
 *  featuresData — Record<route_id, { route_safety_score, route_risk_category, segments }>
 *  featuresLoading — boolean
 *  featuresError  — string | null
 *  analyzeFeatures — (routes: RouteResponse[]) => void
 *  clearFeatures  — () => void
 */

import { useState, useCallback, useRef } from 'react';
import { getRouteFeatures } from '../services/featuresApi';

export default function useFeatures() {
 const [featuresData,  setFeaturesData]  = useState({});
 const [featuresLoading, setFeaturesLoading] = useState(false);
 const [featuresError,  setFeaturesError]  = useState(null);
 const routesRef = useRef([]);

 const analyzeFeatures = useCallback(async (routes, isRetry = false) => {
  if (!routes || routes.length === 0) return;
  routesRef.current = routes;

  setFeaturesLoading(true);
  setFeaturesError(null);

  try {
   const data = await getRouteFeatures(routes);
   setFeaturesData(data);
   setFeaturesError(null);
  } catch (err) {
   // Auto-retry once after 1.5s if this was the initial attempt
   if (!isRetry) {
    console.warn('[useFeatures] Initial analysis failed, auto-retrying in 1.5s...', err.message);
    await new Promise((resolve) => setTimeout(resolve, 1500));
    try {
     const retryData = await getRouteFeatures(routes);
     setFeaturesData(retryData);
     setFeaturesError(null);
     return;
    } catch (retryErr) {
     console.error('[useFeatures] Retry analysis also failed:', retryErr);
     setFeaturesError(retryErr.message || 'Safety score analysis failed.');
    }
   } else {
    setFeaturesError(err.message || 'Safety score analysis failed.');
   }
  } finally {
   setFeaturesLoading(false);
  }
 }, []);

 const retryFeatures = useCallback(() => {
  if (routesRef.current && routesRef.current.length > 0) {
   analyzeFeatures(routesRef.current, true);
  }
 }, [analyzeFeatures]);

 const clearFeatures = useCallback(() => {
  routesRef.current = [];
  setFeaturesData({});
  setFeaturesError(null);
  setFeaturesLoading(false);
 }, []);

 return {
  featuresData,
  featuresLoading,
  featuresError,
  analyzeFeatures,
  retryFeatures,
  clearFeatures,
 };
}

