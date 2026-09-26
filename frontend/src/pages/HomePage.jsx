import { useEffect } from 'react';
import HomeNavbar from '../components/Home/HomeNavbar';
import Hero from '../components/Home/Hero';
import FeatureStrip from '../components/Home/FeatureStrip';
import ProductStatement from '../components/Home/ProductStatement';
import FinalCTA from '../components/Home/FinalCTA';
import HomeFooter from '../components/Home/HomeFooter';

export default function HomePage() {
 // Ensure HomePage is always in clean light theme
 useEffect(() => {
  document.documentElement.classList.remove('dark');
  document.title = 'SafeRoute AI — Intelligent Route Safety Navigation';
 }, []);

 return (
  <div className="min-h-screen flex flex-col bg-white text-slate-900 selection:bg-blue-100 selection:text-blue-900">
   <HomeNavbar />
   <main className="flex-grow">
    <Hero />
    <FeatureStrip />
    <ProductStatement />
    <FinalCTA />
   </main>
   <HomeFooter />
  </div>
 );
}
