import { useState, useCallback } from 'react';
import { analyzeRouteTraffic } from '../services/trafficApi';

export default function useTraffic() {
 const [trafficData, setTrafficData] = useState({});
 const [loading, setLoading] = useState(false);
 const [error, setError] = useState(null);

 /**
  * Request traffic analysis for an array of candidate routes.
  * If a route's traffic fetch fails, it doesn't fail the rest.
  * 
  * @param {Array} routes - Array of candidate RouteResponse objects
  */
 const analyzeTrafficForRoutes = useCallback(async (routes) => {
  if (!routes || routes.length === 0) {
   setTrafficData({});
   return;
  }

  setLoading(true);
  setError(null);
  setTrafficData({}); // Reset previous traffic

  try {
   const results = {};
   
   // We can fetch traffic for all routes concurrently
   const promises = routes.map(async (route) => {
    try {
     const data = await analyzeRouteTraffic(route.id, route.geometry);
     results[route.id] = data;
    } catch (err) {
     console.warn(`Failed to fetch traffic for route ${route.id}`, err);
     // Don't throw here, just leave this route's traffic as undefined
    }
   });

   await Promise.all(promises);
   setTrafficData(results);

  } catch (err) {
   console.error('Error in analyzeTrafficForRoutes:', err);
   setError(err.message || 'Failed to fetch traffic analysis.');
  } finally {
   setLoading(false);
  }
 }, []);

 return {
  trafficData,
  loading,
  error,
  analyzeTrafficForRoutes,
 };
}
