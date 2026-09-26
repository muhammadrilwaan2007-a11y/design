/**
 * RouteLayer.jsx
 * Renders all candidate route polylines on the Leaflet map.
 *
 * Props:
 *  routes    — Array<RouteResponse>
 *  selectedRoute — RouteResponse | null
 *  onSelectRoute — (route) => void
 *
 * Each route.geometry is a GeoJSON LineString:
 *  { type: "LineString", coordinates: [[lon, lat], ...] }
 *
 * Leaflet uses [lat, lon] — this component handles the conversion.
 *
 * Module 3+ will add safety-coloured segments on top of these base polylines.
 */

import { Fragment, useEffect } from 'react';
import { Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';

/**
 * FitRouteBounds — child component that fits the map to all route geometries.
 * Rendered inside <MapContainer> so it has access to the Leaflet map instance.
 */
function FitRouteBounds({ routes }) {
 const map = useMap();

 useEffect(() => {
  if (!routes || routes.length === 0) return;

  // Collect all [lat, lon] points across all route geometries
  const allPoints = routes.flatMap((route) =>
   (route.geometry?.coordinates ?? []).map(([lon, lat]) => [lat, lon]),
  );

  if (allPoints.length === 0) return;

  const bounds = L.latLngBounds(allPoints);
  map.fitBounds(bounds, { padding: [60, 60], maxZoom: 16, animate: true });
 }, [routes, map]);

 return null;
}

/**
 * GeoJSON LineString coordinates are [longitude, latitude].
 * Leaflet expects [latitude, longitude].
 */
function toLeafletPositions(coordinates) {
 return coordinates.map(([lon, lat]) => [lat, lon]);
}

export default function RouteLayer({
 routes = [],
 selectedRoute,
 onSelectRoute,
 closureMap = {},
}) {
 if (!routes.length) return null;

 const hasSelection = selectedRoute !== null && selectedRoute !== undefined;

 return (
  <>
   {/* Fit map to all routes whenever they change */}
   <FitRouteBounds routes={routes} />

   {routes.map((route, idx) => {
    const positions = toLeafletPositions(route.geometry?.coordinates ?? []);
    if (positions.length < 2) return null;

    const isSelected = selectedRoute?.id === route.id;
    const hasClosure = closureMap?.[route.id]?.hasClosure ?? false;

    // Vivid Blue Palette for crystal-clear navigation visibility
    const mainColor = isSelected
     ? '#2563EB' // Solid royal navigation blue
     : (idx === 0 ? '#3B82F6' : '#60A5FA'); // Sky blue for alternatives

    const mainWeight = isSelected ? 6.5 : 4.5;
    const mainOpacity = isSelected ? 1.0 : (hasSelection ? 0.65 : 0.85);

    return (
     <Fragment key={route.id}>
      {/* White halo casing under the selected route for crisp contrast against any background */}
      {isSelected && (
       <Polyline
        key={`${route.id}-halo`}
        positions={positions}
        pathOptions={{
         color: '#1146A6', // Dark blue casing like Google Maps
         weight: 10.5,
         opacity: 0.90,
         lineCap: 'round',
         lineJoin: 'round',
        }}
       />
      )}

      {/* Primary Navigation Polyline — Bold, crisp, vivid BLUE */}
      <Polyline
       key={`${route.id}-main`}
       positions={positions}
       pathOptions={{
        color: mainColor,
        weight: mainWeight,
        opacity: mainOpacity,
        lineCap: 'round',
        lineJoin: 'round',
        dashArray: hasClosure ? '8, 8' : undefined,
       }}
       eventHandlers={{
        click: () => onSelectRoute?.(route),
        mouseover: (e) => {
         if (!isSelected) e.target.setStyle({ opacity: 0.95, weight: 6 });
        },
        mouseout: (e) => {
         if (!isSelected) e.target.setStyle({ opacity: mainOpacity, weight: mainWeight });
        },
       }}
      />
     </Fragment>
    );
   })}
  </>
 );
}
