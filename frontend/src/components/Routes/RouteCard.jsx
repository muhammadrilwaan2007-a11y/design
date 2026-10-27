/**
 * RouteCard.jsx
 * Displays a single candidate route's summary information.
 *
 * Props:
 *  route     — RouteResponse
 *  index     — number (0-based, used for colour dot)
 *  isSelected   — boolean
 *  onSelect    — () => void
 *  trafficSummary — TrafficSummary | null
 *  incidentFeatures — IncidentFeatures | null
 *  safetyScore  — number | null (backend: route_safety_score)
 *  riskCategory  — string | null (backend: route_risk_category)
 *  featuresLoading — boolean
 */

import { Navigation, ShieldCheck, AlertOctagon } from 'lucide-react';
import { getTrafficColor, getTrafficLabel } from '../Map/TrafficLayer';

// Match the colour palette used in RouteLayer.jsx
const ROUTE_COLORS = ['#2563EB', '#2563EB', '#2563EB'];

/** Convert metres to a display string: "8.5 km" or "450 m" */
function formatDistance(meters) {
 if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
 return `${Math.round(meters)} m`;
}

/** Convert seconds to a display string: "18 min" or "1 h 5 min" */
function formatDuration(seconds) {
 const mins = Math.round(seconds / 60);
 if (mins < 60) return `${mins} min`;
 const h = Math.floor(mins / 60);
 const m = mins % 60;
 return m > 0 ? `${h} h ${m} min` : `${h} h`;
}

// Score → badge color
function getScoreColor(score, category) {
 const cat = category?.toLowerCase();
 if (cat === 'low'  || score >= 70) return '#16A34A';
 if (cat === 'medium' || score >= 40) return '#D97706';
 if (cat === 'high'  || score >= 0) return '#DC2626';
 return '#9CA3AF';
}

export default function RouteCard({
 route,
 index,
 isSelected,
 onSelect,
 trafficSummary,
 incidentFeatures,
 safetyScore,
 riskCategory,
 featuresLoading,
 isSafest = false,
 isSafestClosed: _isSafestClosed = false,
 isRecommendedAlternative = false,
 isRecommended = false,
 hasRoadClosure = false,
 closureReason = null,
 isFastest = false,
}) {
 const color = ROUTE_COLORS[index] ?? ROUTE_COLORS[ROUTE_COLORS.length - 1];
 const routeLabel = `Route ${index + 1}`;
 const isHighlighted = (isRecommended || isRecommendedAlternative) && !hasRoadClosure;

 const cardBorderClass = () => {
  if (isSelected) {
   if (hasRoadClosure) return 'border-rose-500 shadow-md ring-1 ring-rose-500/30 scale-[1.01]';
   if (isHighlighted) return 'border-emerald-500 shadow-md ring-1 ring-emerald-500/30 scale-[1.01]';
   return 'border-primary-500 shadow-md ring-1 ring-primary-500/30 scale-[1.01]';
  }
  if (hasRoadClosure) {
   return 'border-rose-300 dark:border-rose-900/60 bg-rose-50/20 dark:bg-rose-950/20 hover:shadow-md';
  }
  if (isHighlighted) {
   return 'border-emerald-300 dark:border-emerald-700/80 bg-emerald-50/20 dark:bg-emerald-950/10 hover:shadow-md';
  }
  return 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:shadow-md hover:scale-[1.005]';
 };

 const hasTopRibbon = hasRoadClosure || isRecommended || isRecommendedAlternative || isFastest;

 return (
  <button
   type="button"
   id={`route-card-${route.id}`}
   onClick={onSelect}
   aria-pressed={isSelected}
   aria-label={`${routeLabel}: ${formatDistance(route.distance_meters)}, ${formatDuration(route.duration_seconds)}`}
   className={[
    'w-full text-left rounded-xl border transition-all duration-150 group relative overflow-hidden',
    'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1',
    cardBorderClass(),
   ].join(' ')}
   style={
    isSelected
     ? hasRoadClosure
      ? { backgroundColor: '#F43F5E12', borderColor: '#F43F5E' }
      : isHighlighted
       ? { backgroundColor: '#10B98118', borderColor: '#10B981' }
       : { backgroundColor: color + '12', borderColor: color }
     : {}
   }
  >
   {/* ── Recommendation / Road Closure Ribbon ── */}
   {hasTopRibbon && (
    <div className="px-4 pt-2 flex flex-wrap items-center gap-1.5">
     {hasRoadClosure ? (
      <>
       <span className="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider bg-rose-600 text-white px-2 py-0.5 rounded-full shadow-xs">
        <AlertOctagon size={11} />
        ⛔ Road Closed (Cannot Travel)
       </span>
       {isSafest && (
        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-rose-800 dark:text-rose-200 bg-rose-100 dark:bg-rose-900/60 px-2 py-0.5 rounded-full">
         Safest Historical Score ({safetyScore ?? '—'}/100)
        </span>
       )}
      </>
     ) : isRecommendedAlternative ? (
      <span className="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider bg-emerald-600 text-white px-2 py-0.5 rounded-full shadow-xs">
       <ShieldCheck size={11} />
       🛡️ Recommended Alternative (Safest Passable)
      </span>
     ) : isRecommended ? (
      <span className="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider bg-emerald-600 text-white px-2 py-0.5 rounded-full shadow-xs">
       <ShieldCheck size={11} />
       Recommended (Safest Route)
      </span>
     ) : null}

     {isFastest && !isRecommended && !isRecommendedAlternative && !hasRoadClosure && (
      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-indigo-700 dark:text-indigo-300 bg-indigo-100/80 dark:bg-indigo-900/50 px-2 py-0.5 rounded-full">
       ⚡ Fastest Route
      </span>
     )}
    </div>
   )}

   <div className={`px-4 ${hasTopRibbon ? 'pt-1.5 pb-2.5' : 'py-3'} flex items-center gap-3`}>
    {/* Colour dot */}
    <span
     className="w-3 h-3 rounded-full shrink-0 ring-2 ring-white dark:ring-slate-800 shadow"
     style={{
      backgroundColor: hasRoadClosure
       ? '#F43F5E'
       : isHighlighted
        ? '#10B981'
        : color,
     }}
     aria-hidden="true"
    />

    {/* Label */}
    <span
     className="text-sm font-semibold"
     style={{
      color: isSelected
       ? hasRoadClosure
        ? '#E11D48'
        : isHighlighted
         ? '#059669'
         : color
       : undefined,
     }}
    >
     {routeLabel}
    </span>

    {/* Stats */}
    <span className="ml-auto flex items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
     <span className="font-medium">{formatDistance(route.distance_meters)}</span>
     <span className="text-slate-400 dark:text-slate-500">·</span>
     <span>{formatDuration(route.duration_seconds)}</span>
    </span>

    {/* Safety Score compact badge */}
    {featuresLoading ? (
     <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-slate-100 animate-pulse">
      <ShieldCheck size={11} className="text-slate-300" />
      <span className="w-5 h-3 bg-slate-200 rounded" />
     </span>
    ) : safetyScore !== null && safetyScore !== undefined ? (
     <span
      className="flex items-center gap-1 px-1.5 py-0.5 rounded-md text-white text-[11px] font-bold shrink-0 shadow-xs"
      style={{ backgroundColor: getScoreColor(safetyScore, riskCategory) }}
      title={`Safety Score: ${safetyScore}/100 (${riskCategory ?? 'unknown'} risk)`}
     >
      <ShieldCheck size={10} />
      {safetyScore}
     </span>
    ) : null}

    {/* Arrow indicator */}
    <Navigation
     size={14}
     className="shrink-0 text-slate-400 dark:text-slate-500 group-hover:text-primary-500 transition-colors"
     style={
      isSelected
       ? { color: hasRoadClosure ? '#E11D48' : isHighlighted ? '#10B981' : color }
       : {}
     }
    />
   </div>

   {/* Road closure warning row if detected */}
   {hasRoadClosure && (
    <div className="px-4 pb-2.5 flex items-center gap-1.5 text-xs text-rose-700 dark:text-rose-300 border-t border-rose-100 dark:border-rose-900/50 pt-2 ml-10 font-medium">
     <AlertOctagon size={13} className="shrink-0 text-rose-600 dark:text-rose-400" />
     <span className="truncate">
      {closureReason || 'Active road closure: cannot be travelled'}
     </span>
    </div>
   )}

   {/* Traffic Summary block */}
   {trafficSummary && (
    <div className="px-4 pb-2 flex items-center gap-3 text-xs border-t border-slate-100 dark:border-slate-700/50 pt-2 ml-10">
     <span className="font-medium text-slate-600 dark:text-slate-300">
      Traffic: <span style={{ color: getTrafficColor(trafficSummary.average_congestion) }}>{getTrafficLabel(trafficSummary.average_congestion)}</span>
     </span>
     {trafficSummary.average_delay_seconds > 0 && (
      <>
       <span className="text-slate-300 dark:text-slate-600">|</span>
       <span className="text-slate-500 dark:text-slate-400">
        Delay: <span className="text-amber-600 dark:text-amber-400">+{Math.ceil(trafficSummary.average_delay_seconds / 60)} min</span>
       </span>
      </>
     )}
    </div>
   )}

   {/* Incident Summary block */}
   {incidentFeatures && incidentFeatures.incident_count > 0 && (
    <div className="px-4 pb-3 flex flex-wrap items-center gap-2 text-xs border-t border-slate-100 dark:border-slate-700/50 pt-2 ml-10">
     <span className="font-medium text-red-600 dark:text-red-400">
      🚨 Live incidents: {incidentFeatures.incident_count}
     </span>
     {incidentFeatures.accident_count > 0 && (
      <span className="bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-1.5 py-0.5 rounded">
       Accident: {incidentFeatures.accident_count}
      </span>
     )}
     {incidentFeatures.roadwork_count > 0 && (
      <span className="bg-orange-50 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 px-1.5 py-0.5 rounded">
       Roadworks: {incidentFeatures.roadwork_count}
      </span>
     )}
     {incidentFeatures.road_closure_count > 0 && (
      <span className="bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300 px-1.5 py-0.5 rounded font-semibold">
       Road closed: {incidentFeatures.road_closure_count}
      </span>
     )}
     {incidentFeatures.traffic_jam_incident_count > 0 && (
      <span className="bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 px-1.5 py-0.5 rounded">
       Jam: {incidentFeatures.traffic_jam_incident_count}
      </span>
     )}
    </div>
   )}
   {incidentFeatures && incidentFeatures.incident_count === 0 && !hasRoadClosure && (
    <div className="px-4 pb-3 text-xs text-slate-400 dark:text-slate-500 border-t border-slate-100 dark:border-slate-700/50 pt-2 ml-10">
     ✅ No live incidents
    </div>
   )}
  </button>
 );
}
