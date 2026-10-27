import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Navigation, ShieldCheck, Sparkles } from 'lucide-react';

export default function Hero() {
 const navigate = useNavigate();

 // Animation variants
 const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
   opacity: 1,
   transition: {
    staggerChildren: 0.15,
    delayChildren: 0.1,
   },
  },
 };

 const itemVariants = {
  hidden: { opacity: 0, y: 24 },
  visible: {
   opacity: 1,
   y: 0,
   transition: {
    duration: 0.6,
    ease: [0.16, 1, 0.3, 1],
   },
  },
 };

 const visualVariants = {
  hidden: { opacity: 0, scale: 0.95 },
  visible: {
   opacity: 1,
   scale: 1,
   transition: {
    duration: 0.8,
    delay: 0.25,
    ease: [0.16, 1, 0.3, 1],
   },
  },
 };

 return (
  <section className="relative overflow-hidden pt-10 pb-16 md:py-20 lg:py-24 bg-gradient-to-b from-white via-slate-50/50 to-white">
   {/* Subtle background ambient glow */}
   <div className="absolute top-0 right-1/4 w-96 h-96 bg-indigo-100/40 rounded-full blur-3xl -z-10 pointer-events-none" />
   <div className="absolute top-1/3 left-10 w-80 h-80 bg-teal-100/30 rounded-full blur-3xl -z-10 pointer-events-none" />

   <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-8 items-center">
     
     {/* Left Column: Text & CTA */}
     <motion.div
      className="lg:col-span-7 flex flex-col items-start text-left"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
     >
      {/* Trust badge / micro-pill */}
      <motion.div
       variants={itemVariants}
       className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-50/90 border border-indigo-200/80 text-indigo-700 text-xs sm:text-sm font-medium mb-6 shadow-2xs"
      >
       <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
       <span>Intelligent Road Safety Navigation</span>
      </motion.div>

      {/* Main Headline */}
      <motion.h1
       variants={itemVariants}
       className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-slate-900 leading-[1.12] mb-6"
      >
       Every Journey <br />
       Deserves{' '}
       <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-500 via-indigo-600 to-cyan-500">
        Safety
       </span>
      </motion.h1>

      {/* Subtitle */}
      <motion.p
       variants={itemVariants}
       className="text-base sm:text-lg lg:text-xl text-slate-600 leading-relaxed max-w-xl mb-8"
      >
       AI-powered navigation that analyzes road risk, traffic, incidents, weather and accident to help you choose a safer route.
      </motion.p>

      {/* Primary CTA */}
      <motion.div variants={itemVariants} className="w-full sm:w-auto">
       <motion.button
        type="button"
        onClick={() => navigate('/map')}
        whileHover={{ scale: 1.025, y: -1 }}
        whileTap={{ scale: 0.98 }}
        className="w-full sm:w-auto inline-flex items-center justify-center gap-3 px-8 py-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white font-semibold text-base sm:text-lg shadow-lg shadow-indigo-500/25 transition-colors duration-150 cursor-pointer focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-600/30"
       >
        <span>Start Safe Navigation</span>
        <Navigation className="w-5 h-5 rotate-45" />
       </motion.button>
      </motion.div>
     </motion.div>

     {/* Right Column: Visual Hero Element */}
     <motion.div
      className="lg:col-span-5 w-full flex justify-center"
      variants={visualVariants}
      initial="hidden"
      animate="visible"
     >
      <div className="relative w-full max-w-lg aspect-[4/3] sm:aspect-[5/4] bg-white rounded-2xl border border-slate-200/90 shadow-xl shadow-slate-200/50 p-4 sm:p-5 flex flex-col justify-between overflow-hidden">
       
       {/* Subtle map digital grid backdrop */}
       <div className="absolute inset-0 bg-[radial-gradient(#e2e8f0_1px,transparent_1px)] [background-size:20px_20px] opacity-70" />

       {/* Vector digital map representation */}
       <div className="relative w-full h-full flex items-center justify-center">
        <svg
         viewBox="0 0 420 300"
         className="w-full h-full"
         fill="none"
         xmlns="http://www.w3.org/2000/svg"
         aria-hidden="true"
        >
         {/* Base secondary roads (clean gray lines) */}
         <path
          d="M 30 180 C 100 180, 120 220, 200 230 C 280 240, 320 200, 390 210"
          stroke="#E2E8F0"
          strokeWidth="3.5"
          strokeLinecap="round"
         />
         <path
          d="M 60 50 C 90 120, 110 160, 140 250"
          stroke="#E2E8F0"
          strokeWidth="3"
          strokeLinecap="round"
         />
         <path
          d="M 260 40 C 270 110, 290 170, 330 260"
          stroke="#E2E8F0"
          strokeWidth="3"
          strokeLinecap="round"
         />
         
         {/* Standard high-risk alternate route (muted gray dash) */}
         <path
          d="M 50 210 C 110 200, 150 90, 220 80 C 290 70, 330 100, 370 70"
          stroke="#CBD5E1"
          strokeWidth="4"
          strokeDasharray="6 6"
          strokeLinecap="round"
         />

         {/* Highlighted Safe Route (Primary Blue & Teal glow) */}
         <path
          d="M 50 210 C 130 220, 160 170, 210 160 C 270 150, 300 100, 370 70"
          stroke="#93C5FD"
          strokeWidth="10"
          strokeLinecap="round"
          opacity="0.4"
         />
         <path
          d="M 50 210 C 130 220, 160 170, 210 160 C 270 150, 300 100, 370 70"
          stroke="#2563EB"
          strokeWidth="4.5"
          strokeLinecap="round"
         />

         {/* Route Safety Waypoint Dot */}
         <circle cx="210" cy="160" r="5" fill="#14B8A6" />
         <circle cx="210" cy="160" r="10" stroke="#14B8A6" strokeWidth="1.5" opacity="0.4" />

         {/* Origin Location Pin */}
         <g transform="translate(50, 210)">
          <circle r="12" fill="#2563EB" fillOpacity="0.15" />
          <circle r="6" fill="#2563EB" />
          <circle r="2.5" fill="#FFFFFF" />
         </g>

         {/* Destination Location Pin */}
         <g transform="translate(370, 70)">
          <circle r="14" fill="#14B8A6" fillOpacity="0.2" />
          <path
           d="M 0 -14 C -5.5 -14 -10 -9.5 -10 -4 C -10 3 0 14 0 14 C 0 14 10 3 10 -4 C 10 -9.5 5.5 -14 0 -14 Z"
           fill="#14B8A6"
          />
          <circle cy="-4" r="3.5" fill="#FFFFFF" />
         </g>
        </svg>

        {/* Floating Card: "Safer Route Found" / "Risk reduced by 24%" */}
        <motion.div
         initial={{ y: 8, opacity: 0 }}
         animate={{ y: 0, opacity: 1 }}
         transition={{ delay: 0.5, duration: 0.6 }}
         className="absolute top-4 left-4 sm:top-5 sm:left-5 bg-white/95 backdrop-blur-md rounded-xl p-3.5 border border-slate-200/90 shadow-lg shadow-slate-300/40 flex items-center gap-3 z-10"
        >
         <div className="w-9 h-9 rounded-lg bg-teal-50 border border-teal-200/80 flex items-center justify-center text-teal-600 shrink-0">
          <ShieldCheck className="w-5 h-5" />
         </div>
         <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
           <span className="text-xs sm:text-sm font-bold text-slate-900">
            Safer Route Found
           </span>
           <span className="w-1.5 h-1.5 rounded-full bg-teal-500" />
          </div>
          <span className="text-xs font-semibold text-teal-600">
           Risk reduced by 24%
          </span>
         </div>
        </motion.div>

        {/* Minimal Route Duration / Live Safety Tag */}
        <div className="absolute bottom-4 right-4 bg-white/95 backdrop-blur-md rounded-lg px-2.5 py-1.5 border border-slate-200/80 shadow-sm flex items-center gap-1.5 text-[11px] font-medium text-slate-600">
         <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
         <span>Optimized for low risk</span>
        </div>
       </div>

      </div>
     </motion.div>

    </div>
   </div>
  </section>
 );
}
