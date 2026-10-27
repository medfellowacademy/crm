// Brand look for Sales Targets + the office TV: lemon, charcoal, electric lavender.
export const LEMON = '#FFF21A';
export const CHARCOAL = '#171717';
export const LAVENDER = '#A66BFF';
export const INK = '#0d0d0d';
export const MUTED = '#a3a3a3';

export const DISPLAY_FONT = "'Archivo Black', 'Arial Black', Impact, sans-serif";
export const BODY_FONT = "'Space Grotesk', 'Segoe UI', system-ui, sans-serif";

export const FONT_LINK =
  'https://fonts.googleapis.com/css2?family=Archivo+Black&family=Space+Grotesk:wght@400;500;700&display=swap';

// Progress colour: lavender while building, lemon when close, white-hot lemon glow at/over target.
export const barColor = (pct) => (pct == null ? '#404040' : pct >= 100 ? LEMON : pct >= 60 ? LAVENDER : '#7c4dcc');

// Loaded lazily so the TV still works (with the fallback stack) if it is offline.
export function loadBrandFonts() {
  if (typeof document === 'undefined' || document.getElementById('sales-brand-fonts')) return;
  const link = document.createElement('link');
  link.id = 'sales-brand-fonts';
  link.rel = 'stylesheet';
  link.href = FONT_LINK;
  document.head.appendChild(link);
}
