import { Routes, Route, Navigate } from 'react-router-dom';
import HomePage from './pages/HomePage';
import MapPage from './pages/MapPage';

/**
 * App — root router.
 * - "/" renders the modern SafeRoute AI Landing Page.
 * - "/map" renders the interactive Map application.
 */
export default function App() {
 return (
  <Routes>
   <Route path="/" element={<HomePage />} />
   <Route path="/map" element={<MapPage />} />
   <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
 );
}
