import dayjs from 'dayjs';

// Server timestamps are UTC but often come without a "Z"; without it dayjs would read them as local time.
export const parseUtc = (s) => {
  if (!s) return null;
  const str = String(s);
  return dayjs(/Z$|[+-]\d{2}:\d{2}$/.test(str) ? str : `${str}Z`);
};

// ₹1,25,000 -> ₹1.25L, ₹2,50,00,000 -> ₹2.5Cr (cards and column headers are narrow)
export const inrShort = (n) => {
  const v = Math.round(Number(n) || 0);
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(v % 1e7 ? 2 : 0).replace(/\.?0+$/, '')}Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(v % 1e5 ? 2 : 0).replace(/\.?0+$/, '')}L`;
  return `₹${v.toLocaleString('en-IN')}`;
};

export const initials = (name) => String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?';

// A wa.me link needs the number with its country code. Ten bare digits are assumed Indian only when
// the lead's country is India; otherwise the digits are used exactly as stored.
export const whatsappLink = (phone, country) => {
  let d = String(phone || '').replace(/\D/g, '');
  if (!d) return null;
  if (d.length === 10 && String(country || '').toLowerCase() === 'india') d = `91${d}`;
  return `https://wa.me/${d}`;
};

// How to show a follow-up: overdue (red), today (amber), later (blue), or none.
export const followUpInfo = (card, now = dayjs()) => {
  const due = parseUtc(card.follow_up);
  if (!due) return null;
  const days = due.startOf('day').diff(now.startOf('day'), 'day');
  if (card.overdue) return { color: 'red', text: `Overdue ${Math.max(1, -days)}d`, title: `Follow-up was due ${due.format('DD/MM, hh:mm A')}` };
  if (days === 0) return { color: 'gold', text: `Today ${due.format('hh:mm A')}`, title: 'Follow-up today' };
  return { color: 'blue', text: due.format('DD/MM'), title: `Follow-up ${due.format('DD/MM/YYYY, hh:mm A')}` };
};

export const scoreColor = (score) => (score >= 70 ? '#16a34a' : score >= 40 ? '#d97706' : '#6b7280');

// Move one card between stages in the cached board without waiting for the server: the card leaves
// its column and lands at the top of the new one, and both counts shift by one. Values and overdue
// counts are fixed by the refetch that follows; this only has to look right for a moment.
export const applyMove = (board, card, toStageId) => {
  if (!board) return board;
  const stages = board.stages.map((s) => {
    if (s.id === card.stage) {
      return { ...s, count: Math.max(0, s.count - 1), cards: s.cards.filter((c) => c.lead_id !== card.lead_id) };
    }
    if (s.id === toStageId) {
      return { ...s, count: s.count + 1, cards: [{ ...card, stage: toStageId, status: toStageId === 'Lost' ? card.status : toStageId }, ...s.cards] };
    }
    return s;
  });
  return { ...board, stages };
};
