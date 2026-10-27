/**
 * MapPage.jsx
 * Top-level page — integrates Module 1 (location search) and Module 2 (routing).
 *
 * State owned here:
 *  source, destination, selectedLocationType — Module 1
 *  routes, selectedRoute, loading, error   — Module 2 (via useRoute)
 *  isDark, panelOpen             — UI
 *
 * Module 3 will consume:
 *  routes[].geometry.coordinates — full GeoJSON route geometries
 *  routes[].steps         — per-step road segments
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Moon, Sun, Route as RouteIcon, RefreshCw, Sparkles } from 'lucide-react';
import { useLocation }  from '../hooks/useLocation';
import { useRoute }    from '../hooks/useRoute';
import useTraffic     from '../hooks/useTraffic';
import useIncidents    from '../hooks/useIncidents';
import useWeather     from '../hooks/useWeather';
import useFeatures    from '../hooks/useFeatures';
import MapView      from '../components/Map/MapView';
import SearchBar     from '../components/Search/SearchBar';
import RouteAlternatives from '../components/Routes/RouteAlternatives';
import RouteDetails    from '../components/Routes/RouteDetails';
import WeatherIndicator  from '../components/Safety/WeatherIndicator';
import LayerControls   from '../components/Map/LayerControls';
import AiAssistantDrawer from '../components/Safety/AiAssistantDrawer';
import { getHistoricalRiskHeatmap } from '../services/featuresApi';
import { getRouteRecommendation }  from '../utils/routeRecommendation';
import { loadMapSession, saveMapSession } from '../utils/sessionStorage';

export const BENGALURU_PRESETS = [
 {
  name: 'Koramangala ➔ Whitefield',
  source: { name: 'Koramangala, Bengaluru', latitude: 12.9352, longitude: 77.6245 },
  destination: { name: 'Whitefield, Bengaluru', latitude: 12.9698, longitude: 77.7499 },
 },
 {
  name: 'Indiranagar ➔ Electronic City',
  source: { name: 'Indiranagar, Bengaluru', latitude: 12.9784, longitude: 77.6408 },
  destination: { name: 'Electronic City, Bengaluru', latitude: 12.8383, longitude: 77.6768 },
 },
 {
  name: 'Majestic ➔ Hebbal',
  source: { name: 'Majestic, Bengaluru', latitude: 12.9767, longitude: 77.5713 },
  destination: { name: 'Hebbal, Bengaluru', latitude: 13.0358, longitude: 77.5970 },
 },
];

export default function MapPage() {
 const initialSession = useMemo(() => loadMapSession(), []);

 // ── Location (Module 1) ───────────────────────────────────────────────────
 const [source,        setSource]        = useState(() => initialSession?.source ?? null);
 const [destination,     setDestination]     = useState(() => initialSession?.destination ?? null);
 const [selectedLocationType, setSelectedLocationType] = useState(() => initialSession?.selectedLocationType ?? 'destination');
 const [mapViewState, setMapViewState] = useState(() => initialSession?.mapView ?? null);

 const handleMapMove = useCallback((view) => {
  setMapViewState(view);
 }, []);

 const {
  location: gpsLocation,
  loading: locationLoading,
  error:  locationError,
  getLocation,
 } = useLocation();

 useEffect(() => {
  if (gpsLocation && !source && !initialSession?.source) setSource(gpsLocation);
 // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [gpsLocation]);

 // ── Routing (Module 2) ────────────────────────────────────────────────────
 const {
  routes,
  selectedRoute,
  loading: routeLoading,
  error:  routeError,
  noRoute,
  fetchRoutes,
  selectRoute,
  clearRoutes,
 } = useRoute(
  initialSession?.routes ?? [],
  initialSession?.selectedRoute ?? null
 );

 // ── Traffic (Module 3) ────────────────────────────────────────────────────
 const {
  trafficData,
  loading: trafficLoading,
  error: _trafficError,
  analyzeTrafficForRoutes,
 } = useTraffic();

 // ── Incidents (Module 4) ────────────────────────────────────────────────────
 const {
  incidentData,
  loading: incidentLoading,
  error: incidentError,
  analyzeIncidentsForRoutes,
  refreshIncidents,
 } = useIncidents();

 // ── Weather (Module 5) ────────────────────────────────────────────────────
 const {
  weather,
  loading: weatherLoading,
  error: weatherError,
  fetchWeather,
  refreshWeather,
 } = useWeather();

 // ── Features + Safety Score (Module 7 + 8) ────────────────────────────────
 const {
  featuresData,
  featuresLoading,
  featuresError,
  analyzeFeatures,
  retryFeatures,
  clearFeatures,
 } = useFeatures();

 /** Compute the midpoint coordinate of a route geometry for weather lookup. */
 const getRouteMidpoint = useCallback((route) => {
  const coords = route?.geometry?.coordinates;
  if (!coords || coords.length === 0) return null;
  const mid = coords[Math.floor(coords.length / 2)];
  return { latitude: mid[1], longitude: mid[0] }; // GeoJSON is [lon, lat]
 }, []);

 // ── Simulated Road Closures (for demonstration & testing) ─────────────────
 const [simulatedClosures, setSimulatedClosures] = useState(() => new Set());

 const handleToggleSimulatedClosure = useCallback((routeId) => {
  setSimulatedClosures((prev) => {
   const next = new Set(prev);
   if (next.has(routeId)) {
    next.delete(routeId);
   } else {
    next.add(routeId);
   }
   return next;
  });
 }, []);

 // ── Intelligent Recommendation Engine (Safety Score + Road Closures) ─────
 const recommendation = useMemo(() => {
  return getRouteRecommendation({
   routes,
   featuresData,
   incidentData,
   trafficData,
   simulatedClosures,
  });
 }, [routes, featuresData, incidentData, trafficData, simulatedClosures]);

 const {
  theoreticallySafestRoute,
  recommendedRoute,
  recommendedScore,
  isAlternativeRecommendation,
  closureMap,
 } = recommendation;

 // Track if the user has explicitly selected a route manually
 const [userSelectedManually, setUserSelectedManually] = useState(false);

 // Reset manual selection when routes change or new search starts
 useEffect(() => {
  setUserSelectedManually(false);
  setSimulatedClosures(new Set());
 }, [source, destination, routes]);

 // When recommendation updates, auto-recommend and auto-select the recommended drivable route!
 useEffect(() => {
  if (userSelectedManually || !recommendedRoute) return;
  if (recommendedRoute.id !== selectedRoute?.id) {
   console.info(
    `[RouteGuard AI] Auto-recommending route: ${recommendedRoute.id} ` +
    `(Score: ${recommendedScore ?? '—'}/100, isAlternative: ${isAlternativeRecommendation})`
   );
   selectRoute(recommendedRoute);
  }
 }, [recommendedRoute, recommendedScore, isAlternativeRecommendation, userSelectedManually, selectRoute, selectedRoute?.id]);

 const handleSelectRoute = useCallback((route) => {
  setUserSelectedManually(true);
  selectRoute(route);
 }, [selectRoute]);

 // Track which index corresponds to selectedRoute (for colour continuity)
 const selectedRouteIndex = routes.findIndex((r) => r.id === selectedRoute?.id);

 const handleFindRoutes = useCallback(() => {
  if (source && destination) fetchRoutes(source, destination);
 }, [source, destination, fetchRoutes]);

 const handleSelectBengaluruPreset = useCallback((preset = BENGALURU_PRESETS[0]) => {
  setSource(preset.source);
  setDestination(preset.destination);
  fetchRoutes(preset.source, preset.destination);
 }, [fetchRoutes]);

 const isFirstMount = useRef(true);
 const prevSourceRef = useRef(source);
 const prevDestRef = useRef(destination);

 // Clear routes when source or destination changes (skipping initial mount session restore)
 useEffect(() => {
  if (isFirstMount.current) {
   isFirstMount.current = false;
   prevSourceRef.current = source;
   prevDestRef.current = destination;
   return;
  }
  const sChanged = JSON.stringify(prevSourceRef.current) !== JSON.stringify(source);
  const dChanged = JSON.stringify(prevDestRef.current) !== JSON.stringify(destination);
  if (sChanged || dChanged) {
   clearRoutes();
   clearFeatures();
   prevSourceRef.current = source;
   prevDestRef.current = destination;
  }
 // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [source, destination, clearRoutes, clearFeatures]);

 // Module 2 handoff — available on window for debugging / Module 3
 useEffect(() => {
  if (source && destination) {
   window.__saferoute_input = {
    source:   { name: source.name, latitude: source.latitude, longitude: source.longitude },
    destination: { name: destination.name, latitude: destination.latitude, longitude: destination.longitude },
   };
  }
  if (routes.length > 0) {
   window.__saferoute_routes = routes;
   console.info('[RouteGuard AI] Routes ready for Modules 3, 4, 5 & 8:', routes);
   analyzeTrafficForRoutes(routes);
   analyzeIncidentsForRoutes(routes);
   analyzeFeatures(routes);  // Module 7 + 8: features & safety scores
   // Use first route midpoint for weather (one API call total)
   const midpoint = getRouteMidpoint(routes[0]);
   if (midpoint) fetchWeather(midpoint.latitude, midpoint.longitude);
  }
 }, [source, destination, routes, analyzeTrafficForRoutes, analyzeIncidentsForRoutes, analyzeFeatures, fetchWeather, getRouteMidpoint]);

 // ── UI state ──────────────────────────────────────────────────────────────
 const [isDark, setIsDark] = useState(() => {
  const saved = localStorage.getItem('saferoute-theme');
  if (saved) return saved === 'dark';
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
 });

 useEffect(() => {
  document.documentElement.classList.toggle('dark', isDark);
  localStorage.setItem('saferoute-theme', isDark ? 'dark' : 'light');
 }, [isDark]);

 const toggleTheme = useCallback(() => setIsDark((d) => !d), []);

 const [panelOpen, setPanelOpen] = useState(() => initialSession?.panelOpen ?? true);
 const [aiDrawerOpen, setAiDrawerOpen] = useState(false);

 // ── Layer Visibility Controls (independent layers) ─────────────────────────
 const [layerVisibility, setLayerVisibility] = useState(
  () => initialSession?.layerVisibility ?? {
   historicalRisk: true,
   traffic: true,
   incidents: true,
   weather: true,
  }
 );

 const handleToggleLayer = useCallback((layerKey) => {
  setLayerVisibility((prev) => ({
   ...prev,
   [layerKey]: !prev[layerKey],
  }));
 }, []);

 // ── Auto-save session across refreshes ──────────────────────────────────
 useEffect(() => {
  saveMapSession({
   source,
   destination,
   selectedLocationType,
   routes,
   selectedRoute,
   layerVisibility,
   panelOpen,
   mapView: mapViewState,
  });
 }, [source, destination, selectedLocationType, routes, selectedRoute, layerVisibility, panelOpen, mapViewState]);

 // ── Heatmap Edge Resolution ───────────────────────────────────────────────
 // ── Heatmap Edge Resolution (City Corridors + Active Route Edges) ─────────
 const [standaloneHeatmapEdges, setStandaloneHeatmapEdges] = useState([]);

 useEffect(() => {
  let isMounted = true;
  if (layerVisibility.historicalRisk && standaloneHeatmapEdges.length === 0) {
   getHistoricalRiskHeatmap({ limit: 1200 })
    .then((edges) => {
     if (isMounted) setStandaloneHeatmapEdges(edges);
    })
    .catch((err) => console.warn('Could not fetch standalone heatmap:', err));
  }
  return () => {
   isMounted = false;
  };
 }, [layerVisibility.historicalRisk, standaloneHeatmapEdges.length]);

 const activeRouteHeatmapEdges = useMemo(() => {
  if (!routes || routes.length === 0) return [];
  if (selectedRoute && featuresData[selectedRoute.id]?.heatmap_edges?.length > 0) {
   return featuresData[selectedRoute.id].heatmap_edges;
  }
  const edgeMap = new Map();
  for (const r of routes) {
   const edges = featuresData[r.id]?.heatmap_edges || [];
   for (const e of edges) {
    if (!edgeMap.has(e.edge_id)) edgeMap.set(e.edge_id, e);
   }
  }
  return Array.from(edgeMap.values());
 }, [selectedRoute, routes, featuresData]);

 // Combine both city corridors and route-matched edges so city risk remains visible
 const displayedHeatmapEdges = useMemo(() => {
  const edgeMap = new Map();
  for (const e of standaloneHeatmapEdges) {
   if (e && e.edge_id != null) edgeMap.set(e.edge_id, e);
  }
  for (const e of activeRouteHeatmapEdges) {
   if (e && e.edge_id != null) edgeMap.set(e.edge_id, e);
  }
  return Array.from(edgeMap.values());
 }, [standaloneHeatmapEdges, activeRouteHeatmapEdges]);

 // ── Handlers ──────────────────────────────────────────────────────────────
 const handleSourceChange = useCallback((place) => setSource(place),   []);
 const handleDestChange  = useCallback((place) => setDestination(place), []);
 const handleTypeChange  = useCallback((type) => setSelectedLocationType(type), []);

 // ── Dynamic panel top position (based on search panel height) ────────────
 // Search panel + presets ~200px + 16px top padding = 216; tab ~28px; total ~245px
 const PANEL_HEIGHT = 245;

 return (
  <div className="relative w-screen h-screen overflow-hidden bg-slate-100 dark:bg-slate-900">

   {/* ── Full-screen map ─────────────────────────────────────────────── */}
   <div className="absolute inset-0 z-0">
    <MapView
     source={source}
     destination={destination}
     currentLocation={gpsLocation}
     isDark={isDark}
     routes={routes}
     selectedRoute={selectedRoute}
     onSelectRoute={handleSelectRoute}
     trafficData={trafficData}
     incidentData={incidentData}
     heatmapEdges={displayedHeatmapEdges}
     showHistoricalRisk={layerVisibility.historicalRisk}
     showTraffic={layerVisibility.traffic}
     showIncidents={layerVisibility.incidents}
     closureMap={closureMap}
     initialCenter={mapViewState?.center}
     initialZoom={mapViewState?.zoom}
     onMapMove={handleMapMove}
    />
   </div>

   {/* ── Sliding search panel ─────────────────────────────────────────── */}
   <div
    className="absolute top-0 left-1/2 w-full max-w-md px-3 z-[1000]"
    style={{
     transform: `translateX(-50%) translateY(${panelOpen ? '0px' : '-100%'})`,
     transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    }}
   >
    <div className="pt-4">
     <SearchBar
      source={source}
      destination={destination}
      selectedType={selectedLocationType}
      onSourceChange={handleSourceChange}
      onDestinationChange={handleDestChange}
      onTypeChange={handleTypeChange}
      userCoords={gpsLocation}
      locationLoading={locationLoading}
      locationError={locationError}
      onRequestLocation={getLocation}
     />
     {/* ── Bengaluru Demo Route Presets ───────────────────────────── */}
     <div className="mt-2.5 flex items-center justify-center gap-1.5 flex-wrap">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mr-1 flex items-center gap-1">
       <span>📍</span> Bengaluru Demo:
      </span>
      {BENGALURU_PRESETS.map((p) => (
       <button
        key={p.name}
        type="button"
        onClick={() => handleSelectBengaluruPreset(p)}
        className="text-[11px] font-medium px-2.5 py-1 rounded-full bg-white/95 dark:bg-slate-800/95 border border-slate-200 dark:border-slate-700 hover:border-primary-500 text-slate-700 dark:text-slate-200 hover:text-primary-600 dark:hover:text-primary-400 shadow-xs transition-all backdrop-blur-xs cursor-pointer"
       >
        {p.name}
       </button>
      ))}
     </div>
    </div>
   </div>

   {/* ── Toggle tab ──────────────────────────────────────────────────── */}
   <div
    className="absolute left-1/2 z-[1001] flex justify-center"
    style={{
     transform: 'translateX(-50%)',
     top: panelOpen ? `${PANEL_HEIGHT}px` : '8px',
     transition: 'top 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    }}
   >
    <button
     id="panel-toggle-btn"
     type="button"
     onClick={() => setPanelOpen((p) => !p)}
     aria-label={panelOpen ? 'Hide search panel' : 'Show search panel'}
     className="
      flex items-center gap-1.5
      bg-white dark:bg-slate-700
      border border-slate-200 dark:border-slate-600
      text-slate-500 dark:text-slate-300 hover:text-primary-600
      text-xs font-medium px-3 py-1 rounded-full
      shadow-md hover:shadow-lg transition-colors duration-150 select-none
     "
    >
     <svg
      width="14" height="14" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round"
      style={{ transform: panelOpen ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.3s ease' }}
     >
      <polyline points="18 15 12 9 6 15" />
     </svg>
     {panelOpen ? 'Hide' : 'Search'}
    </button>
   </div>

   {/* ── Find Routes button ────────────────────────────────────────────── */}
   {source && destination && (
    <div
     className="absolute left-1/2 z-[1000]"
     style={{
      transform: 'translateX(-50%)',
      top: panelOpen ? `${PANEL_HEIGHT + 36}px` : '44px',
      transition: 'top 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
     }}
    >
     <button
      id="find-routes-btn"
      type="button"
      onClick={handleFindRoutes}
      disabled={routeLoading}
      className="
       flex items-center gap-2
       bg-primary-600 hover:bg-primary-700 active:bg-primary-800
       disabled:bg-primary-400
       text-white text-sm font-semibold
       px-5 py-2 rounded-full
       shadow-lg hover:shadow-xl
       transition-all duration-150
       whitespace-nowrap
      "
     >
      <RouteIcon size={15} />
      {routeLoading ? 'Finding routes…' : 'Find Routes'}
     </button>
    </div>
   )}

   {/* ── Route sidebar (bottom-right floating panel) ───────────────────── */}
   {(source && destination) && (
    <div
     className="
      absolute bottom-6 right-4 z-[1000]
      w-80 max-h-[70vh]
      flex flex-col gap-3
      overflow-hidden
     "
    >
     {/* Route alternatives list */}
     <div className="
      bg-white dark:bg-slate-800
      border border-slate-200 dark:border-slate-700
      rounded-xl shadow-card
      p-3
      overflow-y-auto
      max-h-64
     ">
      <RouteAlternatives
       routes={routes}
       selectedRoute={selectedRoute}
       loading={routeLoading}
       error={routeError}
       noRoute={noRoute}
       onSelectRoute={handleSelectRoute}
       onFindRoutes={handleFindRoutes}
       canFetch={!!(source && destination)}
       trafficData={trafficData}
       incidentData={incidentData}
       featuresData={featuresData}
       featuresLoading={featuresLoading}
       recommendation={recommendation}
       onToggleSimulatedClosure={handleToggleSimulatedClosure}
       simulatedClosures={simulatedClosures}
      />
     </div>

     {/* Selected route details */}
     {selectedRoute && (
      <div className="
       bg-white dark:bg-slate-800
       border border-slate-200 dark:border-slate-700
       rounded-xl shadow-card
       p-3
       overflow-y-auto
       max-h-72
      ">
       {/* Manual refresh button */}
       {routes.length > 0 && (
        <div className="flex justify-end mb-2">
         <button
          type="button"
          onClick={() => {
           refreshIncidents();
           analyzeFeatures(routes, true);
          }}
          disabled={incidentLoading || featuresLoading}
          title="Refresh live incidents & safety scores"
          className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400 hover:text-primary-600 disabled:opacity-50 transition-colors"
         >
          <RefreshCw size={11} className={incidentLoading || featuresLoading ? 'animate-spin' : ''} />
          {featuresError ? 'Retry safety score' : 'Refresh live data'}
         </button>
        </div>
       )}
       <RouteDetails
        route={selectedRoute}
        index={selectedRouteIndex >= 0 ? selectedRouteIndex : 0}
        incidentAnalysis={incidentData[selectedRoute?.id]}
        incidentError={incidentError}
        trafficSummary={trafficData[selectedRoute?.id]?.route_summary}
        featureData={featuresData[selectedRoute?.id] ?? null}
        allRoutes={routes}
        allFeaturesData={featuresData}
        featuresLoading={featuresLoading}
        featuresError={featuresError}
        weather={weather}
        weatherLoading={weatherLoading}
        trafficLoading={trafficLoading}
        incidentLoading={incidentLoading}
        recommendation={recommendation}
        onSelectRecommended={() => handleSelectRoute(recommendedRoute)}
        onSelectSafest={() => handleSelectRoute(theoreticallySafestRoute)}
        onToggleSimulatedClosure={() => handleToggleSimulatedClosure(selectedRoute.id)}
        isSimulatedClosed={simulatedClosures.has(selectedRoute.id)}
        onRetryFeatures={retryFeatures}
        onOpenAiAssistant={() => setAiDrawerOpen(true)}
        onSelectPreset={() => handleSelectBengaluruPreset(BENGALURU_PRESETS[0])}
       />
      </div>
     )}
    </div>
   )}

   {/* ── Floating Map Controls & Legends (bottom-left) ─────────────────── */}
   <div className="absolute bottom-6 left-6 z-[1000] flex flex-col gap-2.5 max-h-[85vh] overflow-y-auto">
    {/* Weather Indicator (independent layer) */}
    {layerVisibility.weather && routes.length > 0 && (
     <WeatherIndicator
      weather={weather}
      loading={weatherLoading}
      error={weatherError}
      onRefresh={refreshWeather}
     />
    )}

    {/* Independent Layer Controls & Risk Legend */}
    <LayerControls
     layers={layerVisibility}
     onToggleLayer={handleToggleLayer}
    />
   </div>

   {/* ── Theme toggle ──────────────────────────────────────────────────── */}
   <button
    id="theme-toggle-btn"
    type="button"
    onClick={toggleTheme}
    aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    className="
     absolute top-4 right-4 z-[1001]
     w-9 h-9 rounded-full
     flex items-center justify-center
     bg-white dark:bg-slate-700
     border border-slate-200 dark:border-slate-600
     text-amber-500 dark:text-slate-200
     shadow-md hover:shadow-lg hover:scale-110 active:scale-95
     transition-all duration-150
    "
   >
    {isDark ? <Sun size={17} /> : <Moon size={17} />}
   </button>

   {/* ── AI Safety Assistant Side Button ───────────────────────────────── */}
   <button
    id="ai-assistant-side-btn"
    type="button"
    onClick={() => setAiDrawerOpen(true)}
    aria-label="Open AI Safety Assistant"
    className="
     absolute top-16 right-4 z-[1001]
     flex items-center gap-1.5
     bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600
     text-white text-xs font-semibold
     px-3 py-2 rounded-full
     shadow-lg hover:shadow-indigo-500/30 hover:scale-105 active:scale-95
     transition-all duration-150 select-none group
    "
   >
    <Sparkles size={14} className="text-indigo-200 animate-pulse group-hover:rotate-12 transition-transform" />
    <span>AI Assistant</span>
   </button>

   {/* ── AI Safety Assistant Interactive Drawer ────────────────────────── */}
   <AiAssistantDrawer
    isOpen={aiDrawerOpen}
    onClose={() => setAiDrawerOpen(false)}
    selectedRoute={selectedRoute}
    featureData={featuresData[selectedRoute?.id] ?? null}
    allRoutes={routes}
    allFeaturesData={featuresData}
   />
  </div>
 );
}
