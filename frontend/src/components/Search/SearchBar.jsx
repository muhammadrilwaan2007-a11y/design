/**
 * SearchBar.jsx
 * Dual-input search panel (Source + Destination) with TomTom autocomplete.
 *
 * Props:
 *  source       — { name, latitude, longitude } | null
 *  destination     — { name, latitude, longitude } | null
 *  selectedType    — 'source' | 'destination'
 *  onSourceChange   — (place) => void
 *  onDestinationChange — (place) => void
 *  onTypeChange    — ('source' | 'destination') => void
 *  userCoords     — { latitude, longitude } | null (bias results)
 *  locationLoading   — boolean
 *  locationError    — string | null
 *  onRequestLocation  — () => void
 */

import { useRef, useState, useEffect, useCallback } from 'react';
import { Navigation2, Search, X } from 'lucide-react';
import { useSearch } from '../../hooks/useSearch';
import LocationButton from '../Map/LocationButton';
import SearchSuggestions from './SearchSuggestions';

export default function SearchBar({
 source,
 destination,
 selectedType,
 onSourceChange,
 onDestinationChange,
 onTypeChange,
 userCoords,
 locationLoading,
 locationError,
 onRequestLocation,
}) {
 const [sourceText,    setSourceText]    = useState('');
 const [destText,     setDestText]     = useState('');
 const [activeSuggestions, setActiveSuggestions] = useState(null);

 const sourceRef = useRef(null);
 const destRef  = useRef(null);

 const {
  suggestions,
  loading: searchLoading,
  error:  searchError,
  search,
  clearSuggestions,
 } = useSearch();

 useEffect(() => { if (source)   setSourceText(source.name);   }, [source]);
 useEffect(() => { if (destination) setDestText(destination.name);  }, [destination]);

 // ── Handlers ─────────────────────────────────────────────────────────────

 const handleSourceChange = useCallback((e) => {
  const val = e.target.value;
  setSourceText(val);
  setActiveSuggestions('source');
  onTypeChange('source');
  search(val, userCoords?.latitude, userCoords?.longitude);
 }, [search, userCoords, onTypeChange]);

 const handleDestChange = useCallback((e) => {
  const val = e.target.value;
  setDestText(val);
  setActiveSuggestions('destination');
  onTypeChange('destination');
  search(val, userCoords?.latitude, userCoords?.longitude);
 }, [search, userCoords, onTypeChange]);

 const handleSelect = useCallback((suggestion) => {
  if (activeSuggestions === 'source') {
   setSourceText(suggestion.name);
   onSourceChange(suggestion);
  } else {
   setDestText(suggestion.name);
   onDestinationChange(suggestion);
  }
  clearSuggestions();
  setActiveSuggestions(null);
 }, [activeSuggestions, onSourceChange, onDestinationChange, clearSuggestions]);

 const handleSourceFocus = useCallback(() => {
  onTypeChange('source');
  if (sourceText.trim().length >= 2) {
   setActiveSuggestions('source');
   search(sourceText, userCoords?.latitude, userCoords?.longitude);
  }
 }, [sourceText, onTypeChange, search, userCoords]);

 const handleDestFocus = useCallback(() => {
  onTypeChange('destination');
  if (destText.trim().length >= 2) {
   setActiveSuggestions('destination');
   search(destText, userCoords?.latitude, userCoords?.longitude);
  }
 }, [destText, onTypeChange, search, userCoords]);

 const clearSource = useCallback(() => {
  setSourceText('');
  onSourceChange(null);
  clearSuggestions();
  setActiveSuggestions(null);
  sourceRef.current?.focus();
 }, [onSourceChange, clearSuggestions]);

 const clearDest = useCallback(() => {
  setDestText('');
  onDestinationChange(null);
  clearSuggestions();
  setActiveSuggestions(null);
  destRef.current?.focus();
 }, [onDestinationChange, clearSuggestions]);

 useEffect(() => {
  const handleOutsideClick = (e) => {
   if (!e.target.closest('#search-bar-panel')) {
    clearSuggestions();
    setActiveSuggestions(null);
   }
  };
  document.addEventListener('mousedown', handleOutsideClick);
  return () => document.removeEventListener('mousedown', handleOutsideClick);
 }, [clearSuggestions]);

 const showSuggestions =
  activeSuggestions !== null &&
  (searchLoading || searchError || suggestions.length > 0);

 // ── Input row base classes ────────────────────────────────────────────────
 const inputRowBase =
  'flex items-center gap-1.5 rounded-lg border transition-all ' +
  'bg-white dark:bg-slate-800 ';

 const sourceRowCls =
  inputRowBase +
  'pr-1 pl-3 ' +
  (selectedType === 'source'
   ? 'border-primary-400 ring-2 ring-primary-100 dark:ring-primary-900'
   : 'border-slate-200 dark:border-slate-600');

 const destRowCls =
  inputRowBase +
  'pr-2 pl-3 ' +
  (selectedType === 'destination'
   ? 'border-secondary-500 ring-2 ring-teal-100 dark:ring-teal-900'
   : 'border-slate-200 dark:border-slate-600');

 const inputCls =
  'flex-1 py-2.5 text-sm bg-transparent outline-none min-w-0 ' +
  'text-slate-800 dark:text-slate-100 ' +
  'placeholder:text-slate-400 dark:placeholder:text-slate-500';

 const clearBtnCls =
  'p-1 rounded text-slate-400 dark:text-slate-500 ' +
  'hover:text-slate-600 dark:hover:text-slate-300';

 return (
  <div
   id="search-bar-panel"
   className="
    search-panel rounded-xl border shadow-card
    bg-white dark:bg-slate-800
    border-slate-200 dark:border-slate-700
   "
  >
   {/* ── Brand header ──────────────────────────────────────────────── */}
   <div className="flex items-center gap-2 px-4 pt-4 pb-2">
    <Navigation2
     size={20}
     className="text-primary-600 dark:text-primary-400"
     strokeWidth={2.5}
    />
    <span className="font-semibold text-sm text-primary-700 dark:text-primary-300 tracking-wide">
     RouteGuard AI
    </span>
    <span className="ml-auto text-xs text-slate-400 dark:text-slate-500 font-medium">
     Bengaluru
    </span>
   </div>

   <div className="px-3 pb-3 space-y-2">
    {/* ── Source input ──────────────────────────────────────────── */}
    <div className="relative">
     <label htmlFor="source-input" className="sr-only">Starting point</label>
     <div className={sourceRowCls}>
      <span className="w-2.5 h-2.5 rounded-full bg-primary-500 shrink-0" aria-hidden="true" />
      <input
       id="source-input"
       ref={sourceRef}
       type="text"
       value={sourceText}
       onChange={handleSourceChange}
       onFocus={handleSourceFocus}
       placeholder={locationLoading ? 'Getting your location…' : 'Your location / Starting point'}
       disabled={locationLoading}
       autoComplete="off"
       spellCheck={false}
       className={inputCls}
      />
      {sourceText && !locationLoading && (
       <button type="button" onClick={clearSource} aria-label="Clear source" className={clearBtnCls}>
        <X size={14} />
       </button>
      )}
      <LocationButton
       onClick={onRequestLocation}
       loading={locationLoading}
       error={activeSuggestions !== 'source' ? null : locationError}
      />
     </div>

     {activeSuggestions === 'source' && (
      <SearchSuggestions
       suggestions={suggestions}
       loading={searchLoading}
       error={searchError}
       onSelect={handleSelect}
       visible={showSuggestions}
      />
     )}
    </div>

    {/* ── Destination input ──────────────────────────────────────── */}
    <div className="relative">
     <label htmlFor="destination-input" className="sr-only">Destination</label>
     <div className={destRowCls}>
      <span className="w-2.5 h-2.5 rounded-full bg-secondary-500 shrink-0" aria-hidden="true" />
      <Search size={14} className="text-slate-400 dark:text-slate-500 shrink-0" />
      <input
       id="destination-input"
       ref={destRef}
       type="text"
       value={destText}
       onChange={handleDestChange}
       onFocus={handleDestFocus}
       placeholder="Where do you want to go?"
       autoComplete="off"
       spellCheck={false}
       className={inputCls}
      />
      {destText && (
       <button type="button" onClick={clearDest} aria-label="Clear destination" className={clearBtnCls}>
        <X size={14} />
       </button>
      )}
     </div>

     {activeSuggestions === 'destination' && (
      <SearchSuggestions
       suggestions={suggestions}
       loading={searchLoading}
       error={searchError}
       onSelect={handleSelect}
       visible={showSuggestions}
      />
     )}
    </div>

    {/* ── Location error ────────────────────────────────────────── */}
    {locationError && activeSuggestions !== 'source' && (
     <p className="text-xs text-red-500 dark:text-red-400 px-1 flex items-start gap-1.5">
      <span className="shrink-0 mt-0.5">⚠</span>
      {locationError}
     </p>
    )}

    {/* ── Status chip ──────────────────────────────────────────────── */}
    {source && destination && (
     <div className="flex items-center gap-1.5 mt-1 px-1">
      <span className="inline-flex items-center gap-1 text-xs font-medium text-secondary-600 dark:text-teal-300 bg-teal-50 dark:bg-teal-900/40 border border-teal-200 dark:border-teal-700 rounded-full px-2.5 py-0.5">
       ✓ Route ready to plan
      </span>
     </div>
    )}
   </div>
  </div>
 );
}
