// Brand look for Sales Targets + the office TV: lemon, charcoal, electric lavender.
export const LEMON = '#FFF21A';
export const CHARCOAL = '#171717';
export const LAVENDER = '#A66BFF';
export const INK = '#0d0d0d';
export const MUTED = '#c7c7c7';       // light enough to read from across an office

// The one type scale for the TV. Each size follows the screen width but is also capped by its height,
// so it stays readable on 16:9, ultrawide and portrait screens alike. Use these, not ad-hoc sizes.
export const FS = {
  caption: 'clamp(14px,min(1.3vw,2.3vh),22px)',
  label: 'clamp(16px,min(1.6vw,2.85vh),27px)',
  name: 'clamp(18px,min(2.1vw,3.7vh),36px)',
  title: 'clamp(26px,min(3.4vw,6vh),62px)',
  hero: 'clamp(34px,min(4.8vw,8.5vh),88px)',
};

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
