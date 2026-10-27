import { motion } from 'framer-motion';

export default function ProductStatement() {
 return (
  <section className="py-20 sm:py-24 bg-white text-center">
   <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
    <motion.div
     initial={{ opacity: 0, y: 16 }}
     whileInView={{ opacity: 1, y: 0 }}
     viewport={{ once: true }}
     transition={{ duration: 0.5 }}
     className="flex flex-col items-center"
    >
     <span className="text-xs sm:text-sm font-semibold text-indigo-600 tracking-wider uppercase mb-3">
      Safety-First Navigation
     </span>
     <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mb-5">
      More than the fastest route.
     </h2>
     <p className="text-base sm:text-lg text-slate-600 leading-relaxed max-w-2xl">
      RouteGuard AI combines multiple real-world signals to help you understand the risk of your journey before you start driving.
     </p>
    </motion.div>
   </div>
  </section>
 );
}
