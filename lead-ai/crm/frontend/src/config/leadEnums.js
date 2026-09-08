/**
 * Single frontend copy of the lead enums. The authority is the backend
 * (`backend/constants.py`). Keep the values below in sync with it — a new
 * status/source is added THERE first, then mirrored here.
 *
 * Previously these lists were duplicated inside LeadsPageEnhanced.js and
 * LeadDetails.js and drifted (e.g. "PG-NEET" was in one dropdown but not
 * the other, and the source normaliser silently rewrote it to "Website").
 */

export const STATUS_OPTIONS = [
  'Fresh', 'Follow Up', 'Warm', 'Hot', 'Not Interested', 'Not Answering',
  'Enrolled', 'Junk', 'Will Enroll Later', 'Dropped', 'TMT No Response',
  'Re-assigned Lead', 'Test Lead', 'PG-NEET',
];

export const SOURCE_OPTIONS = ['Website', 'Instagram', 'Facebook', 'Referral', 'WhatsApp', 'PG-NEET'];

export const SEGMENT_OPTIONS = ['Hot', 'Warm', 'Cold', 'Junk'];

// Statuses with no active follow-up cycle — never "overdue" / "due today".
// Mirrors backend/constants.py TERMINAL_STATUSES.
export const TERMINAL_STATUSES = new Set([
  'Enrolled', 'Junk', 'Not Interested', 'Dropped', 'TMT No Response', 'Test Lead',
]);
export const isTerminalStatus = (s) => TERMINAL_STATUSES.has(s);

export const STATUS_COLOR_MAP = {
  Enrolled: 'green', Hot: 'red', Warm: 'orange',
  Fresh: 'blue', 'Follow Up': 'purple',
  'Not Interested': 'default', 'Not Answering': 'gray', Junk: 'volcano',
  'Will Enroll Later': 'cyan', Dropped: 'magenta',
  'TMT No Response': 'gold', 'Re-assigned Lead': 'geekblue', 'Test Lead': 'default',
  'PG-NEET': 'lime',
};

// lowercase raw value -> canonical source (import normalisation only).
const SOURCE_ALIAS_MAP = {
  website: 'Website', web: 'Website', site: 'Website', online: 'Website',
  google: 'Website', 'google ads': 'Website', 'google ad': 'Website', seo: 'Website',
  organic: 'Website', search: 'Website',
  instagram: 'Instagram', ig: 'Instagram', insta: 'Instagram',
  facebook: 'Facebook', fb: 'Facebook', 'fb ads': 'Facebook', 'facebook ads': 'Facebook',
  meta: 'Facebook', 'meta ads': 'Facebook',
  referral: 'Referral', refer: 'Referral', reference: 'Referral', ref: 'Referral',
  'word of mouth': 'Referral', wom: 'Referral', agent: 'Referral',
  friend: 'Referral', recommendation: 'Referral',
  whatsapp: 'WhatsApp', 'whats app': 'WhatsApp', wa: 'WhatsApp', wp: 'WhatsApp', wapp: 'WhatsApp',
};

/**
 * Normalise a raw source string from an import file to a canonical value.
 * Returns null when nothing matches (the caller picks a fallback). An exact
 * canonical value passes through; unknowns are NOT force-mapped to Website.
 */
export const normalizeSource = (raw) => {
  if (!raw) return null;
  const lower = String(raw).toLowerCase().trim();
  if (SOURCE_ALIAS_MAP[lower]) return SOURCE_ALIAS_MAP[lower];
  const direct = SOURCE_OPTIONS.find((s) => s.toLowerCase() === lower);
  if (direct) return direct;
  return null;
};
