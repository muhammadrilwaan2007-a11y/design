/**
 * frontend/src/components/Safety/AiAssistantDrawer.jsx
 * ====================================================
 * Interactive AI Safety Assistant side drawer.
 * Powered by Groq API + openai/gpt-oss-120b.
 *
 * Responsibilities:
 *  - Interactive Q&A grounded strictly in RouteGuard AI's structured evidence
 *  - Contextual awareness of selected route, selected road section, and live conditions
 *  - Quick suggested queries for rapid user interaction
 *  - Clear disclaimer that scores are produced by backend XGBoost, not the LLM
 */

import { useState, useRef, useEffect } from 'react';
import {
  Sparkles,
  Send,
  X,
  Bot,
  User,
  Shield,
  HelpCircle,
  Loader2,
  Trash2,
} from 'lucide-react';
import { askAiAssistant } from '../../services/aiApi';
import { parseAiBullets } from '../../utils/aiTextFormatter';

const SUGGESTED_QUERIES = [
  'Why is this route scored this way?',
  'What factors affected this score?',
  'Is there a closure on my route?',
  'Which sections should I pay attention to?',
  'Explain the high-risk section.',
  'What is happening right now with traffic and weather?',
];

export default function AiAssistantDrawer({
  isOpen,
  onClose,
  selectedRoute = null,
  featureData = null,
  selectedSection = null,
  allRoutes = [],
  allFeaturesData = {},
}) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        "Hello! I am RouteGuard AI's safety explanation assistant. I can explain your route's Safety Score, contributing risk factors, and live traffic, closure, or weather conditions. What would you like to know?",
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) scrollToBottom();
  }, [messages, isOpen]);

  const handleSend = async (customText = null) => {
    const textToSend = customText || input;
    if (!textToSend.trim() || loading) return;

    const userMsg = { role: 'user', content: textToSend };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const alternative_routes = allRoutes
        .filter((r) => r.id !== selectedRoute?.id)
        .map((r) => ({
          route_id: r.id,
          distance_km: r.distance_meters ? r.distance_meters / 1000.0 : null,
          duration_minutes: r.duration_seconds ? r.duration_seconds / 60.0 : null,
          safety_score: allFeaturesData[r.id]?.route_safety_score ?? null,
        }));

      const resp = await askAiAssistant({
        question: textToSend,
        route_id: selectedRoute?.id,
        osm_edge_id: selectedSection?.edge_id ?? selectedSection?.unique_edge_id,
        segment_id: selectedSection?.segment_id,
        alternative_routes: alternative_routes.length > 0 ? alternative_routes : null,
      });

      const assistantMsg = {
        role: 'assistant',
        content: resp.answer || 'I could not generate an explanation for that query.',
        status: resp.status,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'AI explanation temporarily unavailable. The core routing and safety scores remain active.',
          status: 'fallback',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleClearChat = () => {
    setMessages([
      {
        role: 'assistant',
        content:
          "Chat reset. I am ready to answer questions about your route's Safety Score, risk factors, and live conditions.",
      },
    ]);
  };

  if (!isOpen) return null;

  const score = featureData?.route_safety_score ?? null;

  return (
    <div
      className="fixed inset-y-0 right-0 z-[2000] w-full max-w-md bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col transition-all duration-300"
      role="dialog"
      aria-label="AI Safety Assistant"
    >
      {/* ── Top Bar ── */}
      <div className="p-4 bg-gradient-to-r from-slate-950 via-indigo-950 to-slate-900 text-white flex items-center justify-between border-b border-indigo-900/40">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-300 shadow-xs">
            <Sparkles size={17} className="animate-pulse" />
          </div>
          <div>
            <div className="font-bold text-sm tracking-tight text-white flex items-center gap-1.5">
              AI Safety Assistant
            </div>
            <div className="text-[10px] text-indigo-300/80 font-mono">
              RouteGuard AI Intelligence
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleClearChat}
            title="Clear chat"
            className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800/60 transition-colors"
          >
            <Trash2 size={15} />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800/60 transition-colors"
          >
            <X size={17} />
          </button>
        </div>
      </div>

      {/* ── Active Route / Section Context Banner ── */}
      <div className="px-4 py-2 bg-indigo-50/70 dark:bg-indigo-950/30 border-b border-indigo-100 dark:border-indigo-900/40 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300">
          <Shield size={13} className="text-indigo-600 dark:text-indigo-400" />
          <span>Context:</span>
          <strong className="text-slate-800 dark:text-slate-100">
            {selectedRoute ? `Route ${selectedRoute.id.replace('route_', '')}` : 'City Map'}
          </strong>
          {selectedSection && (
            <span className="text-[11px] text-slate-500">
              · Section {selectedSection.segment_index != null ? `#${selectedSection.segment_index + 1}` : ''}
            </span>
          )}
        </div>
        {score !== null && (
          <span className="font-bold text-indigo-700 dark:text-indigo-300 bg-indigo-100/80 dark:bg-indigo-900/60 px-2 py-0.5 rounded-full text-[10px]">
            Score: {score}/100
          </span>
        )}
      </div>

      {/* ── Chat Messages ── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3.5 text-xs">
        {messages.map((msg, i) => {
          const isUser = msg.role === 'user';
          return (
            <div
              key={i}
              className={`flex gap-2.5 ${isUser ? 'justify-end' : 'justify-start'}`}
            >
              {!isUser && (
                <div className="w-6 h-6 rounded-full bg-indigo-100 dark:bg-indigo-900/60 text-indigo-600 dark:text-indigo-300 flex items-center justify-center shrink-0 mt-0.5">
                  <Bot size={13} />
                </div>
              )}
              <div
                className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 leading-relaxed text-xs ${
                  isUser
                    ? 'bg-indigo-600 text-white rounded-tr-xs'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-100 border border-slate-200/60 dark:border-slate-700/60 rounded-tl-xs'
                }`}
              >
                {isUser ? (
                  msg.content
                ) : (
                  (() => {
                    const bullets = parseAiBullets(msg.content);
                    if (bullets.length > 1) {
                      return (
                        <ul className="space-y-1.5 text-xs">
                          {bullets.map((b, i) => (
                            <li key={i} className="flex items-start gap-1.5">
                              <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 dark:bg-indigo-400 mt-1.5 shrink-0" />
                              <span className="flex-1">{b}</span>
                            </li>
                          ))}
                        </ul>
                      );
                    }
                    return msg.content.replace(/[*_#]/g, '');
                  })()
                )}
              </div>
              {isUser && (
                <div className="w-6 h-6 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 flex items-center justify-center shrink-0 mt-0.5">
                  <User size={13} />
                </div>
              )}
            </div>
          );
        })}

        {loading && (
          <div className="flex gap-2.5 items-center text-slate-400 italic">
            <div className="w-6 h-6 rounded-full bg-indigo-100 dark:bg-indigo-900/60 text-indigo-600 dark:text-indigo-300 flex items-center justify-center shrink-0">
              <Bot size={13} />
            </div>
            <div className="bg-slate-100 dark:bg-slate-800 rounded-2xl px-3.5 py-2 flex items-center gap-2">
              <Loader2 size={13} className="animate-spin text-indigo-500" />
              <span>Reasoning over safety evidence…</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* ── Suggested Questions Chips ── */}
      <div className="px-4 py-2 bg-slate-50 dark:bg-slate-900/80 border-t border-slate-100 dark:border-slate-800">
        <p className="text-[10px] uppercase font-bold tracking-wider text-slate-400 mb-1.5 flex items-center gap-1">
          <HelpCircle size={10} /> Suggested Questions
        </p>
        <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
          {SUGGESTED_QUERIES.map((q, i) => (
            <button
              key={i}
              type="button"
              onClick={() => handleSend(q)}
              disabled={loading}
              className="text-[10px] px-2.5 py-1 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:border-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-300 transition-colors whitespace-nowrap shrink-0 shadow-2xs"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* ── Input Box ── */}
      <div className="p-3 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about this route, risk factors, or closures..."
            disabled={loading}
            className="flex-1 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-slate-800 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white p-2.5 rounded-xl transition-colors shadow-xs"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </form>
        <p className="text-[9px] text-slate-400 dark:text-slate-500 mt-1.5 text-center">
          AI Assistant explains evidence produced by the safety model. Live conditions are separate from the score.
        </p>
      </div>
    </div>
  );
}
