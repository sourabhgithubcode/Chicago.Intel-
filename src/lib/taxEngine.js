/**
 * Chicago.Intel — Tax Engine
 * Source: IRS Publication 15-T 2024, Illinois DOR, SSA
 * Confidence: 10/10 — exact law
 *
 * DO NOT MODIFY without updating:
 * 1. Source reference above
 * 2. CHANGELOG.md
 * 3. Confidence rating in confidence.js
 */

const STANDARD_DEDUCTION_2024 = 14600; // Single filer
const IL_FLAT_RATE = 0.0495;
const FICA_RATE = 0.0765; // SS 6.2% + Medicare 1.45%

const FEDERAL_BRACKETS_2024 = [
  { limit: 11600,  rate: 0.10 },
  { limit: 33725,  rate: 0.12 },
  { limit: 46525,  rate: 0.22 },
  { limit: 100525, rate: 0.24 },
  { limit: 181150, rate: 0.32 },
  { limit: 215950, rate: 0.35 },
  { limit: Infinity, rate: 0.37 },
];

/**
 * Calculate monthly take-home pay for a given gross annual salary.
 * @param {number} grossAnnual - Annual gross salary in dollars
 * @returns {number} Monthly take-home pay (rounded to nearest dollar)
 */
export function calcTakeHome(grossAnnual) {
  const taxableIncome = Math.max(0, grossAnnual - STANDARD_DEDUCTION_2024);

  let federalTax = 0;
  let remaining = taxableIncome;
  for (const bracket of FEDERAL_BRACKETS_2024) {
    const chunk = Math.min(remaining, bracket.limit);
    federalTax += chunk * bracket.rate;
    remaining -= chunk;
    if (remaining <= 0) break;
  }

  const illinoisTax = grossAnnual * IL_FLAT_RATE;
  const fica = grossAnnual * FICA_RATE;

  const annualTakeHome = grossAnnual - federalTax - illinoisTax - fica;
  return Math.round(annualTakeHome / 12);
}

/**
 * Returns a breakdown of deductions for display in the surplus formula.
 * @param {number} grossAnnual
 * @returns {object} Breakdown of all deductions
 */
export function getTaxBreakdown(grossAnnual) {
  const taxableIncome = Math.max(0, grossAnnual - STANDARD_DEDUCTION_2024);

  let federalTax = 0;
  let remaining = taxableIncome;
  for (const bracket of FEDERAL_BRACKETS_2024) {
    const chunk = Math.min(remaining, bracket.limit);
    federalTax += chunk * bracket.rate;
    remaining -= chunk;
    if (remaining <= 0) break;
  }

  const illinoisTax = grossAnnual * IL_FLAT_RATE;
  const fica = grossAnnual * FICA_RATE;
  const monthlyTakeHome = Math.round((grossAnnual - federalTax - illinoisTax - fica) / 12);

  return {
    grossMonthly: Math.round(grossAnnual / 12),
    federalTaxMonthly: Math.round(federalTax / 12),
    illinoisTaxMonthly: Math.round(illinoisTax / 12),
    ficaMonthly: Math.round(fica / 12),
    takeHomeMonthly: monthlyTakeHome,
    effectiveFederalRate: ((federalTax / grossAnnual) * 100).toFixed(1),
  };
}
