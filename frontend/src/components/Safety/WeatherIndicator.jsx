/**
 * frontend/src/components/Safety/WeatherIndicator.jsx
 * Module 5 — Weather & Time Analysis
 *
 * A compact floating card displaying current weather and time context.
 * Shows FACTUAL information only — no safety score, no route ranking.
 * Factual advisories (e.g. "Moderate rain may affect driving conditions.")
 * are provided as context, not risk verdicts.
 *
 * Props:
 *  weather — WeatherResponse | null
 *  loading — boolean
 *  error  — string | null
 *  onRefresh — () => void
 */

import { RefreshCw } from 'lucide-react';

// ── Weather icon mapping ────────────────────────────────────────────────────

function getWeatherEmoji(weatherMain, weatherId) {
 if (!weatherMain) return '🌤️';
 const m = weatherMain.toLowerCase();
 if (m === 'thunderstorm')       return '⛈️';
 if (m === 'drizzle')         return '🌦️';
 if (m === 'rain') {
  if (weatherId >= 502)        return '🌧️';
  return '🌦️';
 }
 if (m === 'snow')           return '❄️';
 if (m === 'mist' || m === 'fog')   return '🌫️';
 if (m === 'haze' || m === 'smoke')  return '😶‍🌫️';
 if (m === 'dust' || m === 'sand')   return '🌪️';
 if (m === 'clouds') {
  if (weatherId === 801)       return '🌤️';
  if (weatherId === 802)       return '⛅';
  return '☁️';
 }
 if (m === 'clear')          return '☀️';
 return '🌤️';
}

function getTimePeriodEmoji(period, isNight) {
 if (isNight)       return '🌙';
 if (period === 'early_morning') return '🌅';
 if (period === 'morning') return '🌄';
 if (period === 'afternoon') return '☀️';
 if (period === 'evening') return '🌆';
 return '🌙';
}

function formatVisibility(meters) {
 if (meters == null) return null;
 if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
 return `${meters} m`;
}

function getAdvisory(features) {
 if (!features) return null;
 const lines = [];
 if (features.is_heavy_rain)  lines.push('Heavy rain may significantly reduce visibility.');
 else if (features.is_raining) lines.push(`${features.rain_classification} may affect driving conditions.`);
 if (features.is_low_visibility && !features.is_raining)
  lines.push('Low visibility — drive carefully.');
 if (features.is_strong_wind)  lines.push('Strong winds reported in the area.');
 if (features.is_night)     lines.push('Night-time — reduced visibility expected.');
 return lines.length > 0 ? lines[0] : null; // Show only the most important one
}

// ── Component ────────────────────────────────────────────────────────────────

export default function WeatherIndicator({ weather, loading, _error, onRefresh }) {

 // ── Loading state ─────────────────────────────────────────────────────────
 if (loading && !weather) {
  return (
   <div className="
    flex items-center gap-2 px-3 py-2
    bg-white/90 dark:bg-slate-800/90 backdrop-blur-sm
    border border-slate-200 dark:border-slate-700
    rounded-xl shadow-card text-xs text-slate-500 dark:text-slate-400
   ">
    <RefreshCw size={12} className="animate-spin" />
    <span>Fetching weather…</span>
   </div>
  );
 }

 // ── Error / unavailable ───────────────────────────────────────────────────
 if (!weather || weather.available === false) {
  return (
   <div className="
    flex items-center gap-2 px-3 py-2
    bg-white/90 dark:bg-slate-800/90 backdrop-blur-sm
    border border-slate-200 dark:border-slate-700
    rounded-xl shadow-card text-xs text-slate-400 dark:text-slate-500
   ">
    <span>🌐</span>
    <span>Weather unavailable</span>
    {onRefresh && (
     <button onClick={onRefresh} className="ml-1 hover:text-primary-500 transition-colors">
      <RefreshCw size={10} />
     </button>
    )}
   </div>
  );
 }

 const { weather: w, time, features } = weather;
 const cond   = w?.weather;
 const emoji  = getWeatherEmoji(cond?.main, cond?.id);
 const advisory = getAdvisory(features);

 return (
  <div className="
   bg-white/95 dark:bg-slate-800/95 backdrop-blur-sm
   border border-slate-200 dark:border-slate-700
   rounded-xl shadow-card p-3
   min-w-[200px] max-w-[240px]
   text-xs
  ">
   {/* ── Header row ─────────────────────────────────────────────────── */}
   <div className="flex items-center justify-between mb-2">
    <div className="flex items-center gap-1.5">
     <span className="text-lg leading-none">{emoji}</span>
     <div>
      <p className="font-semibold text-slate-800 dark:text-slate-100 capitalize leading-tight">
       {cond?.description || cond?.main || 'Clear'}
      </p>
      {w?.temperature_c != null && (
       <p className="text-slate-500 dark:text-slate-400 leading-tight">
        {Math.round(w.temperature_c)}°C
        {w.humidity_percent != null && ` · ${w.humidity_percent}% humidity`}
       </p>
      )}
     </div>
    </div>
    {onRefresh && (
     <button
      onClick={onRefresh}
      disabled={loading}
      title="Refresh weather"
      className="text-slate-400 hover:text-primary-500 transition-colors disabled:opacity-40"
     >
      <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
     </button>
    )}
   </div>

   {/* ── Stats row ──────────────────────────────────────────────────── */}
   <div className="flex flex-wrap gap-x-3 gap-y-1 text-slate-500 dark:text-slate-400 mb-2">
    {formatVisibility(w?.visibility_m) && (
     <span>👁️ {formatVisibility(w.visibility_m)}</span>
    )}
    {w?.wind_speed_ms != null && (
     <span>💨 {w.wind_speed_ms.toFixed(1)} m/s</span>
    )}
    {w?.cloudiness_percent != null && (
     <span>☁️ {w.cloudiness_percent}%</span>
    )}
   </div>

   {/* ── Time row ───────────────────────────────────────────────────── */}
   {time && (
    <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 border-t border-slate-100 dark:border-slate-700 pt-2">
     <span>{getTimePeriodEmoji(time.time_period, time.is_night)}</span>
     <span>{time.local_time_str}</span>
     {time.is_rush_hour && (
      <span className="ml-auto bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 px-1.5 py-0.5 rounded text-[10px] font-medium">
       🚦 Rush hour
      </span>
     )}
    </div>
   )}

   {/* ── Advisory (factual only) ─────────────────────────────────────── */}
   {advisory && (
    <p className="mt-2 text-[10px] text-slate-400 dark:text-slate-500 italic border-t border-slate-100 dark:border-slate-700 pt-1.5">
     ℹ️ {advisory}
    </p>
   )}
  </div>
 );
}
