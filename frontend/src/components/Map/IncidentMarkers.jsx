/**
 * frontend/src/components/Map/IncidentMarkers.jsx
 * Module 4 — Live Incident Detection
 *
 * Renders Leaflet markers for route-relevant incidents.
 * Each incident type gets a distinct colored icon.
 * Clicking a marker shows a popup with full incident details.
 *
 * Props:
 *  incidentData  — { [routeId]: RouteIncidentAnalysis }
 *  selectedRoute — RouteResponse | null (used to filter which incidents show)
 */

import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';

// ── Icon colors by incident type ────────────────────────────────────────────

function getIncidentStyle(type, iconCategory) {
 // Use explicit icon category from TomTom if available
 if (iconCategory !== undefined && iconCategory !== null) {
  switch (iconCategory) {
   case 1: return { bg: '#ef4444', emoji: '🚨' }; // Accident
   case 2: return { bg: '#6b7280', emoji: '🌫️' }; // Fog
   case 3: return { bg: '#dc2626', emoji: '⚠️' }; // Dangerous Conditions
   case 4: return { bg: '#6b7280', emoji: '🌧️' }; // Rain
   case 5: return { bg: '#6b7280', emoji: '❄️' }; // Ice
   case 6: return { bg: '#eab308', emoji: '🚗' }; // Jam
   case 7: return { bg: '#9333ea', emoji: '⛔' }; // Lane Closed
   case 8: return { bg: '#7c3aed', emoji: '🚧' }; // Road Closed
   case 9: return { bg: '#f97316', emoji: '🔨' }; // Road Works
   case 10: return { bg: '#6b7280', emoji: '💨' }; // Wind
   case 11: return { bg: '#dc2626', emoji: '🌊' }; // Flooding
   case 14: return { bg: '#a16207', emoji: '🚘' }; // Broken Down Vehicle
  }
 }

 // Fallback to text matching
 const t = (type || '').toLowerCase();
 if (t.includes('accident'))      return { bg: '#ef4444', emoji: '🚨' };
 if (t.includes('road clos') || t === 'closed') return { bg: '#7c3aed', emoji: '🚧' };
 if (t.includes('lane clos'))     return { bg: '#9333ea', emoji: '⛔' };
 if (t.includes('road work') || t.includes('roadwork')) return { bg: '#f97316', emoji: '🔨' };
 if (t.includes('jam') || t.includes('traffic')) return { bg: '#eab308', emoji: '🚗' };
 if (t.includes('dangerous') || t.includes('flood')) return { bg: '#dc2626', emoji: '⚠️' };
 if (t.includes('fog') || t.includes('rain') || t.includes('ice') || t.includes('wind'))
  return { bg: '#6b7280', emoji: '🌧️' };
 if (t.includes('broken'))       return { bg: '#a16207', emoji: '🚘' };
 return { bg: '#3b82f6', emoji: '📍' };
}

function makeIncidentIcon(type, iconCategory) {
 const { bg, emoji } = getIncidentStyle(type, iconCategory);
 return L.divIcon({
  className: '',
  html: `
   <div style="
    background: ${bg};
    border: 2px solid white;
    border-radius: 50%;
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.35);
    cursor: pointer;
   ">${emoji}</div>`,
  iconSize: [28, 28],
  iconAnchor: [14, 14],
  popupAnchor: [0, -16],
 });
}

function formatDelay(seconds) {
 if (!seconds || seconds <= 0) return null;
 const mins = Math.round(seconds / 60);
 if (mins < 60) return `+${mins} min delay`;
 return `+${Math.floor(mins / 60)} h ${mins % 60} min delay`;
}

function formatLength(meters) {
 if (!meters) return null;
 if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km affected`;
 return `${Math.round(meters)} m affected`;
}

// ── Component ────────────────────────────────────────────────────────────────

export default function IncidentMarkers({ incidentData, selectedRoute }) {
 if (!incidentData || Object.keys(incidentData).length === 0) return null;

 const markers = [];
 const hasSelection = !!selectedRoute;

 // Determine which route IDs to show
 const routeIds = hasSelection
  ? [selectedRoute.id]
  : Object.keys(incidentData);

 routeIds.forEach((routeId) => {
  const analysis = incidentData[routeId];
  if (!analysis || !analysis.incidents) return;

  analysis.incidents.forEach((incident, idx) => {
   if (!incident.is_route_relevant) return;

   const icon = makeIncidentIcon(incident.type, incident.icon_category);
   const delay = formatDelay(incident.delay_seconds);
   const length = formatLength(incident.length_meters);

   markers.push(
    <Marker
     key={`${routeId}-incident-${incident.id}-${idx}`}
     position={[incident.latitude, incident.longitude]}
     icon={icon}
    >
     <Popup maxWidth={280} className="incident-popup">
      <div style={{ fontFamily: 'Inter, sans-serif', fontSize: '13px', lineHeight: '1.5' }}>
       {/* Type badge */}
       <div style={{
        display: 'flex', alignItems: 'center', gap: '6px',
        marginBottom: '6px',
       }}>
        <span style={{
         background: getIncidentStyle(incident.type, incident.icon_category).bg,
         color: 'white',
         padding: '2px 8px',
         borderRadius: '99px',
         fontSize: '11px',
         fontWeight: 700,
        }}>
         {incident.type}
        </span>
       </div>

       {/* Description */}
       {incident.description && incident.description !== incident.type && (
        <p style={{ margin: '0 0 4px', color: '#374151' }}>{incident.description}</p>
       )}

       {/* Road name */}
       {incident.road_name && (
        <p style={{ margin: '0 0 2px', fontWeight: 600, color: '#1f2937' }}>
         🛣️ {incident.road_name}
        </p>
       )}

       {/* From → To */}
       {(incident.from_location || incident.to_location) && (
        <p style={{ margin: '0 0 4px', color: '#6b7280', fontSize: '12px' }}>
         {incident.from_location}
         {incident.from_location && incident.to_location && ' → '}
         {incident.to_location}
        </p>
       )}

       {/* Metrics */}
       {(delay || length) && (
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '4px' }}>
         {delay && (
          <span style={{
           background: '#fef3c7', color: '#92400e',
           padding: '2px 6px', borderRadius: '4px', fontSize: '11px',
          }}>⏱ {delay}</span>
         )}
         {length && (
          <span style={{
           background: '#e0e7ff', color: '#3730a3',
           padding: '2px 6px', borderRadius: '4px', fontSize: '11px',
          }}>📏 {length}</span>
         )}
        </div>
       )}

       {/* Distance from route */}
       {incident.distance_to_route_m != null && (
        <p style={{ margin: '6px 0 0', color: '#9ca3af', fontSize: '11px' }}>
         📌 {Math.round(incident.distance_to_route_m)} m from route
        </p>
       )}

       {/* Last reported */}
       {incident.last_report_time && (
        <p style={{ margin: '2px 0 0', color: '#9ca3af', fontSize: '11px' }}>
         Last reported: {new Date(incident.last_report_time).toLocaleTimeString()}
        </p>
       )}
      </div>
     </Popup>
    </Marker>
   );
  });
 });

 return <>{markers}</>;
}
