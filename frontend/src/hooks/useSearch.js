/**
 * useSearch.js
 * Debounced TomTom search hook.
 *
 * Returns:
 *  suggestions  — Array<{id, name, address, latitude, longitude, type}>
 *  loading    — boolean
 *  error     — string | null
 *  search    — (query, lat?, lon?) => void — trigger a search
 *  clearSuggestions — () => void
 */

import { useState, useCallback, useRef } from 'react';
import { searchPlaces } from '../services/searchApi';

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 2;

export function useSearch() {
 const [suggestions, setSuggestions] = useState([]);
 const [loading,   setLoading]   = useState(false);
 const [error,    setError]    = useState(null);

 // Store the debounce timer so we can cancel it on each new keystroke.
 const timerRef = useRef(null);
 // Store an AbortController ref to cancel in-flight requests on new ones.
 const controllerRef = useRef(null);

 const search = useCallback((query, lat, lon) => {
  // Clear previous debounce timer
  if (timerRef.current) {
   clearTimeout(timerRef.current);
  }

  const trimmed = query?.trim() ?? '';

  // Immediately clear if query is too short
  if (trimmed.length < MIN_QUERY_LENGTH) {
   setSuggestions([]);
   setLoading(false);
   setError(null);
   return;
  }

  setLoading(true);
  setError(null);

  timerRef.current = setTimeout(async () => {
   // Cancel any in-flight request
   if (controllerRef.current) {
    controllerRef.current.abort();
   }
   controllerRef.current = new AbortController();

   try {
    const results = await searchPlaces(query, lat, lon);
    setSuggestions(results);
   } catch (err) {
    // Ignore aborted-request errors (new query superseded this one)
    if (err?.name === 'AbortError') return;

    console.error('[useSearch]', err);

    if (err?.message?.includes('API key')) {
     setError('Search is unavailable — API key not configured.');
    } else if (!navigator.onLine) {
     setError('No internet connection. Please check your network.');
    } else {
     setError('Search is temporarily unavailable. Please try again.');
    }
    setSuggestions([]);
   } finally {
    setLoading(false);
   }
  }, DEBOUNCE_MS);
 }, []);

 const clearSuggestions = useCallback(() => {
  if (timerRef.current) clearTimeout(timerRef.current);
  setSuggestions([]);
  setLoading(false);
  setError(null);
 }, []);

 return { suggestions, loading, error, search, clearSuggestions };
}
