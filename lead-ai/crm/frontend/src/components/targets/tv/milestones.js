// Moments worth a banner on the celebration screen, found by comparing the company
// numbers before and after a new sale. One banner at most; the biggest moment wins.

export function ordinal(n) {
  const r = n % 100;
  if (r >= 11 && r <= 13) return `${n}th`;
  return `${n}${({ 1: 'st', 2: 'nd', 3: 'rd' })[n % 10] || 'th'}`;
}

export function milestoneFor(prev, cur) {
  if (!prev || !cur) return null;
  const was = prev.revenue_pct;
  const now = cur.revenue_pct;
  if (now != null && now >= 100 && !(was != null && was >= 100)) return { icon: '🏆', text: 'Company target reached!' };
  if (cur.enrolled > prev.enrolled) {
    const n = Math.floor(cur.enrolled / 5) * 5;
    if (n >= 5 && n > prev.enrolled) return { icon: '🔥', text: `${ordinal(n)} enrollment this month!` };
  }
  if (now != null && was != null) {
    const hit = [75, 50, 25].find((t) => was < t && now >= t);
    if (hit) return { icon: '🎯', text: `Company crossed ${hit}% of target` };
  }
  return null;
}
