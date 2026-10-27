/**
 * frontend/src/components/Safety/AiRouteSummary.jsx
 * =================================================
 * Displays the LLM-powered "AI Route Summary" for the currently active route.
 *
 * Uses:
 *  - Groq API with openai/gpt-oss-120b
 *  - Authoritative route Safety Score and SHAP factors from backend
 *  - Live traffic, incidents, and weather summaries
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Sparkles,
  ArrowUp,
  ArrowDown,
  RefreshCw,
  Loader2,
  HelpCircle,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { explainRoute } from '../../services/aiApi';
import { getHistoricalRiskColor } from '../../utils/riskClassification';
import { parseAiBullets } from '../../utils/aiTextFormatter';

export default function AiRouteSummary({
  route,
  featureData,
  allRoutes = [],
  allFeaturesData = {},
  incidentAnalysis,
  trafficSummary,
  weather,
  onOpenChat = null,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [collapsed, setCollapsed] = useState(false);

  const routeId = route?.id;
  const score = featureData?.route_safety_score ?? null;
  const calProb = featureData?.route_calibrated_risk_prob ?? null;
  const distanceKm = route?.distance_meters ? route.distance_meters / 1000.0 : null;
  const durationMin = route?.duration_seconds ? route.duration_seconds / 60.0 : null;

  const loadRouteSummary = useCallback(async () => {
    if (!routeId) return;

    setLoading(true);
    setError(null);
    try {
      const alternative_routes = allRoutes
        .filter((r) => r.id !== routeId)
        .map((r) => ({
          route_id: r.id,
          distance_km: r.distance_meters ? r.distance_meters / 1000.0 : null,
          duration_minutes: r.duration_seconds ? r.duration_seconds / 60.0 : null,
          safety_score: allFeaturesData[r.id]?.route_safety_score ?? null,
        }));

      const resp = await explainRoute({
        route_id: routeId,
        distance_km: distanceKm,
        duration_minutes: durationMin,
        safety_score: score,
        calibrated_historical_risk: calProb,
        alternative_routes: alternative_routes.length > 0 ? alternative_routes : null,
      });
      setData(resp);
    } catch (err) {
      setError(err.message || 'Could not load AI summary');
    } finally {
      setLoading(false);
    }
  }, [routeId, distanceKm, durationMin, score, calProb]);

  useEffect(() => {
    loadRouteSummary();
  }, [loadRouteSummary]);

  if (!route) return null;

  const scoreColor = calProb !== null ? getHistoricalRiskColor(calProb) : '#64748b';

  return (
    <div className="rounded-2xl border border-indigo-200/80 dark:border-indigo-900/60 bg-gradient-to-b from-indigo-50/40 to-white dark:from-indigo-950/20 dark:to-slate-900 shadow-sm overflow-hidden text-xs">
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-indigo-100/50 dark:bg-indigo-950/40 border-b border-indigo-100 dark:border-indigo-900/40">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-indigo-600 text-white flex items-center justify-center shadow-xs">
            <Sparkles size={12} />
          </div>
          <span className="font-bold text-slate-800 dark:text-slate-100 text-xs tracking-tight">
            AI Route Summary
          </span>
          <span className="text-[10px] bg-indigo-200/60 dark:bg-indigo-900/60 text-indigo-800 dark:text-indigo-300 px-1.5 py-0.5 rounded-full font-mono">
            RouteGuard AI
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={loadRouteSummary}
            disabled={loading}
            title="Regenerate summary"
            className="p-1 text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          >
            {collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="p-3.5 space-y-3">
          {/* Main AI Explanation Text */}
          {loading ? (
            <div className="py-3 flex items-center justify-center gap-2 text-slate-400 italic">
              <Loader2 size={15} className="animate-spin text-indigo-500" />
              <span>Analyzing route safety evidence…</span>
            </div>
          ) : error ? (
            <p className="text-amber-700 dark:text-amber-400 italic">
              AI explanation temporarily unavailable.
            </p>
          ) : (
            (() => {
              const fallback = `This route has a ${score ?? '—'}/100 historical Safety Score. Live conditions remain separate from the historical model.`;
              const bullets = parseAiBullets(data?.answer, fallback);
              return (
                <ul className="space-y-2 text-slate-700 dark:text-slate-300 text-[11px] leading-relaxed">
                  {bullets.map((bullet, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 dark:bg-indigo-400 mt-1.5 shrink-0" />
                      <span className="flex-1">{bullet}</span>
                    </li>
                  ))}
                </ul>
              );
            })()
          )}

          {/* Model factors summary pills */}
          {data?.top_factors && data.top_factors.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {data.top_factors.map((f, i) => (
                <span
                  key={i}
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-medium text-[10px] ${
                    f.direction === 'higher_risk'
                      ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300 border border-rose-200 dark:border-rose-900/40'
                      : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-900/40'
                  }`}
                >
                  {f.direction === 'higher_risk' ? <ArrowUp size={9} /> : <ArrowDown size={9} />}
                  {f.feature}
                </span>
              ))}
            </div>
          )}

          {/* Ask AI Footer Button */}
          {onOpenChat && (
            <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex justify-end">
              <button
                type="button"
                onClick={onOpenChat}
                className="inline-flex items-center gap-1.5 text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 font-semibold text-[11px] transition-colors"
              >
                <HelpCircle size={12} />
                Ask questions about this route →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
