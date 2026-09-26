import { CircleMarker } from 'react-leaflet';

// Thresholds for traffic visualization
export function getTrafficColor(congestionRatio) {
 if (congestionRatio == null) return '#9ca3af'; // gray (unknown)
 if (congestionRatio < 0.25) return '#22c55e'; // green (low)
 if (congestionRatio < 0.50) return '#eab308'; // yellow (moderate)
 if (congestionRatio < 0.75) return '#f97316'; // orange (high)
 return '#ef4444'; // red (severe)
}

export function getTrafficLabel(congestionRatio) {
 if (congestionRatio == null) return 'Unknown';
 if (congestionRatio < 0.25) return 'Low';
 if (congestionRatio < 0.50) return 'Moderate';
 if (congestionRatio < 0.75) return 'High';
 return 'Severe';
}

/**
 * TrafficLayer
 * Renders traffic segment dots along candidate routes.
 * 
 * Props:
 * trafficData: Object where keys are route IDs and values are TrafficRouteResponse.
 * selectedRoute: The currently selected route object (to highlight its traffic, or fade others).
 */
export default function TrafficLayer({ trafficData, selectedRoute }) {
 if (!trafficData || Object.keys(trafficData).length === 0) return null;

 const elements = [];

 Object.entries(trafficData).forEach(([routeId, routeTraffic]) => {
  if (!routeTraffic || !routeTraffic.segments) return;

  // If a route is selected, only show full opacity for that route's traffic
  const isSelected = selectedRoute?.id === routeId;
  const hasSelection = selectedRoute !== null && selectedRoute !== undefined;
  const opacity = hasSelection ? (isSelected ? 1.0 : 0.2) : 0.8;
  const radius = isSelected ? 6 : 4;

  routeTraffic.segments.forEach((segment, idx) => {
   // Don't render if we have no coordinate or congestion ratio
   if (segment.latitude == null || segment.longitude == null) return;
   if (segment.congestion_ratio == null) return;

   const color = getTrafficColor(segment.congestion_ratio);

   elements.push(
    <CircleMarker
     key={`${routeId}-seg-${idx}`}
     center={[segment.latitude, segment.longitude]}
     radius={radius}
     pathOptions={{
      color: '#ffffff',
      weight: 1,
      fillColor: color,
      fillOpacity: opacity,
      opacity: opacity
     }}
    />
   );
  });
 });

 return <>{elements}</>;
}
