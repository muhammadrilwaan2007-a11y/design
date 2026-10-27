import { Shield, Navigation } from 'lucide-react';

export default function HomeFooter() {
 return (
  <footer className="w-full bg-white border-t border-slate-200/80 py-8">
   <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-center sm:text-left">
    {/* Brand */}
    <div className="flex items-center gap-2.5">
     <div className="relative flex items-center justify-center w-7 h-7 rounded-lg bg-indigo-600 text-white shadow-xs">
      <Shield className="w-4 h-4" />
      <Navigation className="w-2 h-2 absolute text-teal-300 rotate-45" />
     </div>
     <span className="text-sm font-bold text-slate-900">
      RouteGuard AI
     </span>
    </div>

    {/* Tagline */}
    <p className="text-xs sm:text-sm text-slate-500 font-normal">
     Intelligent navigation for safer journeys.
    </p>
   </div>
  </footer>
 );
}
