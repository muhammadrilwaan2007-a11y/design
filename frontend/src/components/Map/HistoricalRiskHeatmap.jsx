/**
 * frontend/src/components/Map/HistoricalRiskHeatmap.jsx
 * ====================================================
 * High-polish GIS rendering of historical road-risk predictions
 * directly on OpenStreetMap road edges for the SafeRoute AI Leaflet map.
 *
 * Visual Excellence & Polish Features:
 *  - Adaptive hierarchy-based line widths (arterials stand out, residential streets stay subtle)
 *  - Soft ambient aura casing (eliminates harsh blunt intersections and visual clutter)
 *  - Clean semi-transparent opacity (0.76) preserving street labels, arrows, and buildings
 *  - Z-index ordering (high-risk throughways flow smoothly on top of minor feeder lanes)
 *  - Premium glassmorphism interactive popup with crisp typography and subtle indicators
 *
 * On road segment click:
 *  - Fetches Local SHAP explanation from GET /api/features/roads/{edge_id}/explanation
 *  - Shows ShapExplanationPanel inside the Leaflet Popup
 *  - Risk and Live Conditions remain conceptually separated
 */

import { memo, useMemo, useState, useCallback } from 'react';
import { Polyline, Popup, useMap } from 'react-leaflet';
import { createPortal } from 'react-dom';
import { getHistoricalRiskColor, getHistoricalRiskTier } from '../../utils/riskClassification';
import { getEdgeExplanation } from '../../services/shapApi';
import ShapExplanationPanel from '../Safety/ShapExplanationPanel';
import WhyThisSection from '../Safety/WhyThisSection';

/**
 * Determine visually balanced line weight based on OSM road functional class.
 */
function getRoadWeight(roadClass) {
 const rc = (roadClass || '').toLowerCase();
 if (rc.includes('motorway') || rc.includes('trunk')) return 4.0;
 if (rc.includes('primary')) return 3.5;
 if (rc.includes('secondary')) return 3.0;
 if (rc.includes('tertiary')) return 2.4;
 return 2.0;
}

function HeatmapPolyline({ edge, isDark = false }) {
 const [shapExplanation, setShapExplanation] = useState(null);
 const [shapLoading, setShapLoading] = useState(false);
 const [shapError, setShapError] = useState(null);

 const positions = useMemo(() => {
  const coords = edge.geometry?.coordinates;
  if (!coords || !Array.isArray(coords)) return [];
  return coords.map(([lon, lat]) => [lat, lon]);
 }, [edge.geometry]);

 const color = useMemo(() => {
  return getHistoricalRiskColor(edge.calibrated_risk_prob);
 }, [edge.calibrated_risk_prob]);

 const tier = useMemo(() => {
  return getHistoricalRiskTier(edge.calibrated_risk_prob);
 }, [edge.calibrated_risk_prob]);

 const baseWeight = useMemo(() => {
  return getRoadWeight(edge.road_class);
 }, [edge.road_class]);

 const handleClick = useCallback(async () => {
  if (shapExplanation) return; // Already fetched — show cached result
  if (shapLoading) return;   // Already in flight

  setShapLoading(true);
  setShapError(null);
  try {
   const data = await getEdgeExplanation(edge.edge_id);
   setShapExplanation(data);
  } catch (err) {
   setShapError(err.message || 'Could not load explanation.');
  } finally {
   setShapLoading(false);
  }
 }, [edge.edge_id, shapExplanation, shapLoading]);

 if (!positions || positions.length < 2) return null;

 const lengthM = Math.round(
  edge.length_m != null
   ? edge.length_m
   : (edge.length_km != null ? edge.length_km * 1000 : 0)
 );

 const roadClassClean = (edge.road_class || 'Unknown').replace(/_/g, ' ');

 return (
  <>
   {/* ── Crisp Contrast Edge Casing ── */}
   <Polyline
    positions={positions}
    pathOptions={{
     color: isDark ? '#0f172a' : '#ffffff',
     weight: baseWeight + 1.2,
     opacity: isDark ? 0.75 : 0.7,
     lineCap: 'round',
     lineJoin: 'round',
     interactive: false,
    }}
   />

   {/* ── Core Precision Line ── */}
   <Polyline
    positions={positions}
    pathOptions={{
     color,
     weight: baseWeight,
     opacity: 0.86,
     lineCap: 'round',
     lineJoin: 'round',
    }}
    eventHandlers={{
     mouseover: (e) => {
      const layer = e.target;
      layer.setStyle({ weight: baseWeight + 1.5, opacity: 1.0 });
      layer.bringToFront();
     },
     mouseout: (e) => {
      const layer = e.target;
      layer.setStyle({ weight: baseWeight, opacity: 0.86 });
     },
     click: handleClick,
    }}
   >
    <Popup className="historical-risk-popup" minWidth={280}>
     <div style={{ minWidth: 280, maxWidth: 320 }}>
      <WhyThisSection edge={edge} />
     </div>
    </Popup>
   </Polyline>
  </>
 );
}

const MemoizedHeatmapPolyline = memo(HeatmapPolyline);

export default function HistoricalRiskHeatmap({
 heatmapEdges = [],
 visible = true,
 isDark = false,
}) {
 const sortedEdges = useMemo(() => {
  if (!heatmapEdges || heatmapEdges.length === 0) return [];
  return [...heatmapEdges].sort(
   (a, b) => (a.calibrated_risk_prob || 0) - (b.calibrated_risk_prob || 0)
  );
 }, [heatmapEdges]);

 if (!visible || !heatmapEdges || heatmapEdges.length === 0) {
  return null;
 }

 return (
  <>
   {sortedEdges.map((edge) => (
    <MemoizedHeatmapPolyline
     key={`heatmap-edge-${edge.edge_id}`}
     edge={edge}
     isDark={isDark}
    />
   ))}
  </>
 );
}

