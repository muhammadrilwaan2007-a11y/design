import { Link, useNavigate } from 'react-router-dom';
import { Shield, Navigation } from 'lucide-react';

export default function HomeNavbar() {
 const navigate = useNavigate();

 return (
  <header className="w-full bg-white/95 backdrop-blur-md sticky top-0 z-50 border-b border-slate-200/80">
   <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
    {/* Brand Logo */}
    <Link
     to="/"
     className="flex items-center gap-2.5 group focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600 rounded-lg p-1"
     aria-label="RouteGuard AI Home"
    >
     <div className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-indigo-600 text-white shadow-sm shadow-indigo-400/30 group-hover:scale-105 transition-transform duration-200">
      <Shield className="w-5 h-5" />
      <Navigation className="w-2.5 h-2.5 absolute text-teal-300 rotate-45" />
     </div>
     <div className="flex items-center gap-1.5">
      <span className="text-lg font-bold tracking-tight text-slate-900">
       RouteGuard
      </span>
      <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200/60">
       AI
      </span>
     </div>
    </Link>

    {/* Right Navigation */}
    <nav className="flex items-center gap-2 sm:gap-4" aria-label="Main Navigation">
     <Link
      to="/"
      className="text-sm font-medium text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600"
     >
      Home
     </Link>

     <button
      type="button"
      onClick={() => navigate('/map')}
      className="inline-flex items-center gap-1.5 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 px-4 py-2 rounded-lg shadow-sm hover:shadow transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600 focus-visible:ring-offset-2 cursor-pointer"
     >
      <Navigation className="w-3.5 h-3.5 rotate-45" />
      <span>Navigate</span>
     </button>
    </nav>
   </div>
  </header>
 );
}
