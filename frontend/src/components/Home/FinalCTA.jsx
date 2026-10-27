import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';

export default function FinalCTA() {
 const navigate = useNavigate();

 return (
  <section className="py-16 sm:py-20 bg-slate-50/70 border-t border-slate-200/80 text-center">
   <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
    <motion.div
     initial={{ opacity: 0, scale: 0.98 }}
     whileInView={{ opacity: 1, scale: 1 }}
     viewport={{ once: true }}
     transition={{ duration: 0.5 }}
     className="flex flex-col items-center justify-center"
    >
     <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mb-6">
      Ready to travel safer?
     </h2>

     <motion.button
      type="button"
      onClick={() => navigate('/map')}
      whileHover={{ scale: 1.03, y: -1 }}
      whileTap={{ scale: 0.98 }}
      className="inline-flex items-center gap-2.5 px-8 py-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white font-semibold text-base sm:text-lg shadow-lg shadow-indigo-500/20 transition-all duration-150 cursor-pointer focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-600/30"
     >
      <span>Open Safe Navigation</span>
      <ArrowRight className="w-5 h-5" />
     </motion.button>
    </motion.div>
   </div>
  </section>
 );
}
