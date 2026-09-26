/**
 * frontend/src/utils/routeRecommendation.js
 * =========================================
 * Intelligent Road-Closure & Safety-Aware Recommendation Engine.
 *
 * Requirements:
 * 1. Identify the theoretically safest route based on historical accident risk
 *  (highest route_safety_score from Module 8 XGBoost + Bayesian calibration).
 * 2. Check for active road closures across candidate routes using:
 *  - TomTom live incident features (road_closure_count > 0, icon_category == 8)
 *  - Incident descriptions matching closure keywords ("road closed", "closed to traffic", etc.)
 *  - TomTom traffic flow summary (road_closure === true)
 *  - Segment-level incident features
 *  - Optional simulated closures for testing and demonstration
 * 3. If the safest route has an active road closure:
 *  - The route CANNOT be traveled due to road closure.
 *  - Recommend the best passable alternative (the route with the highest safety score
 *   among candidate routes with NO road closures).
 *  - Auto-select the passable alternative so the user is guided to a safe, drivable path.
 * 4. If the safest route has NO road closures:
 *  - Standard recommendation applies (safest route recommended directly).
 */

/**
 * Check if a route has an active road closure.
 *
 * @param {string} routeId
 * @param {object} context
 * @param {object} [context.incidentData]
 * @param {object} [context.trafficData]
 * @param {object} [context.featuresData]
 * @param {Set<string>} [context.simulatedClosures]
 * @returns {{ hasClosure: boolean, closureCount: number, reason: string | null, isSimulated: boolean }}
 */
export function checkRouteClosure(routeId, {
 incidentData = {},
 trafficData = {},
 featuresData = {},
 simulatedClosures = new Set(),
} = {}) {
 if (simulatedClosures && simulatedClosures.has(routeId)) {
  return {
   hasClosure: true,
   closureCount: 1,
   reason: 'Active road closure (Simulated for demonstration)',
   isSimulated: true,
  };
 }

 // 1. Incident features road_closure_count
 const incidentAnalysis = incidentData?.[routeId];
 const incidentFeatures = incidentAnalysis?.features;
 const closureCount = incidentFeatures?.road_closure_count || 0;
 if (closureCount > 0) {
  return {
   hasClosure: true,
   closureCount,
   reason: `${closureCount} active road closure${closureCount > 1 ? 's' : ''} reported on this route.`,
   isSimulated: false,
  };
 }

 // 2. Incident list matching (icon_category === 8 or text matching strictly within 25m)
 const matchingIncident = (incidentAnalysis?.incidents || []).find((inc) => {
  // Ensure road closures are strictly on the road corridor (<= 25m)
  if (inc.distance_to_route_m != null && inc.distance_to_route_m > 25.0) return false;
  if (inc.icon_category === 8) return true;
  const text = `${inc.type || ''} ${inc.description || ''}`.toLowerCase();
  return (
   text.includes('road closed') ||
   text.includes('road closure') ||
   text.includes('closed to traffic') ||
   text.includes('entire road closed')
  );
 });
 if (matchingIncident) {
  return {
   hasClosure: true,
   closureCount: 1,
   reason: matchingIncident.description || matchingIncident.type || 'Road closed to traffic',
   isSimulated: false,
  };
 }

 // 3. Traffic summary road_closure
 const trafficSummary = trafficData?.[routeId]?.route_summary;
 if (trafficSummary?.road_closure === true) {
  return {
   hasClosure: true,
   closureCount: 1,
   reason: 'Live traffic flow reports road closure along corridor.',
   isSimulated: false,
  };
 }

 // 4. Segment features road_closure_count (fallback if route-level incident analysis is unavailable)
 if (!incidentAnalysis) {
  const segments = featuresData?.[routeId]?.segments;
  const closedSeg = segments?.find(
   (s) =>
    (s.road_closure_count || 0) > 0 &&
    (s.nearest_incident_distance_m == null || s.nearest_incident_distance_m <= 25.0)
  );
  if (closedSeg) {
   return {
    hasClosure: true,
    closureCount: closedSeg.road_closure_count,
    reason: 'Segment incident analysis flags active road closure on corridor.',
    isSimulated: false,
   };
  }
 }

 return {
  hasClosure: false,
  closureCount: 0,
  reason: null,
  isSimulated: false,
 };
}

/**
 * Computes the recommendation state across all candidate routes.
 *
 * @param {object} params
 * @param {Array} params.routes
 * @param {object} params.featuresData
 * @param {object} params.incidentData
 * @param {object} params.trafficData
 * @param {Set<string>} [params.simulatedClosures]
 * @returns {object} Recommendation analysis
 */
export function getRouteRecommendation({
 routes = [],
 featuresData = {},
 incidentData = {},
 trafficData = {},
 simulatedClosures = new Set(),
} = {}) {
 if (!routes || routes.length === 0) {
  return {
   theoreticallySafestRoute: null,
   theoreticallySafestScore: null,
   theoreticallySafestIndex: -1,
   isSafestRouteClosed: false,
   safestClosureInfo: null,
   recommendedRoute: null,
   recommendedScore: null,
   recommendedIndex: -1,
   isAlternativeRecommendation: false,
   allRoutesClosed: false,
   closureMap: {},
  };
 }

 // Build closure map for all candidate routes
 const closureMap = {};
 for (const r of routes) {
  closureMap[r.id] = checkRouteClosure(r.id, {
   incidentData,
   trafficData,
   featuresData,
   simulatedClosures,
  });
 }

 // Find the theoretically safest route (highest route_safety_score)
 let theoreticallySafestRoute = null;
 let bestScore = -1;

 for (const r of routes) {
  const score = featuresData?.[r.id]?.route_safety_score;
  if (score != null && score > bestScore) {
   bestScore = score;
   theoreticallySafestRoute = r;
  }
 }

 // Fallback to first route if safety scores are not ready yet
 if (!theoreticallySafestRoute && routes.length > 0) {
  theoreticallySafestRoute = routes[0];
 }

 const theoreticallySafestIndex = theoreticallySafestRoute
  ? routes.findIndex((r) => r.id === theoreticallySafestRoute.id)
  : -1;
 const theoreticallySafestScore = theoreticallySafestRoute
  ? featuresData?.[theoreticallySafestRoute.id]?.route_safety_score ?? null
  : null;

 const safestClosureInfo = theoreticallySafestRoute
  ? closureMap[theoreticallySafestRoute.id]
  : null;
 const isSafestRouteClosed = safestClosureInfo?.hasClosure === true;

 // Determine the recommended passable route
 let recommendedRoute = null;
 let isAlternativeRecommendation = false;

 if (!isSafestRouteClosed) {
  // Safest route is open and drivable!
  recommendedRoute = theoreticallySafestRoute;
  isAlternativeRecommendation = false;
 } else {
  // The safest route is closed!
  // Find the best passable alternative (no road closures) with highest safety score
  const openRoutes = routes.filter((r) => !closureMap[r.id]?.hasClosure);

  if (openRoutes.length > 0) {
   let bestOpenScore = -1;
   let bestOpenRoute = null;

   for (const r of openRoutes) {
    const score = featuresData?.[r.id]?.route_safety_score;
    if (score != null && score > bestOpenScore) {
     bestOpenScore = score;
     bestOpenRoute = r;
    }
   }

   // If scores not loaded yet or equal, pick fastest among open routes
   if (!bestOpenRoute) {
    bestOpenRoute = [...openRoutes].sort(
     (a, b) => (a.duration_seconds || 0) - (b.duration_seconds || 0),
    )[0];
   }

   recommendedRoute = bestOpenRoute;
   isAlternativeRecommendation = true;
  } else {
   // All routes closed (rare edge case)
   recommendedRoute = theoreticallySafestRoute;
   isAlternativeRecommendation = false;
  }
 }

 const recommendedIndex = recommendedRoute
  ? routes.findIndex((r) => r.id === recommendedRoute.id)
  : -1;
 const recommendedScore = recommendedRoute
  ? featuresData?.[recommendedRoute.id]?.route_safety_score ?? null
  : null;

 const allRoutesClosed = routes.every((r) => closureMap[r.id]?.hasClosure);

 return {
  theoreticallySafestRoute,
  theoreticallySafestScore,
  theoreticallySafestIndex,
  isSafestRouteClosed,
  safestClosureInfo,
  recommendedRoute,
  recommendedScore,
  recommendedIndex,
  isAlternativeRecommendation,
  allRoutesClosed,
  closureMap,
 };
}
