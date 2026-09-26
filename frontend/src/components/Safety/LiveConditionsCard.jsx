/**
 * frontend/src/components/Safety/LiveConditionsCard.jsx
 * Displays live traffic, incidents, and weather as contextual alerts.
 *
 * ARCHITECTURE RULE: This card is COMPLETELY SEPARATE from the Safety Score.
 * It MUST NOT display anything that implies the Safety Score was changed by
 * live conditions. Do not render "Safety Score reduced because of rain" etc.
 *
 * Props:
 *  weather     — WeatherResponse | null (from useWeather)
 *  trafficSummary — TrafficSummary | null  (from useTraffic, route-specific)
 *  incidentAnalysis — RouteIncidentAnalysis | null (from useIncidents, route-specific)
 *  weatherLoading — boolean
 *  trafficLoading — boolean
 *  incidentLoading — boolean
 */

import { motion } from 'framer-motion';
import { Radio } from 'lucide-react';

// ── Weather helpers ────────────────────────────────────────────────────────────
function getWeatherLines(weather) {
 if (!weather || weather.available === false) return [];
 const lines = [];
 const f   = weather.features;
 const w   = weather.weather?.weather;

 if (f?.is_heavy_rain) lines.push({ icon: '🌧️', text: 'Heavy rain along this route', severity: 'warn' });
 else if (f?.is_raining) {
  // Describe imminence — if condition is "drizzle" or light rain
  const desc = w?.description?.toLowerCase() || '';
  if (desc.includes('drizzle') || desc.includes('light')) {
   lines.push({ icon: '🌦️', text: 'Light drizzle in the area', severity: 'info' });
  } else {
   lines.push({ icon: '🌧️', text: 'Rain in the area', severity: 'info' });
  }
 }
 if (f?.is_low_visibility) lines.push({ icon: '🌫️', text: 'Reduced visibility', severity: 'warn' });
 if (f?.is_strong_wind)  lines.push({ icon: '💨', text: 'Strong winds reported', severity: 'info' });
 if (f?.is_night)     lines.push({ icon: '🌙', text: 'Night-time driving conditions', severity: 'info' });

 // If nothing flagged but weather is available
 if (lines.length === 0 && weather.available !== false) {
  const desc = w?.description;
  lines.push({ icon: '☀️', text: desc ? `${desc.charAt(0).toUpperCase()}${desc.slice(1)}` : 'Clear conditions', severity: 'ok' });
 }
 return lines;
}

// ── Traffic helpers ────────────────────────────────────────────────────────────
function getTrafficLines(trafficSummary) {
 if (!trafficSummary) return [];
 const lines = [];
 const cong = trafficSummary.average_congestion ?? 0;

 if (cong >= 0.7)    lines.push({ icon: '🚗', text: 'Heavy traffic on this route', severity: 'warn' });
 else if (cong >= 0.4) lines.push({ icon: '🚗', text: 'Moderate traffic', severity: 'info' });
 else          lines.push({ icon: '🚗', text: 'Light traffic', severity: 'ok' });

 if (trafficSummary.average_delay_seconds > 60) {
  const mins = Math.ceil(trafficSummary.average_delay_seconds / 60);
  lines.push({ icon: '⏱️', text: `Traffic delay: ~${mins} min`, severity: 'warn' });
 }
 return lines;
}

// ── Incident helpers ───────────────────────────────────────────────────────────
function getIncidentLines(incidentAnalysis) {
 if (!incidentAnalysis) return [];
 const lines = [];
 const f   = incidentAnalysis.features;

 if (!f || f.incident_count === 0) {
  lines.push({ icon: '✅', text: 'No active incidents', severity: 'ok' });
  return lines;
 }
 if (f.accident_count > 0)      lines.push({ icon: '🚨', text: `${f.accident_count} accident${f.accident_count > 1 ? 's' : ''} nearby`, severity: 'warn' });
 if (f.road_closure_count > 0)    lines.push({ icon: '🚧', text: `${f.road_closure_count} road closure${f.road_closure_count > 1 ? 's' : ''}`, severity: 'warn' });
 if (f.roadwork_count > 0)      lines.push({ icon: '🔨', text: `${f.roadwork_count} roadwork zone${f.roadwork_count > 1 ? 's' : ''}`, severity: 'info' });
 if (f.traffic_jam_incident_count > 0) lines.push({ icon: '🚗', text: `${f.traffic_jam_incident_count} traffic jam${f.traffic_jam_incident_count > 1 ? 's' : ''} reported`, severity: 'info' });
 return lines;
}

// ── Row severity colour ────────────────────────────────────────────────────────
const SEVERITY_STYLES = {
 ok:  'text-green-700',
 info: 'text-slate-600',
 warn: 'text-amber-700',
};

function ConditionRow({ icon, text, severity = 'info' }) {
 return (
  <div className={`flex items-center gap-2 text-xs ${SEVERITY_STYLES[severity]}`}>
   <span className="text-sm leading-none shrink-0">{icon}</span>
   <span>{text}</span>
  </div>
 );
}

// ── Section ────────────────────────────────────────────────────────────────────
function Section({ title, lines, loading, emptyText }) {
 return (
  <div>
   <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
    {title}
   </p>
   {loading ? (
    <div className="flex items-center gap-1.5 animate-pulse">
     <div className="w-4 h-3 bg-slate-200 rounded" />
     <div className="h-3 w-24 bg-slate-200 rounded" />
    </div>
   ) : lines.length === 0 ? (
    <p className="text-xs text-slate-400 italic">{emptyText}</p>
   ) : (
    <div className="space-y-1">
     {lines.map((l, i) => (
      <ConditionRow key={i} {...l} />
     ))}
    </div>
   )}
  </div>
 );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function LiveConditionsCard({
 weather,
 trafficSummary,
 incidentAnalysis,
 weatherLoading = false,
 trafficLoading = false,
 incidentLoading = false,
}) {
 const weatherLines = getWeatherLines(weather);
 const trafficLines = getTrafficLines(trafficSummary);
 const incidentLines = getIncidentLines(incidentAnalysis);

 const anyLoading = weatherLoading || trafficLoading || incidentLoading;
 const anyData  = weather || trafficSummary || incidentAnalysis;

 if (!anyLoading && !anyData) return null;

 return (
  <motion.div
   initial={{ opacity: 0, y: 6 }}
   animate={{ opacity: 1, y: 0 }}
   transition={{ duration: 0.3, ease: 'easeOut', delay: 0.1 }}
   className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden"
   aria-label="Live route conditions"
  >
   {/* Header */}
   <div className="flex items-center gap-2 px-4 py-2.5 bg-slate-50 border-b border-slate-100">
    <Radio size={13} className="text-slate-400" />
    <span className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
     Live Conditions
    </span>
    <span className="ml-auto text-[10px] text-slate-400">
     Does not affect Safety Score
    </span>
   </div>

   {/* Body */}
   <div className="px-4 py-3 space-y-3">
    <Section
     title="Weather"
     lines={weatherLines}
     loading={weatherLoading && !weather}
     emptyText="Weather data unavailable"
    />
    <div className="border-t border-slate-100" />
    <Section
     title="Traffic"
     lines={trafficLines}
     loading={trafficLoading && !trafficSummary}
     emptyText="Traffic data unavailable"
    />
    <div className="border-t border-slate-100" />
    <Section
     title="Incidents"
     lines={incidentLines}
     loading={incidentLoading && !incidentAnalysis}
     emptyText="Incident data unavailable"
    />
   </div>
  </motion.div>
 );
}
