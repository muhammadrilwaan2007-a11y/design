/**
 * frontend/src/components/Safety/WhyThisSection.jsx
 * =================================================
 * Dedicated "Why This Section?" UI panel.
 *
 * Implements the exact layout and behavior required:
 *  - Historical Safety Score (0-100)
 *  - Natural-language explanation from GPT-OSS 120B (Groq)
 *  - Model factors (with directional arrows and human statements)
 *  - Live conditions (Traffic, Incidents, Weather)
 *  - Interactive "Ask RouteGuard AI" question interface
 *
 * CRITICAL ARCHITECTURE RULES:
 *  1. Numerical SHAP evidence and Safety Score come verbatim from the backend.
 *  2. GPT-OSS converts that evidence into human-readable explanation.
 *  3. Live conditions are kept visually and conceptually separate from historical risk.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Sparkles,
  ArrowUp,
  ArrowDown,
  Minus,
  AlertTriangle,
  CloudRain,
  Car,
  CheckCircle2,
  HelpCircle,
  Send,
  Loader2,
  Shield,
  MessageSquare,
  RefreshCw,
  X,
} from 'lucide-react';
import { explainSection, askAiAssistant } from '../../services/aiApi';
import { getHistoricalRiskColor } from '../../utils/riskClassification';
import { parseAiBullets } from '../../utils/aiTextFormatter';

const QUICK_QUESTIONS = [
  'Why is this section risky?',
  'What factors affected this score?',
  'Is there a closure on my route?',
  'What is happening right now?',
];

export default function WhyThisSection({
  edge = null,
  segment = null,
  routeId = null,
  onClose = null,
  onOpenChat = null,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // User Q&A within the section
  const [userQuestion, setUserQuestion] = useState('');
  const [customAnswer, setCustomAnswer] = useState(null);
  const [asking, setAsking] = useState(false);

  const osmEdgeId = edge?.edge_id ?? edge?.unique_edge_id ?? null;
  const segmentId = segment?.segment_id ?? null;
  const segmentCoords = segment?.geometry?.coordinates ?? edge?.geometry?.coordinates ?? null;

  const loadExplanation = useCallback(async (customQ = null) => {
    if (!osmEdgeId && !segmentCoords && !segmentId) return;

    setLoading(true);
    setError(null);
    try {
      const resp = await explainSection({
        osm_edge_id: osmEdgeId,
        segment_id: segmentId,
        route_id: routeId,
        segment_coords: segmentCoords,
        question: customQ,
      });
      setData(resp);
    } catch (err) {
      setError(err.message || 'Could not retrieve AI explanation.');
    } finally {
      setLoading(false);
    }
  }, [osmEdgeId, segmentId, routeId, segmentCoords]);

  useEffect(() => {
    loadExplanation();
  }, [loadExplanation]);

  const handleAsk = async (q) => {
    const questionText = q || userQuestion;
    if (!questionText.trim()) return;

    setAsking(true);
    try {
      const resp = await askAiAssistant({
        question: questionText,
        osm_edge_id: osmEdgeId,
        segment_id: segmentId,
        route_id: routeId,
      });
      setCustomAnswer({
        question: questionText,
        answer: resp.answer,
      });
      setUserQuestion('');
    } catch (err) {
      setCustomAnswer({
        question: questionText,
        answer: 'AI explanation temporarily unavailable. Please try again.',
      });
    } finally {
      setAsking(false);
    }
  };

  const score = data?.safety_score ?? edge?.safety_score ?? segment?.safety_score ?? null;
  const calRisk = data?.calibrated_historical_risk ?? edge?.calibrated_risk_prob ?? segment?.calibrated_risk_prob ?? null;
  const scoreColor = calRisk !== null ? getHistoricalRiskColor(calRisk) : '#64748b';

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xl overflow-hidden text-xs max-w-sm w-full select-text transition-all duration-200">
      {/* ── Header ── */}
      <div className="bg-gradient-to-r from-slate-900 to-indigo-950 text-white p-3.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center text-indigo-300">
            <Sparkles size={14} className="animate-pulse" />
          </div>
          <div>
            <h3 className="font-bold text-sm tracking-tight text-white flex items-center gap-1.5">
              Why This Section?
            </h3>
            <p className="text-[10px] text-indigo-200/70 font-mono">
              RouteGuard AI Intelligence
            </p>
          </div>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-md transition-colors"
          >
            <X size={15} />
          </button>
        )}
      </div>

      <div className="p-4 space-y-3.5 max-h-[75vh] overflow-y-auto">
        {/* ── Safety Score Badge ── */}
        <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/80 dark:border-slate-700/80">
          <div>
            <div className="text-[10px] uppercase font-bold tracking-wider text-slate-500 dark:text-slate-400">
              Safety Score
            </div>
            <div className="text-xl font-extrabold tracking-tight" style={{ color: scoreColor }}>
              {score !== null ? `${score} / 100` : '— / 100'}
            </div>
            <div className="text-[10px] text-slate-400 dark:text-slate-500">
              Historical road data
            </div>
          </div>
          <div className="w-10 h-10 rounded-full flex items-center justify-center border-2" style={{ borderColor: scoreColor, backgroundColor: scoreColor + '18' }}>
            <Shield size={18} style={{ color: scoreColor }} />
          </div>
        </div>

        {/* ── AI Explanation Text (GPT-OSS 120B) ── */}
        <div className="rounded-xl bg-indigo-50/60 dark:bg-indigo-950/30 border border-indigo-100 dark:border-indigo-900/50 p-3">
          <div className="flex items-center gap-1.5 text-indigo-800 dark:text-indigo-300 font-semibold mb-1 text-[11px]">
            <Sparkles size={12} />
            AI Explanation
          </div>

          {loading ? (
            <div className="py-3 flex flex-col items-center justify-center gap-2 text-slate-400">
              <Loader2 size={18} className="animate-spin text-indigo-500" />
              <span className="text-[11px] animate-pulse">Generating explanation…</span>
            </div>
          ) : error ? (
            <p className="text-amber-700 dark:text-amber-400 text-[11px] italic">
              AI explanation temporarily unavailable.
            </p>
          ) : (
            (() => {
              const fallback = 'Historical risk is calculated by the model based on road infrastructure characteristics.';
              const bullets = parseAiBullets(data?.answer, fallback);
              return (
                <ul className="space-y-1.5 text-slate-700 dark:text-slate-300 text-[11px] leading-relaxed">
                  {bullets.map((bullet, idx) => (
                    <li key={idx} className="flex items-start gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 dark:bg-indigo-400 mt-1.5 shrink-0" />
                      <span className="flex-1">{bullet}</span>
                    </li>
                  ))}
                </ul>
              );
            })()
          )}
        </div>

        {/* ── Model Factors (Local SHAP Evidence) ── */}
        <div>
          <div className="text-[10px] uppercase font-bold tracking-wider text-slate-500 dark:text-slate-400 mb-2 flex items-center justify-between">
            <span>Model factors</span>
          </div>

          <div className="space-y-1.5">
            {data?.top_factors && data.top_factors.length > 0 ? (
              data.top_factors.map((factor, idx) => {
                const isHigh = factor.direction === 'higher_risk';
                const isLow = factor.direction === 'lower_risk';
                return (
                  <div
                    key={idx}
                    className="p-2 rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800 flex items-start gap-2"
                  >
                    <div
                      className={`mt-0.5 w-4 h-4 rounded flex items-center justify-center shrink-0 ${
                        isHigh
                          ? 'bg-rose-100 dark:bg-rose-900/40 text-rose-600 dark:text-rose-400'
                          : isLow
                          ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-400'
                      }`}
                    >
                      {isHigh ? <ArrowUp size={11} /> : isLow ? <ArrowDown size={11} /> : <Minus size={11} />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-slate-800 dark:text-slate-200 text-[11px]">
                        {factor.feature}
                      </div>
                      <div className="text-[10px] text-slate-500 dark:text-slate-400 leading-tight">
                        {isHigh
                          ? 'Higher modeled historical risk'
                          : isLow
                          ? 'Lower modeled historical risk'
                          : 'Neutral model influence'}
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-[11px] text-slate-400 italic p-2 bg-slate-50 dark:bg-slate-800/40 rounded-lg">
                Loading model factor evidence…
              </div>
            )}
          </div>
        </div>

        {/* ── Live Conditions (SEPARATE from Safety Score) ── */}
        <div>
          <div className="text-[10px] uppercase font-bold tracking-wider text-slate-500 dark:text-slate-400 mb-2">
            Live conditions
          </div>
          <div className="space-y-1.5">
            {/* Traffic */}
            <div className="flex items-center gap-2 p-2 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 text-[11px] text-slate-700 dark:text-slate-300">
              <Car size={13} className="text-amber-500 shrink-0" />
              <span>{data?.live_conditions?.traffic || 'Normal flowing traffic'}</span>
            </div>

            {/* Incidents / Closures */}
            <div className="flex items-start gap-2 p-2 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 text-[11px]">
              {data?.live_conditions?.incidents?.length > 0 ? (
                <>
                  <AlertTriangle size={13} className="text-rose-500 shrink-0 mt-0.5" />
                  <div className="text-rose-700 dark:text-rose-300">
                    <span className="font-semibold">{data.live_conditions.incidents[0].type}</span>
                    {data.live_conditions.incidents[0].distance_m != null && (
                      <span className="text-[10px] text-slate-400 ml-1">
                        (~{data.live_conditions.incidents[0].distance_m}m away)
                      </span>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />
                  <span className="text-slate-600 dark:text-slate-300">No active incident</span>
                </>
              )}
            </div>

            {/* Weather */}
            <div className="flex items-center gap-2 p-2 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 text-[11px] text-slate-700 dark:text-slate-300">
              <CloudRain size={13} className="text-sky-500 shrink-0" />
              <span>
                {data?.live_conditions?.weather?.description || data?.live_conditions?.weather?.condition || 'Weather normal'}
                {data?.live_conditions?.weather?.temp_c != null && ` · ${data.live_conditions.weather.temp_c}°C`}
              </span>
            </div>
          </div>
        </div>

        {/* ── Custom Q&A Answer Display ── */}
        {customAnswer && (
          <div className="p-3 rounded-xl bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 text-[11px] space-y-1.5">
            <div className="font-semibold text-amber-900 dark:text-amber-200 flex items-center gap-1">
              <MessageSquare size={12} />
              Q: {customAnswer.question}
            </div>
            {(() => {
              const bullets = parseAiBullets(customAnswer.answer);
              return bullets.length > 1 ? (
                <ul className="space-y-1 text-slate-700 dark:text-slate-300">
                  {bullets.map((b, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-1.5 shrink-0" />
                      <span className="flex-1">{b}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-slate-700 dark:text-slate-300 leading-relaxed">
                  {bullets[0] || customAnswer.answer.replace(/[*_#]/g, '')}
                </p>
              );
            })()}
          </div>
        )}

        {/* ── "Ask RouteGuard AI" Section ── */}
        <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-bold text-slate-700 dark:text-slate-200 flex items-center gap-1">
              <HelpCircle size={12} className="text-indigo-500" />
              Ask RouteGuard AI
            </span>
            {onOpenChat && (
              <button
                type="button"
                onClick={onOpenChat}
                className="text-[10px] text-indigo-600 dark:text-indigo-400 hover:underline font-semibold"
              >
                Open Full Assistant →
              </button>
            )}
          </div>

          {/* Quick chips */}
          <div className="flex flex-wrap gap-1 mb-2">
            {QUICK_QUESTIONS.map((q, i) => (
              <button
                key={i}
                type="button"
                onClick={() => handleAsk(q)}
                disabled={asking}
                className="text-[10px] px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-indigo-50 hover:text-indigo-600 dark:hover:bg-indigo-950/60 dark:hover:text-indigo-300 transition-colors border border-slate-200 dark:border-slate-700 text-left"
              >
                {q}
              </button>
            ))}
          </div>

          {/* Question input */}
          <div className="flex items-center gap-1.5">
            <input
              type="text"
              value={userQuestion}
              onChange={(e) => setUserQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
              placeholder="Ask about this section..."
              disabled={asking}
              className="flex-1 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 text-[11px] text-slate-800 dark:text-slate-100 focus:outline-hidden focus:ring-1 focus:ring-indigo-500"
            />
            <button
              type="button"
              onClick={() => handleAsk()}
              disabled={asking || !userQuestion.trim()}
              className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white p-1.5 rounded-lg transition-colors flex items-center justify-center shrink-0"
            >
              {asking ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
