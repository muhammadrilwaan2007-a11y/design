/**
 * RouteDetails.jsx
 * Displays detailed information about the currently selected route.
 *
 * Props:
 *  route       — RouteResponse | null
 *  index       — number (0-based index of the route in the routes array)
 *  incidentAnalysis  — RouteIncidentAnalysis | null (Module 4)
 *  incidentError   — string | null
 *  trafficSummary   — TrafficSummary | null
 *  featureData    — { route_safety_score, route_risk_category, segments } | null (Module 8)
 *  allRoutes    — Array of all RouteResponse objects
 *  allFeaturesData — Object containing featureData for all routes
 *  featuresLoading  — boolean
 *  featuresError   — string | null
 *  weather      — WeatherResponse | null
 *  weatherLoading   — boolean
 *  trafficLoading   — boolean
 *  incidentLoading  — boolean
 */

import { MapPin, Clock, ArrowRight, AlertTriangle, ShieldCheck, AlertOctagon, Sparkles, HelpCircle } from 'lucide-react';
import SafetyScoreCard  from '../Safety/SafetyScoreCard';
import SegmentSafetyList from '../Safety/SegmentSafetyList';
import LiveConditionsCard from '../Safety/LiveConditionsCard';
import AiRouteSummary from '../Safety/AiRouteSummary';

const ROUTE_COLORS = ['#2563EB', '#F59E0B', '#8B5CF6'];

function formatDistance(meters) {
 if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
 return `${Math.round(meters)} m`;
}

function formatDuration(seconds) {
 const mins = Math.round(seconds / 60);
 if (mins < 60) return `${mins} min`;
 const h = Math.floor(mins / 60);
 const m = mins % 60;
 return m > 0 ? `${h} h ${m} min` : `${h} h`;
}

/** Format a maneuver type into a readable instruction. */
function maneuverLabel(maneuver) {
 if (!maneuver?.type) return null;
 const type = maneuver.type.replace(/_/g, ' ');
 const modifier = maneuver.modifier ? ` ${maneuver.modifier}` : '';
 return (type + modifier).replace(/\b\w/g, (c) => c.toUpperCase());
}

function getIncidentEmoji(type) {
 const t = (type || '').toLowerCase();
 if (t.includes('accident'))  return '🚨';
 if (t.includes('road clos'))  return '🚧';
 if (t.includes('lane clos'))  return '⛔';
 if (t.includes('road work') || t.includes('roadwork')) return '🔨';
 if (t.includes('jam'))     return '🚗';
 if (t.includes('dangerous') || t.includes('flood')) return '⚠️';
 return '📍';
}

export default function RouteDetails({
 route,
 index = 0,
 incidentAnalysis,
 incidentError,
 trafficSummary,
 featureData,
 allRoutes = [],
 allFeaturesData = {},
 featuresLoading,
 featuresError,
 weather,
 weatherLoading,
 trafficLoading,
 incidentLoading,
 isSafest: _isSafest = false,
 safestRoute = null,
 safestScore = null,
 safestRouteIndex = 0,
 onSelectSafest = null,
 recommendation = null,
 onSelectRecommended = null,
 onToggleSimulatedClosure = null,
 isSimulatedClosed = false,
 onRetryFeatures = null,
 onOpenAiAssistant = null,
}) {
 if (!route) return null;

 const color   = ROUTE_COLORS[index] ?? ROUTE_COLORS[ROUTE_COLORS.length - 1];
 const routeLabel = `Route ${index + 1}`;

 // Filter steps: skip empty/depart/arrive-only entries for cleanliness
 const steps = (route.steps ?? []).filter(
  (s) => s.name || (s.maneuver?.type && s.maneuver.type !== 'depart'),
 );

 const relevantIncidents = incidentAnalysis?.incidents ?? [];

 // Extract recommendation properties
 const theoreticallySafestRoute = recommendation?.theoreticallySafestRoute ?? safestRoute;
 const theoreticallySafestScore = recommendation?.theoreticallySafestScore ?? safestScore;
 const theoreticallySafestIndex = recommendation?.theoreticallySafestIndex ?? safestRouteIndex;
 const isSafestRouteClosed = recommendation?.isSafestRouteClosed ?? false;
 const recommendedRoute = recommendation?.recommendedRoute ?? (isSafestRouteClosed ? null : theoreticallySafestRoute);
 const recommendedScore = recommendation?.recommendedScore ?? (isSafestRouteClosed ? null : theoreticallySafestScore);
 const recommendedIndex = recommendation?.recommendedIndex ?? (isSafestRouteClosed ? 0 : theoreticallySafestIndex);
 const isAlternativeRecommendation = recommendation?.isAlternativeRecommendation ?? false;

 const closureInfo = recommendation?.closureMap?.[route.id];
 const hasClosure = closureInfo?.hasClosure ?? false;
 const closureReason = closureInfo?.reason ?? null;

 const isCurrentRouteTheSafest = theoreticallySafestRoute?.id === route.id;
 const isCurrentRouteRecommended = recommendedRoute?.id === route.id;

 return (
  <div className="flex flex-col gap-3">
   {/* ── Header ─────────────────────────────────────────────────────── */}
   <div
    className="flex items-center gap-2 px-4 py-3 rounded-xl"
    style={{
     backgroundColor: hasClosure ? '#F43F5E18' : color + '14',
     borderLeft: `3px solid ${hasClosure ? '#E11D48' : color}`,
    }}
   >
    <span className="text-sm font-bold" style={{ color: hasClosure ? '#E11D48' : color }}>
     {routeLabel}
    </span>
    {hasClosure && (
     <span className="text-[10px] font-extrabold uppercase bg-rose-600 text-white px-2 py-0.5 rounded-full shadow-xs">
      Road Closed
     </span>
    )}
    <span className="ml-auto flex items-center gap-3 text-sm text-slate-700 dark:text-slate-200">
     <span className="flex items-center gap-1">
      <MapPin size={13} className="shrink-0" style={{ color: hasClosure ? '#E11D48' : color }} />
      {formatDistance(route.distance_meters)}
     </span>
     <span className="flex items-center gap-1">
      <Clock size={13} className="shrink-0" style={{ color: hasClosure ? '#E11D48' : color }} />
      {formatDuration(route.duration_seconds)}
     </span>
    </span>
   </div>

   {/* ── Road Closure Banner (Cannot Be Traveled) ── */}
   {hasClosure && (
    <div className="bg-rose-50 dark:bg-rose-950/50 border border-rose-300 dark:border-rose-800 rounded-xl p-3 flex flex-col gap-2.5 text-xs shadow-xs">
     <div className="flex items-start gap-2">
      <AlertOctagon size={18} className="text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1">
       <div className="flex items-center justify-between gap-1 flex-wrap">
        <span className="font-extrabold text-rose-900 dark:text-rose-200 text-xs">
         ⛔ Road Closed — Cannot Be Traveled
        </span>
        {isCurrentRouteTheSafest && theoreticallySafestScore != null && (
         <span className="text-[10px] font-bold text-rose-800 dark:text-rose-300 bg-rose-100 dark:bg-rose-900/60 px-2 py-0.5 rounded-full">
          Safest Score: {theoreticallySafestScore}/100
         </span>
        )}
       </div>
       <p className="text-rose-800 dark:text-rose-300/90 text-[11px] mt-1 leading-snug">
        {isCurrentRouteTheSafest
         ? `Although Route ${index + 1} has the highest historical safety score, an active road closure prevents travel on this corridor.`
         : `Route ${index + 1} is currently blocked by an active road closure and cannot be driven.`}
       </p>
       {closureReason && (
        <p className="text-rose-700 dark:text-rose-400 text-[10px] mt-0.5 font-medium">
         {closureReason}
        </p>
       )}
      </div>
     </div>

     {recommendedRoute && recommendedRoute.id !== route.id && onSelectRecommended && (
      <div className="flex items-center justify-between pt-1.5 border-t border-rose-200 dark:border-rose-800/60 flex-wrap gap-2">
       <span className="text-[11px] font-medium text-rose-900 dark:text-rose-200">
        Recommended alternative: <strong>Route {recommendedIndex + 1}</strong>
       </span>
       <button
        type="button"
        onClick={onSelectRecommended}
        className="inline-flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-[11px] px-3 py-1.5 rounded-lg transition-colors shadow-xs whitespace-nowrap"
       >
        <ShieldCheck size={13} />
        Switch to Route {recommendedIndex + 1}
       </button>
      </div>
     )}
    </div>
   )}

   {/* ── Case A: Passable Alternative Recommended Banner ── */}
   {!hasClosure && isAlternativeRecommendation && isCurrentRouteRecommended && (
    <div className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-300 dark:border-emerald-800 rounded-xl p-3 flex items-start gap-2.5 text-xs shadow-xs">
     <ShieldCheck size={18} className="text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
     <div className="min-w-0 flex-1">
      <div className="flex items-center justify-between gap-1 flex-wrap">
       <span className="font-bold text-emerald-900 dark:text-emerald-200 text-xs">
        🛡️ Recommended Alternative Route (Score: {recommendedScore ?? '—'}/100)
       </span>
       <span className="text-[10px] font-extrabold text-emerald-700 dark:text-emerald-300 bg-emerald-100 dark:bg-emerald-900/60 px-2 py-0.5 rounded-full">
        Safest Passable
       </span>
      </div>
      <p className="text-emerald-800 dark:text-emerald-300/90 text-[11px] mt-1 leading-snug">
       Route {theoreticallySafestIndex + 1} has a higher historical safety score ({theoreticallySafestScore ?? '—'}/100) but <strong>cannot be traveled due to an active road closure</strong>.
      </p>
      <p className="text-emerald-700 dark:text-emerald-300/80 text-[11px] mt-0.5 leading-snug">
       Route {index + 1} is recommended as your safest open, passable path.
      </p>
     </div>
    </div>
   )}

   {/* ── Case B: Standard Safest Route Banner (No Closures) ── */}
   {!hasClosure && !isAlternativeRecommendation && isCurrentRouteRecommended && recommendedScore != null && (
    <div className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-300 dark:border-emerald-800 rounded-xl p-2.5 flex items-center gap-2 text-xs shadow-xs">
     <ShieldCheck size={16} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
     <span className="font-semibold text-emerald-800 dark:text-emerald-200">
      Recommended Safest Route — Lowest historical accident risk among candidate paths.
     </span>
    </div>
   )}

   {/* ── Case C: Non-Recommended Route Alert ── */}
   {!hasClosure && !isCurrentRouteRecommended && recommendedRoute && recommendedScore != null && (
    <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-800 rounded-xl p-2.5 flex items-center justify-between gap-2 text-xs shadow-xs">
     <div className="flex items-center gap-1.5 min-w-0">
      <AlertTriangle size={15} className="text-amber-600 dark:text-amber-400 shrink-0" />
      <span className="text-amber-800 dark:text-amber-200 font-medium truncate">
       {isAlternativeRecommendation
        ? `Route ${recommendedIndex + 1} is recommended alternative (${recommendedScore}/100).`
        : `Route ${theoreticallySafestIndex + 1} is safer (${theoreticallySafestScore}/100 vs ${featureData?.route_safety_score ?? '—'}/100).`}
      </span>
     </div>
     {(onSelectRecommended || onSelectSafest) && (
      <button
       type="button"
       onClick={isAlternativeRecommendation ? onSelectRecommended : (onSelectSafest || onSelectRecommended)}
       className="bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-bold px-2.5 py-1 rounded-lg shrink-0 transition-colors shadow-xs whitespace-nowrap"
      >
       Switch to Route {recommendedIndex + 1}
      </button>
     )}
    </div>
   )}



   {/* ── AI Route Summary (GPT-OSS 120B) ── */}
   <AiRouteSummary
    route={route}
    featureData={featureData}
    allRoutes={allRoutes}
    allFeaturesData={allFeaturesData}
    incidentAnalysis={incidentAnalysis}
    trafficSummary={trafficSummary}
    weather={weather}
    onOpenChat={onOpenAiAssistant}
   />

   {/* ── Module 8: Safety Score Card ──────────────────────────────────── */}
   <SafetyScoreCard
    score={featureData?.route_safety_score ?? null}
    category={featureData?.route_risk_category ?? null}
    loading={featuresLoading}
    error={featuresError}
    onRetry={onRetryFeatures}
   />

   {/* ── Module 8: Segment-level Safety Scores ───────────────────────── */}
   <SegmentSafetyList
    segments={featureData?.segments ?? null}
    loading={featuresLoading}
   />

   {/* ── Live Conditions (SEPARATE from Safety Score) ─────────────────── */}
   <LiveConditionsCard
    weather={weather}
    trafficSummary={trafficSummary}
    incidentAnalysis={incidentAnalysis}
    weatherLoading={weatherLoading}
    trafficLoading={trafficLoading}
    incidentLoading={incidentLoading}
   />

   {/* ── Live Incidents detail list ────────────────────────────────────── */}
   <div>
    <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide px-1 mb-2 flex items-center gap-1.5">
     <AlertTriangle size={12} />
     Incident Details
    </p>

    {incidentError ? (
     <div className="px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 text-xs">
      ⚠️ Live incident data unavailable.
     </div>
    ) : !incidentAnalysis ? (
     <div className="px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-700/50 text-slate-400 text-xs">
      Loading incident data…
     </div>
    ) : relevantIncidents.length === 0 ? (
     <div className="px-3 py-2 rounded-lg bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 text-xs">
      ✅ No live incidents detected near this route.
     </div>
    ) : (
     <div className="space-y-1.5">
      <p className="text-xs font-medium text-red-600 dark:text-red-400 px-1">
       🚨 {relevantIncidents.length} incident{relevantIncidents.length !== 1 ? 's' : ''} near this route
      </p>
      <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
       {relevantIncidents.map((inc, i) => (
        <div
         key={`${inc.id}-${i}`}
         className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-800/30"
        >
         <span className="text-base shrink-0 mt-0.5">{getIncidentEmoji(inc.type)}</span>
         <div className="min-w-0">
          <p className="text-xs font-semibold text-slate-800 dark:text-slate-100">{inc.type}</p>
          {inc.road_name && (
           <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{inc.road_name}</p>
          )}
          {inc.description && inc.description !== inc.type && (
           <p className="text-xs text-slate-400 dark:text-slate-500 truncate">{inc.description}</p>
          )}
          {inc.distance_to_route_m != null && (
           <p className="text-xs text-slate-400 mt-0.5">
            📌 {Math.round(inc.distance_to_route_m)} m from route
           </p>
          )}
         </div>
        </div>
       ))}
      </div>
     </div>
    )}
   </div>

   {/* ── Steps ──────────────────────────────────────────────────────── */}
   {steps.length > 0 && (
    <div>
     <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide px-1 mb-2">
      Route steps
     </p>
     <div className="space-y-1 max-h-52 overflow-y-auto pr-1">
      {steps.map((step, i) => {
       const instruction = maneuverLabel(step.maneuver);
       return (
        <div
         key={i}
         className="flex items-start gap-2 px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-700/50"
        >
         <ArrowRight
          size={13}
          className="mt-0.5 shrink-0 text-slate-400 dark:text-slate-500"
         />
         <div className="min-w-0">
          {instruction && (
           <p className="text-xs text-slate-500 dark:text-slate-400">
            {instruction}
           </p>
          )}
          <p className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">
           {step.name || 'Unnamed road'}
          </p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
           {formatDistance(step.distance)} · {formatDuration(step.duration)}
          </p>
         </div>
        </div>
       );
      })}
     </div>
    </div>
   )}

   {/* ── Ask SafeRoute AI Trigger Button ── */}
   {onOpenAiAssistant && (
    <button
     type="button"
     onClick={onOpenAiAssistant}
     className="w-full flex items-center justify-center gap-2 p-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white font-semibold text-xs transition-all duration-200 shadow-md hover:shadow-lg group"
    >
     <Sparkles size={15} className="group-hover:rotate-12 transition-transform" />
     <span>Ask SafeRoute AI About This Route</span>
    </button>
   )}
  </div>
 );
}
