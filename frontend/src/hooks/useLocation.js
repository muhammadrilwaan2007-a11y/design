/**
 * useLocation.js
 * Custom hook wrapping the browser Geolocation API.
 *
 * Returns:
 *  location — { latitude, longitude, name } | null
 *  loading  — boolean, true while awaiting the browser
 *  error   — string | null, user-friendly message
 *  getLocation — function to trigger geolocation
 *  clearError — function to dismiss the error
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

export function useLocation() {
 const [location, setLocation] = useState(null);
 const [loading, setLoading] = useState(false);
 const [error,  setError]  = useState(null);

 const getLocation = useCallback(() => {
  if (!navigator.geolocation) {
   setError('Geolocation is not supported by your browser. Please enter your starting point manually.');
   return;
  }

  setLoading(true);
  setError(null);

  navigator.geolocation.getCurrentPosition(
   async (position) => {
    const { latitude, longitude } = position.coords;

    // Attempt reverse geocoding for a friendly label.
    // Falls back to coordinate string if API key is not set.
    let name = 'Current Location';
    try {
     const label = await reverseGeocode(latitude, longitude);
     if (label) name = label;
    } catch {
     // Keep the default label — never crash on reverse geocode failure
    }

    setLocation({ latitude, longitude, name });
    setLoading(false);
   },
   (err) => {
    setError(humaniseError(err));
    setLoading(false);
   },
   {
    enableHighAccuracy: true,
    timeout:      10_000, // 10 s
    maximumAge:     30_000, // Accept a cached position up to 30 s old
   },
  );
 }, []);

 const clearError = useCallback(() => setError(null), []);

 return { location, loading, error, getLocation, clearError };
}
