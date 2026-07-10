import dayjs from 'dayjs';

// Currency formatter shared by every page that shows lead revenue/payments.
export const fmt = v => `₹${Number(v || 0).toLocaleString('en-IN')}`;

// Safe JSON parse — emi_details / registration_payments / documents /
// lms_modules may arrive as a string from Supabase JSONB depending on the
// write path, so callers should never assume Array.isArray() alone is safe.
export const safeParse = (val, fallback = []) => {
  if (!val) return fallback;
  if (Array.isArray(val)) return val;
  try { return JSON.parse(val); } catch { return fallback; }
};

// Single source of truth for every payment number derived from a lead —
// PaymentsPage, FinanceDashboard, and anywhere else that shows revenue all
// call this so "Collected" / "Balance Due" / "Overdue" can never drift
// apart from mismatched calculations copy-pasted in different places.
export const financeFor = (lead) => {
  const total  = Number(lead.actual_revenue)    || 0;
  const reg    = Number(lead.registration_fees) || 0;
  const emis   = safeParse(lead.emi_details, []);
  const today  = dayjs().startOf('day');

  const emiPaid = emis
    .filter(e => e.status === 'paid')
    .reduce((s, e) => s + (Number(e.amount) || 0), 0);

  // An EMI counts as overdue if it's still unpaid and its due date has
  // passed — regardless of whether it was ever manually marked "overdue",
  // so this stays accurate even if nobody updates the status field.
  const overdueEmis = emis.filter(e =>
    e.status !== 'paid' && e.date && dayjs(e.date).isBefore(today)
  );
  const overdueAmount = overdueEmis.reduce((s, e) => s + (Number(e.amount) || 0), 0);

  const collected = reg + emiPaid;
  const balance    = Math.max(0, total - collected);
  const pct = total > 0 ? Math.round((collected / total) * 100) : 0;

  let paymentStatus;
  if (total > 0 && balance <= 0)      paymentStatus = 'paid';
  else if (overdueAmount > 0)         paymentStatus = 'overdue';
  else if (collected > 0)             paymentStatus = 'partial';
  else                                paymentStatus = 'not_started';

  return { total, reg, emis, emiPaid, overdueEmis, overdueAmount, collected, balance, pct, paymentStatus };
};

export const PAYMENT_STATUS_CONFIG = {
  paid:        { label: 'Fully Paid',  color: 'success' },
  overdue:     { label: 'Overdue',     color: 'error'   },
  partial:     { label: 'Partial',     color: 'processing' },
  not_started: { label: 'Not Started', color: 'default' },
};
