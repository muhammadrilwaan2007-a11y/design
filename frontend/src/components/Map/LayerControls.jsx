/**
 * frontend/src/components/Map/LayerControls.jsx
 * ==============================================
 * Layer Control Panel and Legend for SafeRoute AI Map.
 *
 * Visual Polish:
 *  - Sleek frosted glassmorphic card (backdrop-blur-md)
 *  - Custom iOS-style toggle switches (replacing raw HTML checkboxes)
 *  - Clean typography with status dots and smooth transitions
 *  - Gradient indicator with "Lower ───────── Higher"
 */

import { useState } from 'react';
import { Layers, ChevronDown, ChevronUp, Shield, Activity, AlertTriangle, CloudSun } from 'lucide-react';
import { HISTORICAL_RISK_TIERS } from '../../utils/riskClassification';

function ToggleSwitch({ checked, onChange, id }) {
 return (
  <button
   id={id}
   type="button"
   role="switch"
   aria-checked={checked}
   onClick={onChange}
   className={`w-7 h-4 flex items-center rounded-full p-0.5 cursor-pointer transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary-500/30 ${
    checked ? 'bg-primary-600 dark:bg-primary-500' : 'bg-slate-300 dark:bg-slate-600'
   }`}
  >
   <span
    className={`bg-white w-3 h-3 rounded-full shadow-sm transform transition-transform duration-200 ${
     checked ? 'translate-x-3' : 'translate-x-0'
    }`}
   />
  </button>
 );
}

export default function LayerControls({
 layers = {
  historicalRisk: true,
  traffic: true,
  incidents: true,
  weather: true,
 },
 onToggleLayer,
}) {
 const [isOpen, setIsOpen] = useState(true);

 const toggle = (key) => {
  if (onToggleLayer) onToggleLayer(key);
 };

 return (
  <div className="bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border border-slate-200/90 dark:border-slate-700/90 rounded-2xl shadow-xl transition-all duration-200 w-64 overflow-hidden text-xs">
   {/* Header bar */}
   <div
    className="flex items-center justify-between px-3.5 py-2.5 cursor-pointer select-none bg-slate-50/80 dark:bg-slate-800/80 border-b border-slate-200/70 dark:border-slate-700/70"
    onClick={() => setIsOpen((prev) => !prev)}
   >
    <div className="flex items-center gap-2 font-bold text-slate-800 dark:text-slate-100">
     <Layers size={14} className="text-primary-600 dark:text-primary-400" />
     <span>Map Layers &amp; Risk</span>
    </div>
    <button
     type="button"
     aria-label={isOpen ? 'Collapse layer controls' : 'Expand layer controls'}
     className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
    >
     {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
    </button>
   </div>

   {isOpen && (
    <div className="p-3.5 space-y-3.5">
     {/* Layer toggles with iOS switches */}
     <div className="space-y-2">
      {/* 1. Risk Heatmap */}
      <div className="flex items-center justify-between py-0.5">
       <span className="flex items-center gap-2 font-medium text-slate-700 dark:text-slate-200 text-xs">
        <Shield size={13} className="text-emerald-500" />
        <span>Risk Heatmap</span>
       </span>
       <ToggleSwitch
        id="toggle-historical-risk"
        checked={!!layers.historicalRisk}
        onChange={() => toggle('historicalRisk')}
       />
      </div>

      {/* 2. Live Traffic */}
      <div className="flex items-center justify-between py-0.5">
       <span className="flex items-center gap-2 font-medium text-slate-700 dark:text-slate-200 text-xs">
        <Activity size={13} className="text-amber-500" />
        <span>Live Traffic</span>
       </span>
       <ToggleSwitch
        id="toggle-live-traffic"
        checked={!!layers.traffic}
        onChange={() => toggle('traffic')}
       />
      </div>

      {/* 3. Live Incidents */}
      <div className="flex items-center justify-between py-0.5">
       <span className="flex items-center gap-2 font-medium text-slate-700 dark:text-slate-200 text-xs">
        <AlertTriangle size={13} className="text-rose-500" />
        <span>Live Incidents</span>
       </span>
       <ToggleSwitch
        id="toggle-live-incidents"
        checked={!!layers.incidents}
        onChange={() => toggle('incidents')}
       />
      </div>

      {/* 4. Weather */}
      <div className="flex items-center justify-between py-0.5">
       <span className="flex items-center gap-2 font-medium text-slate-700 dark:text-slate-200 text-xs">
        <CloudSun size={13} className="text-blue-500" />
        <span>Weather</span>
       </span>
       <ToggleSwitch
        id="toggle-weather"
        checked={!!layers.weather}
        onChange={() => toggle('weather')}
       />
      </div>
     </div>

     {/* Risk Legend */}
     {layers.historicalRisk && (
      <div className="pt-2.5 border-t border-slate-200/80 dark:border-slate-700/80 space-y-2">
       <div className="flex items-center justify-between">
        <span className="font-bold text-slate-800 dark:text-slate-200 text-[11px]">
         Risk
        </span>
        <span className="text-[10px] font-medium text-slate-400 dark:text-slate-500">
         ML
        </span>
       </div>

       {/* Gradient Bar */}
       <div className="space-y-1">
        <div
         className="h-2 rounded-full w-full shadow-inner opacity-90"
         style={{
          background:
           'linear-gradient(to right, #10B981 0%, #F59E0B 35%, #F97316 70%, #EF4444 100%)',
         }}
        />
        <div className="flex justify-between text-[10px] text-slate-500 dark:text-slate-400 font-semibold px-0.5">
         <span>Lower</span>
         <span className="tracking-tight text-slate-400">─────────</span>
         <span>Higher</span>
        </div>
       </div>

       {/* Discrete Tier Legend */}
       <div className="grid grid-cols-2 gap-1.5 pt-0.5 text-[10px]">
        <div className="flex items-center gap-1.5 bg-slate-50 dark:bg-slate-800/60 px-2 py-1 rounded-md border border-slate-100 dark:border-slate-800">
         <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: HISTORICAL_RISK_TIERS.LOWER.color }}
         />
         <span className="text-slate-600 dark:text-slate-300 font-medium">
          Lower (90+)
         </span>
        </div>
        <div className="flex items-center gap-1.5 bg-slate-50 dark:bg-slate-800/60 px-2 py-1 rounded-md border border-slate-100 dark:border-slate-800">
         <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: HISTORICAL_RISK_TIERS.MODERATE.color }}
         />
         <span className="text-slate-600 dark:text-slate-300 font-medium">
          Moderate (79-89)
         </span>
        </div>
        <div className="flex items-center gap-1.5 bg-slate-50 dark:bg-slate-800/60 px-2 py-1 rounded-md border border-slate-100 dark:border-slate-800">
         <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: HISTORICAL_RISK_TIERS.HIGHER.color }}
         />
         <span className="text-slate-600 dark:text-slate-300 font-medium">
          Higher (65-78)
         </span>
        </div>
        <div className="flex items-center gap-1.5 bg-slate-50 dark:bg-slate-800/60 px-2 py-1 rounded-md border border-slate-100 dark:border-slate-800">
         <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: HISTORICAL_RISK_TIERS.HIGHEST.color }}
         />
         <span className="text-slate-600 dark:text-slate-300 font-medium">
          Highest (&lt;65)
         </span>
        </div>
       </div>

       <p className="text-[9px] text-slate-400 dark:text-slate-500 leading-tight pt-0.5">
        Colors show risk. Separate from live traffic and weather.
       </p>
      </div>
     )}
    </div>
   )}
  </div>
 );
}
