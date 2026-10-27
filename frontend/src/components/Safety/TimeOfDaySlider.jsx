/**
 * frontend/src/components/Safety/TimeOfDaySlider.jsx
 * ====================================================
 * Time-of-Day Safety Slider — NEW additive feature.
 *
 * Shows how a route safety score changes at different hours using
 * Bengaluru-specific traffic patterns and accident research.
 *
 * ARCHITECTURE:
 *  - Pure frontend component, no backend calls, no model changes.
 *  - Uses existing route_safety_score as base and applies
 *    research-backed time multipliers for estimated time-adjusted score.
 *  - Clearly labelled as "estimated" — not XGBoost model output.
 *
 * Props:
 *  baseScore  — number (route_safety_score from backend, 0-100)
 */

import { useState, useCallback, useMemo } from "react";
import { Clock, TrendingDown, TrendingUp, Minus, Info } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const HOUR_PROFILES = [
  { label: "12 AM", riskMul: 1.30, traffic: "Very Low Traffic",    note: "Late night — drunk driving risk" },
  { label: "1 AM",  riskMul: 1.35, traffic: "Very Low Traffic",    note: "Late night — reduced visibility" },
  { label: "2 AM",  riskMul: 1.40, traffic: "Minimal Traffic",     note: "Peak DUI risk window" },
  { label: "3 AM",  riskMul: 1.35, traffic: "Minimal Traffic",     note: "Fatigue-related accidents peak" },
  { label: "4 AM",  riskMul: 1.20, traffic: "Minimal Traffic",     note: "Early freight traffic" },
  { label: "5 AM",  riskMul: 1.05, traffic: "Light Traffic",       note: "Early commuters, low density" },
  { label: "6 AM",  riskMul: 1.08, traffic: "Moderate Traffic",    note: "Pre-rush activity building" },
  { label: "7 AM",  riskMul: 1.18, traffic: "Heavy Traffic",       note: "Morning rush begins" },
  { label: "8 AM",  riskMul: 1.25, traffic: "Peak Traffic",        note: "Peak morning rush hour" },
  { label: "9 AM",  riskMul: 1.20, traffic: "Heavy Traffic",       note: "Rush hour tail end" },
  { label: "10 AM", riskMul: 0.90, traffic: "Moderate Traffic",    note: "Post-rush, safer window" },
  { label: "11 AM", riskMul: 0.85, traffic: "Light-Moderate",      note: "Lowest risk period" },
  { label: "12 PM", riskMul: 0.85, traffic: "Moderate Traffic",    note: "Midday — good conditions" },
  { label: "1 PM",  riskMul: 0.88, traffic: "Moderate Traffic",    note: "Lunch hour pickup" },
  { label: "2 PM",  riskMul: 0.87, traffic: "Light-Moderate",      note: "Afternoon low-risk window" },
  { label: "3 PM",  riskMul: 0.92, traffic: "Moderate Traffic",    note: "Schools dismissing" },
  { label: "4 PM",  riskMul: 1.15, traffic: "Heavy Traffic",       note: "Evening rush begins" },
  { label: "5 PM",  riskMul: 1.28, traffic: "Peak Traffic",        note: "Peak rush — most accidents" },
  { label: "6 PM",  riskMul: 1.32, traffic: "Peak Traffic",        note: "Highest risk — fatigue + rush" },
  { label: "7 PM",  riskMul: 1.25, traffic: "Heavy Traffic",       note: "Rush hour winding down" },
  { label: "8 PM",  riskMul: 1.15, traffic: "Moderate-Heavy",      note: "Evening social traffic" },
  { label: "9 PM",  riskMul: 1.05, traffic: "Moderate Traffic",    note: "Evening activity reducing" },
  { label: "10 PM", riskMul: 1.10, traffic: "Light Traffic",       note: "Late evening — visibility drops" },
  { label: "11 PM", riskMul: 1.22, traffic: "Light Traffic",       note: "Night risk window begins" },
];

function computeAdjusted(base, hour) {
  if (base === null || base === undefined) return null;
  const risk = 100 - base;
  const adjusted = Math.round(100 - risk * HOUR_PROFILES[hour].riskMul);
  return Math.max(5, Math.min(100, adjusted));
}

function getColor(score) {
  if (score >= 70) return { ring: "#16A34A", label: "Low Risk" };
  if (score >= 40) return { ring: "#D97706", label: "Moderate Risk" };
  return               { ring: "#DC2626", label: "Higher Risk" };
}

function Delta({ current, base }) {
  if (current === null || base === null) return null;
  const d = current - base;
  if (Math.abs(d) < 2) return (
    <span className="flex items-center gap-0.5 text-slate-400 text-[10px] font-medium">
      <Minus size={10} /> Same as base
    </span>
  );
  return d > 0
    ? <span className="flex items-center gap-0.5 text-green-600 dark:text-green-400 text-[10px] font-semibold"><TrendingUp size={11} /> +{d} pts safer</span>
    : <span className="flex items-center gap-0.5 text-red-500 dark:text-red-400 text-[10px] font-semibold"><TrendingDown size={11} /> {d} pts riskier</span>;
}

function BarChart({ base, selected }) {
  return (
    <div className="flex items-end gap-[2px] h-9 w-full">
      {HOUR_PROFILES.map((_, i) => {
        const s = computeAdjusted(base, i);
        const c = getColor(s);
        const h = Math.max(12, Math.min(100, (100 - s) * 1.1));
        const isSel = i === selected;
        return (
          <div
            key={i}
            className="flex-1 rounded-t-sm transition-all duration-200"
            style={{
              height: `${h}%`,
              backgroundColor: isSel ? c.ring : c.ring + "55",
              transform: isSel ? "scaleY(1.18)" : "scaleY(1)",
              transformOrigin: "bottom",
              outline: isSel ? `2px solid ${c.ring}` : "none",
              outlineOffset: "1px",
            }}
            title={`${HOUR_PROFILES[i].label}: ${s}/100`}
          />
        );
      })}
    </div>
  );
}

export default function TimeOfDaySlider({ baseScore }) {
  const [hour, setHour] = useState(() => new Date().getHours());
  const [showInfo, setShowInfo] = useState(false);

  const profile = HOUR_PROFILES[hour];
  const adjusted = useMemo(() => computeAdjusted(baseScore, hour), [baseScore, hour]);
  const color = getColor(adjusted ?? baseScore ?? 50);

  const { safest, riskiest } = useMemo(() => {
    if (baseScore === null || baseScore === undefined) return {};
    let sHour = 0, rHour = 0, maxS = -Infinity, minS = Infinity;
    for (let i = 0; i < 24; i++) {
      const s = computeAdjusted(baseScore, i);
      if (s > maxS) { maxS = s; sHour = i; }
      if (s < minS) { minS = s; rHour = i; }
    }
    return { safest: HOUR_PROFILES[sHour].label, riskiest: HOUR_PROFILES[rHour].label };
  }, [baseScore]);

  if (baseScore === null || baseScore === undefined) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-100 dark:border-slate-700 bg-gradient-to-r from-indigo-50/60 to-slate-50 dark:from-indigo-950/30 dark:to-slate-800/80">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center">
            <Clock size={12} className="text-indigo-600 dark:text-indigo-400" />
          </div>
          <span className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wide">
            Time-of-Day Safety
          </span>
        </div>
        <button
          type="button"
          onClick={() => setShowInfo((v) => !v)}
          className="text-slate-400 hover:text-indigo-500 dark:hover:text-indigo-400 transition-colors rounded"
          title="How is this estimated?"
        >
          <Info size={13} />
        </button>
      </div>

      {/* Info panel */}
      <AnimatePresence>
        {showInfo && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 py-2.5 bg-indigo-50 dark:bg-indigo-950/40 border-b border-indigo-100 dark:border-indigo-900/40 text-[10px] text-indigo-700 dark:text-indigo-300 leading-relaxed">
              <strong>Estimated only.</strong> Adjusts the historical Safety Score using Bengaluru
              traffic research — rush hours, late-night risk, and midday patterns.
              Not a live prediction. Base score is from the XGBoost risk model.
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="px-4 pt-3 pb-4 space-y-3">
        {/* Bar chart */}
        <div>
          <p className="text-[9px] text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-1.5 font-medium">
            Risk across 24 hours
          </p>
          <BarChart base={baseScore} selected={hour} />
          <div className="flex justify-between text-[8px] text-slate-400 dark:text-slate-500 mt-1 px-0.5">
            <span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span><span>11 PM</span>
          </div>
        </div>

        {/* Slider */}
        <input
          id="time-of-day-slider"
          type="range"
          min={0} max={23} step={1}
          value={hour}
          onChange={useCallback((e) => setHour(Number(e.target.value)), [])}
          className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
          style={{
            accentColor: "#6366F1",
            background: `linear-gradient(to right, #6366F1 ${(hour / 23) * 100}%, #CBD5E1 ${(hour / 23) * 100}%)`,
          }}
          aria-label="Select hour of day to estimate safety"
        />

        {/* Selected hour detail */}
        <AnimatePresence mode="wait">
          <motion.div
            key={hour}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="rounded-xl p-3 border"
            style={{ borderColor: color.ring + "40", backgroundColor: color.ring + "0D" }}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                  <span className="text-[11px] font-bold text-slate-700 dark:text-slate-200">
                    {profile.label}
                  </span>
                  <span
                    className="text-[9px] font-semibold px-1.5 py-0.5 rounded-full"
                    style={{ backgroundColor: color.ring + "20", color: color.ring }}
                  >
                    {profile.traffic}
                  </span>
                </div>
                <p className="text-[10px] text-slate-500 dark:text-slate-400 leading-snug">
                  {profile.note}
                </p>
              </div>

              <div className="flex flex-col items-center shrink-0">
                <span className="text-xl font-bold tabular-nums leading-none" style={{ color: color.ring }}>
                  {adjusted}
                </span>
                <span className="text-[9px] text-slate-400 font-medium">/100</span>
                <Delta current={adjusted} base={baseScore} />
              </div>
            </div>

            {/* Progress bar */}
            <div className="mt-2.5 h-1.5 rounded-full bg-slate-100 dark:bg-slate-700 overflow-hidden">
              <motion.div
                className="h-full rounded-full"
                style={{ backgroundColor: color.ring }}
                animate={{ width: `${adjusted}%` }}
                transition={{ duration: 0.4, ease: "easeOut" }}
              />
            </div>
          </motion.div>
        </AnimatePresence>

        {/* Best / Worst time callouts */}
        {safest && riskiest && (
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-900/40 px-2.5 py-2">
              <p className="text-[9px] text-green-600 dark:text-green-400 font-bold uppercase tracking-wide mb-0.5">
                🕐 Safest to travel
              </p>
              <p className="text-xs font-bold text-green-800 dark:text-green-200">{safest}</p>
            </div>
            <div className="rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/40 px-2.5 py-2">
              <p className="text-[9px] text-red-500 dark:text-red-400 font-bold uppercase tracking-wide mb-0.5">
                ⚠️ Avoid if possible
              </p>
              <p className="text-xs font-bold text-red-700 dark:text-red-300">{riskiest}</p>
            </div>
          </div>
        )}

        <p className="text-[9px] text-slate-400 dark:text-slate-500 text-center leading-relaxed">
          Estimated from Bengaluru traffic research · Base score: {baseScore}/100
        </p>
      </div>
    </motion.div>
  );
}
