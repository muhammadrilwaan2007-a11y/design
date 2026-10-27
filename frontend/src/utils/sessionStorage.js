/**
 * frontend/src/utils/sessionStorage.js
 * =====================================
 * Utilities for persisting and restoring the RouteGuard AI user session
 * ONLY across page refreshes (F5 / reload in the existing page/tab).
 *
 * Uses window.sessionStorage exclusively so that when the browser tab or app
 * is closed, reopened, or restarted, the session is cleared and starts fresh.
 */

const STORAGE_KEY = 'saferoute_active_session_v1';

export function loadMapSession() {
  try {
    // Purge any legacy localStorage entry so closed/restarted app never restores stale routes
    localStorage.removeItem(STORAGE_KEY);

    // Only read from sessionStorage (retained across refresh in existing tab, discarded on close/restart)
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (err) {
    console.warn('[RouteGuard AI] Failed to parse saved session:', err);
    return null;
  }
}

export function saveMapSession(data) {
  try {
    const serialized = JSON.stringify(data);
    // Strictly sessionStorage — survives page refresh, cleared when app or tab is closed
    sessionStorage.setItem(STORAGE_KEY, serialized);
  } catch (err) {
    console.warn('[RouteGuard AI] Failed to save session:', err);
  }
}

export function clearMapSession() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_KEY);
  } catch (err) {
    console.warn('[RouteGuard AI] Failed to clear session:', err);
  }
}
