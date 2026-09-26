/**
 * SearchSuggestions.jsx
 * Dropdown list of TomTom search suggestions.
 *
 * Props:
 *  suggestions — Array<{id, name, address, latitude, longitude}>
 *  loading   — boolean
 *  error    — string | null
 *  onSelect   — (suggestion) => void
 *  visible   — boolean — controls visibility
 */

import { MapPin, Loader2, SearchX, AlertCircle } from 'lucide-react';

export default function SearchSuggestions({
 suggestions = [],
 loading = false,
 error = null,
 onSelect,
 visible = false,
}) {
 if (!visible) return null;

 // ── Loading state ────────────────────────────────────────────────────────
 if (loading) {
  return (
   <div className="suggestions-wrapper" role="status" aria-live="polite">
    <div className="flex items-center gap-2 px-4 py-3 text-sm text-slate-500">
     <Loader2 size={16} className="animate-spin text-primary-600 shrink-0" />
     <span>Searching…</span>
    </div>
   </div>
  );
 }

 // ── Error state ──────────────────────────────────────────────────────────
 if (error) {
  return (
   <div className="suggestions-wrapper" role="alert">
    <div className="flex items-start gap-2 px-4 py-3 text-sm text-red-600">
     <AlertCircle size={16} className="shrink-0 mt-0.5" />
     <span>{error}</span>
    </div>
   </div>
  );
 }

 // ── No results ───────────────────────────────────────────────────────────
 if (suggestions.length === 0) {
  return (
   <div className="suggestions-wrapper" role="status">
    <div className="flex items-center gap-2 px-4 py-3 text-sm text-slate-500">
     <SearchX size={16} className="shrink-0" />
     <span>No results found. Try a different search term.</span>
    </div>
   </div>
  );
 }

 // ── Results list ─────────────────────────────────────────────────────────
 return (
  <ul
   className="suggestions-wrapper"
   role="listbox"
   aria-label="Search suggestions"
  >
   {suggestions.map((suggestion, idx) => (
    <li
     key={suggestion.id || idx}
     role="option"
     aria-selected="false"
     className="suggestion-item group"
     onClick={() => onSelect?.(suggestion)}
     onKeyDown={(e) => {
      if (e.key === 'Enter' || e.key === ' ') {
       e.preventDefault();
       onSelect?.(suggestion);
      }
     }}
     tabIndex={0}
    >
     {/* Icon */}
     <span className="suggestion-icon">
      <MapPin size={15} className="text-primary-600" />
     </span>

     {/* Text */}
     <span className="suggestion-text">
      <span className="suggestion-name">{suggestion.name}</span>
      {suggestion.address && (
       <span className="suggestion-address">{suggestion.address}</span>
      )}
     </span>
    </li>
   ))}
  </ul>
 );
}
