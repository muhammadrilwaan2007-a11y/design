/**
 * useLocation.js
 * Custom hook wrapping the browser Geolocation API.
 *
 * Returns:
 *  location — { latitude, longitude, name } | null
 *  loading  — boolean, true while awaiting the browser
 *  error    — string | null, user-friendly message
 *  getLocation — function to trigger geolocation
 *  clearError  — function to dismiss the error
 */

import { useState, useCallback } from 'react';
import { reverseGeocode } from '../services/searchApi';

/** Map GeolocationPositionError codes to friendly messages. */
function humaniseError(err) {
  switch (err?.code) {
    case 1: // PERMISSION_DENIED
      return 'Location permission was denied. Please allow access in your browser settings, or type your starting point manually.';
    case 2: // POSITION_UNAVAILABLE
      return 'Your current location is unavailable. Please enter your starting point manually.';
    case 3: // TIMEOUT
      return 'Location request timed out. Please try again or enter your starting point manually.';
    default:
      return 'Unable to get your location. Please enter your starting point manually.';
  }
}

/**
 * Try to get position with the given options.
 * Returns a Promise that resolves with GeolocationPosition or rejects with GeolocationPositionError.
 */
function getPositionPromise(options) {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, reject, options);
  });
}

export function useLocation() {
  const [location, setLocation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const getLocation = useCallback(async () => {
    if (!navigator.geolocation) {
      setError('Geolocation is not supported by your browser. Please enter your starting point manually.');
      return;
    }

    setLoading(true);
    setError(null);

    let position = null;

    // Stage 1 — Low accuracy (uses Wi-Fi / IP / cell tower): fast and reliable on
    // all devices including desktops. No GPS hardware required.
    try {
      position = await getPositionPromise({
        enableHighAccuracy: false,
        timeout: 10_000,       // 10 s — should succeed almost immediately
        maximumAge: 60_000,    // Accept a cached position up to 1 min old
      });
    } catch (lowAccErr) {
      // Stage 2 — High accuracy fallback (GPS): only if low-accuracy also fails.
      // Mainly useful on mobile devices with GPS.
      try {
        position = await getPositionPromise({
          enableHighAccuracy: true,
          timeout: 20_000,     // 20 s for GPS acquisition
          maximumAge: 30_000,
        });
      } catch (highAccErr) {
        setError(humaniseError(highAccErr));
        setLoading(false);
        return;
      }
    }

    const { latitude, longitude } = position.coords;

    // Attempt reverse geocoding for a friendly label.
    // Falls back to coordinate string if API call fails.
    let name = 'Current Location';
    try {
      const label = await reverseGeocode(latitude, longitude);
      if (label) name = label;
    } catch {
      // Keep the default label — never crash on reverse geocode failure
    }

    setLocation({ latitude, longitude, name });
    setLoading(false);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { location, loading, error, getLocation, clearError };
}
