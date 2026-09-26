/**
 * MapView.jsx
 * React-Leaflet map component.
 *
 * Props:
 *  source     — { latitude, longitude, name } | null
 *  destination   — { latitude, longitude, name } | null
 *  currentLocation — { latitude, longitude } | null
 *  mapRef     — ref forwarded from parent for imperative access
 */

import { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import RouteLayer from './RouteLayer';
import TrafficLayer from './TrafficLayer';
import IncidentMarkers from './IncidentMarkers';
import HistoricalRiskHeatmap from './HistoricalRiskHeatmap';

// ── Leaflet icon fix (Vite bundler doesn't inline image URLs) ────────────
import markerIconPng  from 'leaflet/dist/images/marker-icon.png';
import markerIconRetina from 'leaflet/dist/images/marker-icon-2x.png';
import markerShadowPng from 'leaflet/dist/images/marker-shadow.png';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
 iconUrl:    markerIconPng,
 iconRetinaUrl: markerIconRetina,
 shadowUrl:   markerShadowPng,
});

// ── Bengaluru centre ──────────────────────────────────────────────────────
const BENGALURU_CENTER = [12.9716, 77.5946];
const DEFAULT_ZOOM   = 13;

// ── Tile layers ──────────────────────────────────────────────────────────
// Official OpenStreetMap tile layer — 100% free, reliable, no API key or watermark needed.
// Theme appearance (clean pastel in light mode, sleek dark in dark mode) is handled
// gracefully via refined CSS filters in index.css.
const OSM_TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

// ── Custom icons ─────────────────────────────────────────────────────────

/** Blue pulsing dot — current GPS location */
const currentLocationIcon = L.divIcon({
 className: '',
 html: `
  <div style="
   position: relative;
   width: 20px;
   height: 20px;
  ">
   <!-- Outer pulse ring -->
   <div style="
    position: absolute;
    inset: -6px;
    border-radius: 50%;
    background: rgba(37,99,235,0.18);
    animation: pulse-ring 2s ease-out infinite;
   "></div>
   <!-- Inner dot -->
   <div class="current-location-dot" style="
    width: 20px;
    height: 20px;
    background: #2563EB;
    border: 3px solid white;
    border-radius: 50%;
    box-shadow: 0 2px 6px rgba(37,99,235,0.5);
   "></div>
  </div>
  <style>
   @keyframes pulse-ring {
    0%  { transform: scale(0.8); opacity: 1; }
    100% { transform: scale(2.2); opacity: 0; }
   }
  </style>
 `,
 iconSize:  [20, 20],
 iconAnchor: [10, 10],
 popupAnchor:[0, -14],
});

/** Red teardrop pin — source */
const sourceIcon = L.divIcon({
 className: '',
 html: `
  <svg width="28" height="38" viewBox="0 0 28 38" fill="none" xmlns="http://www.w3.org/2000/svg">
   <path d="M14 0C6.268 0 0 6.268 0 14C0 24.5 14 38 14 38C14 38 28 24.5 28 14C28 6.268 21.732 0 14 0Z" fill="#2563EB"/>
   <circle cx="14" cy="14" r="6" fill="white"/>
  </svg>
 `,
 iconSize:  [28, 38],
 iconAnchor: [14, 38],
 popupAnchor:[0, -40],
});

/** Green teardrop pin — destination */
const destinationIcon = L.divIcon({
 className: '',
 html: `
  <svg width="28" height="38" viewBox="0 0 28 38" fill="none" xmlns="http://www.w3.org/2000/svg">
   <path d="M14 0C6.268 0 0 6.268 0 14C0 24.5 14 38 14 38C14 38 28 24.5 28 14C28 6.268 21.732 0 14 0Z" fill="#14B8A6"/>
   <circle cx="14" cy="14" r="6" fill="white"/>
  </svg>
 `,
 iconSize:  [28, 38],
 iconAnchor: [14, 38],
 popupAnchor:[0, -40],
});

// ── Recentre helper component ─────────────────────────────────────────────
/**
 * Rendered inside MapContainer so it has access to the Leaflet map instance.
 * Watches the `target` prop and pans/zooms the map whenever it changes.
 */
function FlyToTarget({ target }) {
 const map = useMap();

 useEffect(() => {
  if (!target) return;
  map.flyTo([target.latitude, target.longitude], 15, {
   duration: 1.2,
   easeLinearity: 0.35,
  });
 }, [target, map]);

 return null;
}

/**
 * Fit both markers in view when both source and destination are set.
 */
function FitBounds({ source, destination }) {
 const map = useMap();

 useEffect(() => {
  if (!source || !destination) return;
  const bounds = L.latLngBounds(
   [source.latitude, source.longitude],
   [destination.latitude, destination.longitude],
  );
  map.fitBounds(bounds, { padding: [60, 60], maxZoom: 16, duration: 1 });
 }, [source, destination, map]);

 return null;
}

/**
 * Track user pans and zooms to preserve viewport across refreshes.
 */
function MapStateTracker({ onMapMove }) {
 const map = useMap();
 useEffect(() => {
  if (!onMapMove) return;
  const handleMove = () => {
   const c = map.getCenter();
   onMapMove({
    center: [c.lat, c.lng],
    zoom: map.getZoom(),
   });
  };
  map.on('moveend', handleMove);
  return () => {
   map.off('moveend', handleMove);
  };
 }, [map, onMapMove]);

 return null;
}

// ── Main component ────────────────────────────────────────────────────────
export default function MapView({
 source,
 destination,
 currentLocation,
 isDark = false,
 routes = [],
 selectedRoute = null,
 onSelectRoute,
 trafficData = {},
 incidentData = {},
 heatmapEdges = [],
 showHistoricalRisk = true,
 showTraffic = true,
 showIncidents = true,
 closureMap = {},
 initialCenter = null,
 initialZoom = null,
 onMapMove = null,
}) {
 // Track which location to fly to (last changed)
 const flyTarget = destination || source || currentLocation || null;

 return (
  <MapContainer
   center={initialCenter || BENGALURU_CENTER}
   zoom={initialZoom || DEFAULT_ZOOM}
   className="w-full h-full"
   zoomControl={true}
   attributionControl={false}
   id="saferoute-map"
  >
   <MapStateTracker onMapMove={onMapMove} />
   {/* Base tile layer — Official OpenStreetMap (no key or watermark required) */}
   <TileLayer
    url={OSM_TILE_URL}
    attribution={OSM_ATTRIBUTION}
    maxZoom={19}
   />

   {/* ── Current location marker ── */}
   {currentLocation && (
    <Marker
     position={[currentLocation.latitude, currentLocation.longitude]}
     icon={currentLocationIcon}
    >
     <Popup>
      <div className="text-sm font-medium text-primary-700">
       📍 Your current location
      </div>
     </Popup>
    </Marker>
   )}

   {/* ── Source marker ── */}
   {source && (
    <Marker
     position={[source.latitude, source.longitude]}
     icon={sourceIcon}
    >
     <Popup>
      <div className="text-sm">
       <div className="font-semibold text-primary-700">Start</div>
       <div className="text-slate-600 text-xs mt-0.5">{source.name}</div>
      </div>
     </Popup>
    </Marker>
   )}

   {/* ── Destination marker ── */}
   {destination && (
    <Marker
     position={[destination.latitude, destination.longitude]}
     icon={destinationIcon}
    >
     <Popup>
      <div className="text-sm">
       <div className="font-semibold text-secondary-600">Destination</div>
       <div className="text-slate-600 text-xs mt-0.5">{destination.name}</div>
      </div>
     </Popup>
    </Marker>
   )}

   {/* ── Risk Heatmap (background city road risk context) ── */}
   <HistoricalRiskHeatmap
    heatmapEdges={heatmapEdges}
    visible={showHistoricalRisk}
    isDark={isDark}
   />

   {/* ── Route polylines (primary navigation path — rendered ON TOP so route is clearly visible and BLUE) ── */}
   <RouteLayer
    routes={routes}
    selectedRoute={selectedRoute}
    onSelectRoute={onSelectRoute}
    showHistoricalRisk={showHistoricalRisk}
    closureMap={closureMap}
   />

   {/* ── Traffic indicators (independent layer) ── */}
   {showTraffic && (
    <TrafficLayer
     trafficData={trafficData}
     selectedRoute={selectedRoute}
    />
   )}

   {/* ── Incident markers (independent layer) ── */}
   {showIncidents && (
    <IncidentMarkers
     incidentData={incidentData}
     selectedRoute={selectedRoute}
    />
   )}

   {/* Fly to the most recent change (only when no routes displayed) */}
   {!destination && routes.length === 0 && <FlyToTarget target={flyTarget} />}

   {/* Fit markers when both set but no routes yet */}
   {source && destination && routes.length === 0 && (
    <FitBounds source={source} destination={destination} />
   )}
  </MapContainer>
 );
}
