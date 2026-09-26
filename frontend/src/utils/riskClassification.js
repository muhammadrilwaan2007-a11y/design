/**
 * frontend/src/utils/riskClassification.js
 * ========================================
 * Statistically justified 4-tier quantile classification for SafeRoute AI
 * Risk Heatmap.
 *
 * Derived from empirical distribution of risk
 * probabilities across Bengaluru's OpenStreetMap road network (N=59,124 held-out edges):
 *
 * 1. Lower Risk (Green):
 *  - Risk: p_cal <= 0.0100 (<= 1.00%)
 *  - Safety Score:  >= 90
 *  - Network scope:  Covers bottom ~83% of network (residential, living_street, quiet tertiary)
 *  - Color:      #22c55e (Emerald Green)
 *
 * 2. Moderate Risk (Yellow):
 *  - Risk: 0.0100 < p_cal <= 0.0450 (1.00% - 4.50%)
 *  - Safety Score:  79 - 89
 *  - Network scope:  Covers 83rd - 93rd percentile (tertiary collectors, unclassified, quiet links)
 *  - Color:      #eab308 (Amber Yellow)
 *
 * 3. Higher Risk (Orange):
 *  - Risk: 0.0450 < p_cal <= 0.1225 (4.50% - 12.25%)
 *  - Safety Score:  65 - 78
 *  - Network scope:  Covers 93rd - 97.5th percentile (secondary avenues, primary connector links)
 *  - Color:      #f97316 (Vibrant Orange)
 *
 * 4. Highest Risk (Red):
 *  - Risk: p_cal > 0.1225 (> 12.25%)
 *  - Safety Score:  < 65
 *  - Network scope:  Covers top ~2.5% of network (primary arterials, trunk expressways, motorways)
 *  - Color:      #ef4444 (Vivid Red)
 *
 * IMPORTANT:
 * Safety Score strictly follows: score = 100 - 100 * sqrt(calibrated_risk_prob).
 * Raw uncalibrated probabilities are NOT used for risk classification or styling.
 */

export const HISTORICAL_RISK_TIERS = {
 LOWER: {
  id: 'lower',
  name: 'Lower',
  label: 'Lower Risk',
  maxProb: 0.0100,
  minScore: 90,
  color: '#10B981', // Clean Emerald Green
  badgeClass: 'bg-emerald-500/90 text-white',
 },
 MODERATE: {
  id: 'moderate',
  name: 'Moderate',
  label: 'Moderate Risk',
  maxProb: 0.0450,
  minScore: 79,
  color: '#F59E0B', // Warm Amber Gold
  badgeClass: 'bg-amber-500/90 text-white',
 },
 HIGHER: {
  id: 'higher',
  name: 'Higher',
  label: 'Higher Risk',
  maxProb: 0.1225,
  minScore: 65,
  color: '#F97316', // Vibrant Coral-Orange
  badgeClass: 'bg-orange-500/90 text-white',
 },
 HIGHEST: {
  id: 'highest',
  name: 'Highest',
  label: 'Highest Risk',
  color: '#EF4444', // Sleek Crimson Red
  badgeClass: 'bg-rose-500/90 text-white',
 },
};

/**
 * Return the color hex for a given risk probability.
 *
 * @param {number|null|undefined} calibratedProb
 * @returns {string} Hex color
 */
export function getHistoricalRiskColor(calibratedProb) {
 if (calibratedProb == null || isNaN(calibratedProb)) return '#94a3b8'; // slate-400 fallback
 if (calibratedProb <= HISTORICAL_RISK_TIERS.LOWER.maxProb) return HISTORICAL_RISK_TIERS.LOWER.color;
 if (calibratedProb <= HISTORICAL_RISK_TIERS.MODERATE.maxProb) return HISTORICAL_RISK_TIERS.MODERATE.color;
 if (calibratedProb <= HISTORICAL_RISK_TIERS.HIGHER.maxProb) return HISTORICAL_RISK_TIERS.HIGHER.color;
 return HISTORICAL_RISK_TIERS.HIGHEST.color;
}

/**
 * Return tier label for a given risk probability.
 *
 * @param {number|null|undefined} calibratedProb
 * @returns {string}
 */
export function getHistoricalRiskTierLabel(calibratedProb) {
 if (calibratedProb == null || isNaN(calibratedProb)) return 'Unknown';
 if (calibratedProb <= HISTORICAL_RISK_TIERS.LOWER.maxProb) return HISTORICAL_RISK_TIERS.LOWER.label;
 if (calibratedProb <= HISTORICAL_RISK_TIERS.MODERATE.maxProb) return HISTORICAL_RISK_TIERS.MODERATE.label;
 if (calibratedProb <= HISTORICAL_RISK_TIERS.HIGHER.maxProb) return HISTORICAL_RISK_TIERS.HIGHER.label;
 return HISTORICAL_RISK_TIERS.HIGHEST.label;
}

/**
 * Return tier descriptor object for a given risk probability.
 *
 * @param {number|null|undefined} calibratedProb
 * @returns {typeof HISTORICAL_RISK_TIERS.LOWER}
 */
export function getHistoricalRiskTier(calibratedProb) {
 if (calibratedProb == null || isNaN(calibratedProb)) return HISTORICAL_RISK_TIERS.LOWER;
 if (calibratedProb <= HISTORICAL_RISK_TIERS.LOWER.maxProb) return HISTORICAL_RISK_TIERS.LOWER;
 if (calibratedProb <= HISTORICAL_RISK_TIERS.MODERATE.maxProb) return HISTORICAL_RISK_TIERS.MODERATE;
 if (calibratedProb <= HISTORICAL_RISK_TIERS.HIGHER.maxProb) return HISTORICAL_RISK_TIERS.HIGHER;
 return HISTORICAL_RISK_TIERS.HIGHEST;
}
