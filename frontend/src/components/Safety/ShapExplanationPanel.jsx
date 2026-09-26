/**
 * frontend/src/components/Safety/ShapExplanationPanel.jsx
 * ==========================================================
 * Local SHAP Explanation Panel — SafeRoute AI
 *
 * Renders why the XGBoost model produced a specific risk
 * prediction for a clicked OSM road edge on the heatmap.
 *
 * IMPORTANT DESIGN RULES:
 * ────────────────────────
 * 1. SHAP values are in model log-odds space — NOT probability percentages.
 *  Do NOT display shap_value as a percentage.
 *  Do NOT say "increased risk by X%".
 * 2. Use directional language: "pushed risk higher" / "pushed risk lower".
 * 3. SHAP is an explanation only — never modify Safety Score from here.
 * 4. Keep Risk section and Live Conditions section SEPARATE.
 *
 * Props:
 *  explanation — ShapExplanation object from API | null
 *  loading   — boolean
 *  error    — string | null
 *  edge     — OSMHeatmapEdge object | null (for header info)
 *  onClose   — function | null (close callback)
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronDown, ChevronUp, TrendingUp, TrendingDown, Minus, Info } from 'lucide-react';

// ── Direction config ───────────────────────────────────────────────────────────
const DIRECTION_CONFIG = {
 higher_risk: {
  icon: TrendingUp,
  color: '#EF4444',
  bg: 'rgba(239,68,68,0.08)',
  border: 'rgba(239,68,68,0.2)',
  label: 'pushed risk higher',
  arrow: '↑',
 },
 lower_risk: {
  icon: TrendingDown,
  color: '#10B981',
  bg: 'rgba(16,185,129,0.08)',
  border: 'rgba(16,185,129,0.2)',
  label: 'pushed risk lower',
  arrow: '↓',
 },
 neutral: {
  icon: Minus,
  color: '#94A3B8',
  bg: 'rgba(148,163,184,0.08)',
  border: 'rgba(148,163,184,0.15)',
  label: 'minimal influence',
  arrow: '→',
 },
};

function FactorRow({ contribution, rank }) {
 const cfg = DIRECTION_CONFIG[contribution.direction] || DIRECTION_CONFIG.neutral;
 const Icon = cfg.icon;

 return (
  <motion.div
   initial={{ opacity: 0, x: -8 }}
   animate={{ opacity: 1, x: 0 }}
   transition={{ delay: rank * 0.07 }}
   className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
   style={{
    backgroundColor: cfg.bg,
    border: `1px solid ${cfg.border}`,
   }}
  >
   {/* Rank badge */}
   <span
    className="text-[10px] font-black w-5 h-5 rounded-full flex items-center justify-center shrink-0"
    style={{ backgroundColor: cfg.color, color: '#fff' }}
   >
    {rank + 1}
   </span>

   {/* Label & value */}
   <div className="flex-1 min-w-0">
    <div className="flex items-baseline gap-2 flex-wrap">
     <span className="text-xs font-bold text-slate-800 dark:text-slate-100">
      {contribution.label}
     </span>
     <span className="text-[10px] text-slate-500 dark:text-slate-400 font-medium">
      {contribution.display_value}
     </span>
    </div>
    <div className="flex items-center gap-1 mt-0.5">
     <span style={{ color: cfg.color }} className="text-xs font-semibold">
      {cfg.arrow}
     </span>
     <span className="text-[10px] text-slate-600 dark:text-slate-300">
      {cfg.label}
     </span>
    </div>
   </div>

   {/* Direction icon */}
   <Icon size={14} style={{ color: cfg.color }} className="shrink-0" />
  </motion.div>
 );
}

function AllFactorsRow({ contribution, rank }) {
 const cfg = DIRECTION_CONFIG[contribution.direction] || DIRECTION_CONFIG.neutral;

 return (
  <div
   className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg"
   style={{ backgroundColor: cfg.bg, border: `1px solid ${cfg.border}` }}
  >
   <span style={{ color: cfg.color }} className="text-xs font-bold w-3 shrink-0 text-center">
    {cfg.arrow}
   </span>
   <span className="text-[10px] font-semibold text-slate-700 dark:text-slate-200 flex-1">
    {contribution.label}
   </span>
   <span className="text-[10px] text-slate-500 dark:text-slate-400 shrink-0">
    {contribution.display_value}
   </span>
  </div>
 );
}

export default function ShapExplanationPanel({ explanation, loading, error, edge, onClose }) {
 const [showAll, setShowAll] = useState(false);

 const calRiskPct =
  explanation?.calibrated_risk_prob != null
   ? (explanation.calibrated_risk_prob * 100).toFixed(2)
   : edge?.calibrated_risk_prob != null
    ? (edge.calibrated_risk_prob * 100).toFixed(2)
    : null;

 const safetyScore =
  explanation?.safety_score ?? edge?.safety_score ?? null;

 const edgeName = edge?.name || edge?.road_class?.replace(/_/g, ' ') || 'Road segment';

 return (
  <motion.div
   initial={{ opacity: 0, y: 10 }}
   animate={{ opacity: 1, y: 0 }}
   exit={{ opacity: 0, y: 6 }}
   className="rounded-2xl overflow-hidden shadow-xl border select-none"
   style={{
    background: 'rgba(255,255,255,0.97)',
    backdropFilter: 'blur(16px)',
    borderColor: 'rgba(148,163,184,0.25)',
   }}
  >
   {/* ── Header ── */}
   <div
    className="flex items-center justify-between px-4 py-3"
    style={{
     background: 'linear-gradient(135deg, #1e40af 0%, #2563eb 100%)',
    }}
   >
    <div className="flex items-center gap-2.5 min-w-0">
     <div className="w-2 h-2 rounded-full bg-white/70 shrink-0" />
     <div className="min-w-0">
      <p className="text-white font-bold text-xs">Risk</p>
      <p className="text-blue-100 text-[10px] truncate">{edgeName}</p>
     </div>
    </div>
    {onClose && (
     <button
      type="button"
      onClick={onClose}
      className="text-white/80 hover:text-white ml-2 shrink-0 transition-colors"
      aria-label="Close explanation"
     >
      <X size={15} />
     </button>
    )}
   </div>

   {/* ── Scores row ── */}
   <div className="flex items-center divide-x divide-slate-200 dark:divide-slate-700 px-0">
    {safetyScore != null && (
     <div className="flex-1 text-center py-2.5 px-3">
      <p className="text-[10px] text-slate-500 dark:text-slate-400 font-medium">Safety Score</p>
      <p className="text-lg font-black text-slate-900 dark:text-slate-50 leading-tight">
       {safetyScore}
       <span className="text-[10px] font-normal text-slate-400 ml-0.5">/ 100</span>
      </p>
     </div>
    )}
    {calRiskPct != null && (
     <div className="flex-1 text-center py-2.5 px-3">
      <p className="text-[10px] text-slate-500 dark:text-slate-400 font-medium">Risk</p>
      <p className="text-lg font-black text-slate-900 dark:text-slate-50 leading-tight">
       {calRiskPct}
       <span className="text-[10px] font-normal text-slate-400 ml-0.5">%</span>
      </p>
     </div>
    )}
   </div>

   {/* ── Divider ── */}
   <div className="h-px bg-gradient-to-r from-transparent via-slate-200 to-transparent mx-4" />

   {/* ── Body ── */}
   <div className="px-3 pb-3 pt-2 space-y-2">

    {/* Why section header */}
    <p className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider px-1 flex items-center gap-1.5">
     <Info size={10} />
     Why this road received this risk
    </p>

    {/* Loading */}
    {loading && (
     <div className="space-y-2 animate-pulse">
      {[1, 2, 3].map((i) => (
       <div key={i} className="h-10 bg-slate-100 dark:bg-slate-800 rounded-xl" />
      ))}
     </div>
    )}

    {/* Error */}
    {error && !loading && (
     <div className="px-3 py-2.5 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40 text-xs text-amber-700 dark:text-amber-300">
      ⚠️ {error}
     </div>
    )}

    {/* Top 3 factors */}
    {!loading && !error && explanation?.top_factors && (
     <div className="space-y-1.5">
      {explanation.top_factors.map((factor, i) => (
       <FactorRow key={factor.feature} contribution={factor} rank={i} />
      ))}
     </div>
    )}

    {/* Show all factors toggle */}
    {!loading && !error && explanation?.explanation && explanation.explanation.length > 3 && (
     <>
      <button
       type="button"
       onClick={() => setShowAll((v) => !v)}
       className="w-full flex items-center justify-center gap-1.5 text-[10px] font-bold text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 py-1 transition-colors"
      >
       {showAll ? (
        <><ChevronUp size={12} /> Hide all factors</>
       ) : (
        <><ChevronDown size={12} /> View all {explanation.explanation.length} factors</>
       )}
      </button>

      <AnimatePresence>
       {showAll && (
        <motion.div
         initial={{ opacity: 0, height: 0 }}
         animate={{ opacity: 1, height: 'auto' }}
         exit={{ opacity: 0, height: 0 }}
         className="overflow-hidden"
        >
         <div className="space-y-1 pb-1">
          {explanation.explanation.map((factor, i) => (
           <AllFactorsRow key={factor.feature} contribution={factor} rank={i} />
          ))}
         </div>
        </motion.div>
       )}
      </AnimatePresence>
     </>
    )}

    {/* SHAP disclaimer */}
    {!loading && explanation && (
     <div
      className="text-[9px] text-slate-400 dark:text-slate-500 leading-relaxed px-1 pt-0.5 border-t border-slate-100 dark:border-slate-800"
     >
      <span className="font-semibold">Note:</span>{' '}
      Factors show model feature influence in log-odds space (TreeSHAP).
      Arrows indicate direction, not probability percentages.
      Based on historical road structure only — live conditions shown separately.
     </div>
    )}
   </div>
  </motion.div>
 );
}
