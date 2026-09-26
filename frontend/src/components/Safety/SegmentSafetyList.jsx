/**
 * frontend/src/components/Safety/SegmentSafetyList.jsx
 * Displays per-segment safety scores for the selected route.
 *
 * Segment scores come verbatim from:
 *  segment.safety_score    (0-100, from backend)
 *  segment.historical_risk_prob (0-1, from backend XGBoost)
 *  segment.segment_id
 *  segment.segment_index
 *  segment.segment_length_km
 *
 * No calculations are performed here. Scores are displayed as returned.
 *
 * Props:
 *  segments — SegmentFeatureVector[] | null | undefined
 *  loading — boolean
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, BarChart3, HelpCircle } from 'lucide-react';
import WhyThisSection from './WhyThisSection';

function getSegmentColor(score) {
 if (score === null || score === undefined) return '#9CA3AF';
 if (score >= 70) return '#16A34A';
 if (score >= 40) return '#D97706';
 return '#DC2626';
}

function getSegmentLabel(score) {
 if (score === null || score === undefined) return 'Unknown';
 if (score >= 70) return 'Low Risk';
 if (score >= 40) return 'Moderate';
 return 'Higher Risk';
}

function SegmentBar({ score }) {
 const color = getSegmentColor(score);
 const pct  = score !== null && score !== undefined ? score : 0;
 return (
  <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
   <div
    className="h-full rounded-full transition-all duration-700"
    style={{ width: `${pct}%`, backgroundColor: color }}
   />
  </div>
 );
}

function SegmentRow({ segment, index, isSelected, onSelect }) {
  const score  = segment.safety_score;
  const color  = getSegmentColor(score);
  const label  = getSegmentLabel(score);
  const lengthKm = segment.segment_length_km?.toFixed(2) ?? '—';

  return (
    <button
      type="button"
      onClick={() => onSelect(segment)}
      className={`w-full text-left flex items-center gap-2 px-3 py-2 rounded-lg transition-colors group cursor-pointer ${
        isSelected
          ? 'bg-indigo-50 dark:bg-indigo-950/50 border border-indigo-300 dark:border-indigo-700'
          : 'bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800'
      }`}
      title={`Segment ${index + 1} (${lengthKm} km): Click to see Why This Section?`}
    >
      {/* Index badge */}
      <span className="text-[10px] font-semibold text-slate-400 w-4 shrink-0">
        {index + 1}
      </span>

      {/* Progress bar */}
      <SegmentBar score={score} />

      {/* Score */}
      <span
        className="text-xs font-bold tabular-nums w-10 text-right shrink-0"
        style={{ color }}
      >
        {score !== null && score !== undefined ? `${score}/100` : '—'}
      </span>

      {/* Action / Explain button hint */}
      <span className="text-[10px] text-indigo-600 dark:text-indigo-400 font-medium hidden group-hover:inline-flex items-center gap-0.5 shrink-0">
        Why?
      </span>
    </button>
  );
}

export default function SegmentSafetyList({ segments, loading, onSelectSegment = null }) {
  const [expanded, setExpanded] = useState(false);
  const [selectedSegment, setSelectedSegment] = useState(null);

  // Don't render the section at all if there's nothing
  if (!loading && (!segments || segments.length === 0)) return null;

  // Check if any segment actually has a score
  const hasScores = segments?.some((s) => s.safety_score !== null && s.safety_score !== undefined);

  const handleSegmentClick = (seg) => {
    const next = selectedSegment?.segment_id === seg.segment_id ? null : seg;
    setSelectedSegment(next);
    if (onSelectSegment) onSelectSegment(next);
  };

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
      {/* Header / Toggle */}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2">
          <BarChart3 size={13} className="text-slate-400" />
          <span className="text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wide">
            Segment Safety Scores
          </span>
          {segments && (
            <span className="text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-1.5 py-0.5 rounded-full font-medium">
              {segments.length} segments
            </span>
          )}
        </div>
        {expanded ? (
          <ChevronUp size={13} className="text-slate-400 shrink-0" />
        ) : (
          <ChevronDown size={13} className="text-slate-400 shrink-0" />
        )}
      </button>

      {/* Content */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div className="border-t border-slate-100 dark:border-slate-800 px-3 py-2 space-y-2">
              {loading ? (
                /* Skeleton */
                <div className="space-y-1.5 animate-pulse">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-800">
                      <div className="w-4 h-3 bg-slate-200 dark:bg-slate-700 rounded" />
                      <div className="flex-1 h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full" />
                      <div className="w-10 h-3 bg-slate-200 dark:bg-slate-700 rounded" />
                    </div>
                  ))}
                </div>
              ) : !hasScores ? (
                <p className="text-xs text-slate-400 italic py-2 px-1">
                  Segment scores unavailable.
                </p>
              ) : (
                <div className="space-y-1 max-h-52 overflow-y-auto pr-0.5">
                  {segments.map((seg, i) => (
                    <SegmentRow
                      key={seg.segment_id ?? i}
                      segment={seg}
                      index={i}
                      isSelected={selectedSegment?.segment_id === seg.segment_id}
                      onSelect={handleSegmentClick}
                    />
                  ))}
                </div>
              )}

              {/* Dedicated "Why This Section?" if segment selected */}
              {selectedSegment && (
                <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
                  <WhyThisSection
                    segment={selectedSegment}
                    onClose={() => setSelectedSegment(null)}
                  />
                </div>
              )}

              <p className="text-[10px] text-slate-400 italic mt-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                Click any section above to inspect SHAP factors & live conditions.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
