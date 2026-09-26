/**
 * LocationButton.jsx
 * "Use my current location" button — supports light and dark mode.
 */

import { LocateFixed, Loader2 } from 'lucide-react';

export default function LocationButton({ onClick, loading = false, error = null }) {
 return (
  <div className="relative">
   <button
    id="current-location-btn"
    type="button"
    onClick={onClick}
    disabled={loading}
    aria-label="Use my current location"
    title={error || 'Use my current location'}
    className={[
     'flex items-center justify-center',
     'w-9 h-9 rounded-lg border transition-all duration-150',
     'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1',
     loading
      ? 'bg-primary-50 dark:bg-primary-900/30 border-primary-200 dark:border-primary-700 cursor-wait'
      : error
      ? 'bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-700 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/50'
      : 'bg-white dark:bg-slate-700 border-slate-200 dark:border-slate-600 text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/30 hover:border-primary-300 dark:hover:border-primary-500 active:scale-95',
    ].join(' ')}
   >
    {loading ? (
     <Loader2 size={17} className="animate-spin text-primary-500" />
    ) : (
     <LocateFixed size={17} />
    )}
   </button>

   {error && !loading && (
    <div
     role="alert"
     className="
      absolute left-0 top-full mt-1 z-50
      w-64 p-2.5 rounded-lg
      bg-red-50 dark:bg-red-900/60
      border border-red-200 dark:border-red-700
      text-xs text-red-700 dark:text-red-300
      shadow-md
     "
    >
     {error}
    </div>
   )}
  </div>
 );
}
