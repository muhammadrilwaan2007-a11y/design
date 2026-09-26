import { motion } from 'framer-motion';
import { ShieldAlert, Car, AlertTriangle, CloudRain } from 'lucide-react';

const features = [
 {
  icon: ShieldAlert,
  label: 'Accident Risk',
  color: 'text-blue-600',
  bgColor: 'bg-blue-50',
  borderColor: 'border-blue-100',
 },
 {
  icon: Car,
  label: 'Live Traffic',
  color: 'text-teal-600',
  bgColor: 'bg-teal-50',
  borderColor: 'border-teal-100',
 },
 {
  icon: AlertTriangle,
  label: 'Live Incidents',
  color: 'text-amber-600',
  bgColor: 'bg-amber-50',
  borderColor: 'border-amber-100',
 },
 {
  icon: CloudRain,
  label: 'Weather Conditions',
  color: 'text-sky-600',
  bgColor: 'bg-sky-50',
  borderColor: 'border-sky-100',
 },
];

export default function FeatureStrip() {
 return (
  <section className="py-8 bg-slate-50/60 border-y border-slate-200/80">
   <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
     {features.map((feature, idx) => {
      const Icon = feature.icon;
      return (
       <motion.div
        key={feature.label}
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.4, delay: idx * 0.08 }}
        whileHover={{ y: -2 }}
        className="flex items-center gap-3 p-3 sm:p-3.5 bg-white rounded-xl border border-slate-200/80 shadow-2xs hover:border-slate-300 hover:shadow-xs transition-all duration-200 cursor-default"
       >
        <div
         className={`w-9 h-9 rounded-lg ${feature.bgColor} ${feature.borderColor} border flex items-center justify-center shrink-0 ${feature.color}`}
        >
         <Icon className="w-4.5 h-4.5" />
        </div>
        <div className="min-w-0">
         <span className="text-xs sm:text-sm font-semibold text-slate-800 tracking-tight block truncate">
          {feature.label}
         </span>
        </div>
       </motion.div>
      );
     })}
    </div>
   </div>
  </section>
 );
}
