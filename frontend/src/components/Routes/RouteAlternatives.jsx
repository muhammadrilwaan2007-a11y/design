/**
 * RouteAlternatives.jsx
 * Renders the list of all candidate routes + loading/error/no-route states.
 *
 * Props:
 *  routes    — Array<RouteResponse>
 *  selectedRoute — RouteResponse | null
 *  loading    — boolean
 *  error     — string | null
 *  noRoute    — boolean
 *  onSelectRoute — (route) => void
 *  onFindRoutes — () => void  (retry / initial trigger)
 *  canFetch   — boolean   (true when source + destination are both set)
 */

import { useMemo } from 'react';
import { Loader2, AlertCircle, NavigationOff, Route, ShieldCheck, AlertTriangle } from 'lucide-react';
import RouteCard from './RouteCard';
import { getRouteRecommendation } from '../../utils/routeRecommendation';

export default function RouteAlternatives({
 routes = [],
 selectedRoute,
 loading,
 error,
 noRoute,
 onSelectRoute,
 onFindRoutes,
 canFetch,
 trafficData,
 incidentData,
 featuresData,
 featuresLoading,
 recommendation: propRecommendation = null,
 onToggleSimulatedClosure: _onToggleSimulatedClosure = null,
 simulatedClosures = new Set(),
}) {
 // Use recommendation from prop if supplied, or compute locally
 const recommendation = useMemo(() => {
  if (propRecommendation) return propRecommendation;
  return getRouteRecommendation({
   routes,
   featuresData,
   incidentData,
   trafficData,
   simulatedClosures,
  });
 }, [propRecommendation, routes, featuresData, incidentData, trafficData, simulatedClosures]);

 const {
  theoreticallySafestRoute,
  theoreticallySafestScore,
  theoreticallySafestIndex,
  isSafestRouteClosed,
  recommendedRoute,
  recommendedScore,
  recommendedIndex,
  isAlternativeRecommendation,
  allRoutesClosed,
  closureMap,
 } = recommendation;

 // Identify the fastest route (shortest duration_seconds)
 const fastestRoute = useMemo(() => {
  if (!routes || routes.length === 0) return null;
  return [...routes].sort((a, b) => (a.duration_seconds || 0) - (b.duration_seconds || 0))[0];
 }, [routes]);

 // ── Not yet ready ─────────────────────────────────────────────────────────
 if (!canFetch) return null;

 // ── Loading ───────────────────────────────────────────────────────────────
 if (loading) {
  return (
   <div className="flex flex-col items-center gap-2 py-5 text-slate-500 dark:text-slate-400">
    <Loader2 size={22} className="animate-spin text-primary-500" />
    <p className="text-sm font-medium">Finding routes…</p>
   </div>
  );
 }

 // ── No route ──────────────────────────────────────────────────────────────
 if (noRoute) {
  return (
   <div
    role="alert"
    className="flex flex-col items-center gap-2 py-5 text-center text-slate-500 dark:text-slate-400"
   >
    <NavigationOff size={22} className="text-amber-500" />
    <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
     No route found
    </p>
    <p className="text-xs">
     No drivable route could be found between these locations.
     <br />
     Try selecting different start or end points.
    </p>
   </div>
  );
 }

 // ── Error ─────────────────────────────────────────────────────────────────
 if (error) {
  return (
   <div
    role="alert"
    className="flex flex-col items-center gap-2 py-5 text-center"
   >
    <AlertCircle size={22} className="text-red-500" />
    <p className="text-sm font-medium text-red-600 dark:text-red-400">
     Routing failed
    </p>
    <p className="text-xs text-slate-500 dark:text-slate-400 max-w-[220px]">
     {error}
    </p>
    <button
     type="button"
     onClick={onFindRoutes}
     className="mt-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline"
    >
     Try again
    </button>
   </div>
  );
 }

 // ── Initial state — prompt user to click Find Routes ──────────────────────
 if (routes.length === 0) {
  return (
   <div className="flex flex-col items-center gap-2 py-4 text-center">
    <Route size={20} className="text-primary-400" />
    <p className="text-xs text-slate-500 dark:text-slate-400">
     Click <strong className="text-slate-700 dark:text-slate-200">Find Routes</strong> to generate candidate routes.
    </p>
   </div>
  );
 }

 // ── Route list ────────────────────────────────────────────────────────────
 return (
  <div className="flex flex-col gap-2">
   {/* ── Case 1: Safest Route has Road Closure -> Recommend Alternative Banner ── */}
   {isAlternativeRecommendation && recommendedRoute && (
    <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-700/80 rounded-xl p-3 flex items-start gap-2.5 shadow-xs">
     <AlertTriangle className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" size={18} />
     <div className="min-w-0 flex-1">
      <div className="flex items-center justify-between gap-1 flex-wrap">
       <span className="font-bold text-amber-950 dark:text-amber-200 text-xs">
        🛡️ Alternative Recommended: Route {recommendedIndex + 1}
       </span>
       {recommendedScore != null && (
        <span className="text-[10px] font-extrabold text-amber-800 dark:text-amber-300 bg-amber-100 dark:bg-amber-900/60 px-2 py-0.5 rounded-full">
         Score: {recommendedScore}/100
        </span>
       )}
      </div>
      <p className="text-[11px] text-amber-900 dark:text-amber-200/90 mt-1 leading-snug">
       <strong>Route {theoreticallySafestIndex + 1}</strong> has the highest safety score ({theoreticallySafestScore ?? '—'}/100) but <strong>cannot be traveled due to an active road closure</strong>.
      </p>
      <p className="text-[11px] text-amber-800 dark:text-amber-300/80 mt-0.5 leading-snug">
       👉 Route {recommendedIndex + 1} is recommended as your safest passable alternative.
      </p>
     </div>
    </div>
   )}

   {/* ── Case 2: Standard Safest Route Recommendation (No Closure) ── */}
   {!isAlternativeRecommendation && !allRoutesClosed && recommendedRoute && recommendedScore != null && (
    <div className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-300 dark:border-emerald-800 rounded-xl p-2.5 flex items-start gap-2 shadow-xs">
     <ShieldCheck className="text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" size={17} />
     <div className="min-w-0 flex-1">
      <div className="flex items-center justify-between gap-1">
       <span className="font-bold text-emerald-900 dark:text-emerald-200 text-xs">
        Recommended: Route {recommendedIndex + 1}
       </span>
       <span className="text-[10px] font-extrabold text-emerald-700 dark:text-emerald-300 bg-emerald-100 dark:bg-emerald-900/60 px-2 py-0.5 rounded-full">
        Score: {recommendedScore}/100
       </span>
      </div>
      <p className="text-[11px] text-emerald-700 dark:text-emerald-300/90 mt-0.5 leading-snug">
       Identified as the safest path with the lowest historical accident risk.
      </p>
     </div>
    </div>
   )}

   {/* ── Case 3: All candidate routes have road closures ── */}
   {allRoutesClosed && (
    <div className="bg-rose-50 dark:bg-rose-950/40 border border-rose-300 dark:border-rose-800 rounded-xl p-2.5 flex items-start gap-2 text-xs shadow-xs">
     <AlertCircle className="text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" size={17} />
     <div className="min-w-0 flex-1">
      <p className="font-bold text-rose-900 dark:text-rose-200 text-xs">
       ⚠️ Road Closures on All Candidate Routes
      </p>
      <p className="text-[11px] text-rose-800 dark:text-rose-300/90 mt-0.5 leading-snug">
       Every route reports active road closures. Exercise caution and verify local traffic police advisories.
      </p>
     </div>
    </div>
   )}

   <div className="flex items-center justify-between px-1">
    <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
     {routes.length} candidate route{routes.length !== 1 ? 's' : ''}
    </p>
   </div>

   {routes.map((route, idx) => {
    const closure = closureMap?.[route.id];
    const isRouteSafest = theoreticallySafestRoute?.id === route.id;
    const isRouteRecommendedAlt = isAlternativeRecommendation && recommendedRoute?.id === route.id;
    const isRouteRecommendedStandard = !isAlternativeRecommendation && recommendedRoute?.id === route.id;

    return (
     <RouteCard
      key={route.id}
      route={route}
      index={idx}
      isSelected={selectedRoute?.id === route.id}
      onSelect={() => onSelectRoute(route)}
      trafficSummary={trafficData?.[route.id]?.route_summary}
      incidentFeatures={incidentData?.[route.id]?.features}
      safetyScore={featuresData?.[route.id]?.route_safety_score ?? null}
      riskCategory={featuresData?.[route.id]?.route_risk_category ?? null}
      featuresLoading={featuresLoading}
      isSafest={isRouteSafest}
      isSafestClosed={isRouteSafest && isSafestRouteClosed}
      isRecommendedAlternative={isRouteRecommendedAlt}
      isRecommended={isRouteRecommendedStandard}
      hasRoadClosure={closure?.hasClosure ?? false}
      closureReason={closure?.reason ?? null}
      isFastest={fastestRoute?.id === route.id}
     />
    );
   })}
  </div>
 );
}
