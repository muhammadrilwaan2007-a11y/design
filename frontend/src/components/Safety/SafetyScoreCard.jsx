/**
 * frontend/src/components/Safety/SafetyScoreCard.jsx
 * Module 8 — Safety Score display card.
 *
 * Renders the XGBoost-derived Safety Score as a circular ring gauge
 * with animated fill, a score counter, risk category label, and an
 * expandable "Why this score?" explainability section.
 *
 * ARCHITECTURE RULES (enforced here):
 * ─────────────────────────────────────
 * 1. Score values come ONLY from backend props (route_safety_score, route_risk_category).
 *  No calculation is performed in this component.
 * 2. Live conditions (weather, traffic, incidents) are NOT accepted as props here.
 *  They belong in LiveConditionsCard.
 * 3. The wording "Based on historical accident patterns and road characteristics"
 *  is required by spec — do NOT change it to a probability statement.
 *
 * Props:
 *  score  — number | null (backend: route_safety_score, 0-100)
 *  category — string | null (backend: route_risk_category: "low"|"medium"|"high")
 *  loading — boolean
 *  error  — string | null
 */

import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { ShieldCheck, RotateCw } from 'lucide-react';

// ── Score → visual config ──────────────────────────────────────────────────────
function getScoreVisuals(score, category) {
 // Drive from backend category where possible; fall back to score range
 const cat = category?.toLowerCase();
 if (cat === 'low'  || score >= 70) return { color: '#16A34A', label: 'Low Risk',   ring: '#16A34A', bg: '#F0FDF4' };
 if (cat === 'medium' || score >= 40) return { color: '#D97706', label: 'Moderate Risk', ring: '#D97706', bg: '#FFFBEB' };
 if (cat === 'high'  || score >= 0) return { color: '#DC2626', label: 'Higher Risk',  ring: '#DC2626', bg: '#FEF2F2' };
 return { color: '#6B7280', label: 'Risk Unknown', ring: '#6B7280', bg: '#F9FAFB' };
}

// ── SVG circular progress ring ─────────────────────────────────────────────────
const RADIUS = 44;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function ScoreRing({ _score, color, animatedScore }) {
 const pct   = Math.max(0, Math.min(100, animatedScore)) / 100;
 const offset = CIRCUMFERENCE * (1 - pct);

 return (
  <svg width="120" height="120" viewBox="0 0 120 120" aria-hidden="true">
   {/* Track */}
   <circle
    cx="60" cy="60" r={RADIUS}
    fill="none"
    stroke="#E2E8F0"
    strokeWidth="10"
   />
   {/* Animated fill */}
   <circle
    cx="60" cy="60" r={RADIUS}
    fill="none"
    stroke={color}
    strokeWidth="10"
    strokeLinecap="round"
    strokeDasharray={CIRCUMFERENCE}
    strokeDashoffset={offset}
    transform="rotate(-90 60 60)"
    style={{ transition: 'stroke-dashoffset 1s cubic-bezier(0.4,0,0.2,1), stroke 0.3s' }}
   />
  </svg>
 );
}

// ── Animated counter ───────────────────────────────────────────────────────────
function useCountUp(target, duration = 1000) {
 const [value, setValue] = useState(0);
 const raf = useRef(null);

 useEffect(() => {
  if (target === null || target === undefined) { setValue(0); return; }
  const start   = performance.now();
  const startVal = 0;
  const endVal  = target;

  function step(now) {
   const elapsed = now - start;
   const progress = Math.min(elapsed / duration, 1);
   // ease-out cubic
   const eased  = 1 - Math.pow(1 - progress, 3);
   setValue(Math.round(startVal + (endVal - startVal) * eased));
   if (progress < 1) raf.current = requestAnimationFrame(step);
  }

  raf.current = requestAnimationFrame(step);
  return () => cancelAnimationFrame(raf.current);
 }, [target, duration]);

 return value;
}

// ── Skeleton loader ────────────────────────────────────────────────────────────
function ScoreSkeleton() {
 return (
  <div className="flex flex-col items-center gap-3 py-2 animate-pulse">
   <div className="w-[120px] h-[120px] rounded-full bg-slate-200" />
   <div className="h-3 w-28 rounded bg-slate-200" />
   <div className="h-2 w-40 rounded bg-slate-100" />
  </div>
 );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function SafetyScoreCard({ score, category, loading, error, onRetry }) {
 const animatedScore      = useCountUp(score ?? 0);

 // While backend score hasn't arrived yet, show 0 in the ring
 const displayScore = score ?? 0;
 const visuals   = getScoreVisuals(displayScore, category);

 // ── Loading ──────────────────────────────────────────────────────────────────
 if (loading) {
  return (
   <div
    className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm p-4"
    aria-label="Safety score loading"
   >
    <div className="flex items-center justify-between mb-3">
     <div className="flex items-center gap-2">
      <ShieldCheck size={15} className="text-primary-500 animate-pulse" />
      <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
       Safety Score
      </span>
     </div>
     <span className="text-[11px] text-slate-400 animate-pulse">
      Analyzing safety risk…
     </span>
    </div>
    <ScoreSkeleton />
   </div>
  );
 }

 // ── Error / Score unavailable ─────────────────────────────────────────────────
 if (error || score === null || score === undefined) {
  return (
   <div
    className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm p-4"
    aria-label="Safety score unavailable"
   >
    <div className="flex items-center justify-between gap-2 mb-2">
     <div className="flex items-center gap-2">
      <ShieldCheck size={15} className="text-slate-400 dark:text-slate-500" />
      <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
       Safety Score
      </span>
     </div>
     {onRetry && (
      <button
       type="button"
       onClick={onRetry}
       className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 hover:underline"
       title="Retry safety score analysis"
      >
       <RotateCw size={11} />
       Retry
      </button>
     )}
    </div>
    <p className="text-xs text-slate-400 dark:text-slate-500 italic mb-2">
     {error
      ? error.includes('service') || error.includes('timed out') || error.includes('failed')
       ? 'Safety score temporarily unavailable. Click retry to analyze.'
       : error
      : 'Safety score unavailable'}
    </p>
    {onRetry && (
     <button
      type="button"
      onClick={onRetry}
      className="w-full mt-1 py-1.5 px-3 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 text-xs font-medium flex items-center justify-center gap-1.5 transition-colors shadow-xs"
     >
      <RotateCw size={12} />
      Calculate Safety Score
     </button>
    )}
   </div>
  );
 }

 // ── Normal render ────────────────────────────────────────────────────────────
 return (
  <motion.div
   initial={{ opacity: 0, y: 8 }}
   animate={{ opacity: 1, y: 0 }}
   transition={{ duration: 0.35, ease: 'easeOut' }}
   className="rounded-xl border bg-white shadow-sm overflow-hidden"
   style={{ borderColor: visuals.color + '40' }}
   aria-label={`Safety score: ${score} out of 100, ${visuals.label}`}
  >
   {/* Header */}
   <div
    className="flex items-center gap-2 px-4 py-2.5 border-b"
    style={{ backgroundColor: visuals.bg, borderColor: visuals.color + '25' }}
   >
    <ShieldCheck size={14} style={{ color: visuals.color }} />
    <span
     className="text-xs font-semibold uppercase tracking-wide"
     style={{ color: visuals.color }}
    >
     Safety Score
    </span>
    <span className="ml-auto text-[10px] text-slate-400 font-medium">
     Risk Model
    </span>
   </div>

   {/* Ring + Score */}
   <div className="flex flex-col items-center px-4 pt-4 pb-3 gap-1">
    <div className="relative w-[120px] h-[120px] flex items-center justify-center">
     <ScoreRing score={displayScore} color={visuals.ring} animatedScore={animatedScore} />
     {/* Score overlay */}
     <div className="absolute inset-0 flex flex-col items-center justify-center">
      <span
       className="text-3xl font-bold leading-none tabular-nums"
       style={{ color: visuals.color }}
      >
       {animatedScore}
      </span>
      <span className="text-[10px] text-slate-400 font-medium">/100</span>
     </div>
    </div>

    {/* Category label */}
    <p
     className="text-sm font-semibold mt-1"
     style={{ color: visuals.color }}
    >
     {visuals.label}
    </p>

    {/* Explanation */}
    <p className="text-[11px] text-slate-400 text-center leading-relaxed px-2 pb-1">
     Based on historical accident patterns and road characteristics.
    </p>
   </div>
  </motion.div>
 );
}
