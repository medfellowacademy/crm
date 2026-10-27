import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { fmt } from '../../../utils/finance';
import {
  LEMON, LAVENDER, INK, MUTED, DISPLAY_FONT, BODY_FONT, FS, barColor,
} from '../salesTheme';

// Numbers roll to their new value instead of jumping.
export function useCountUp(target, ms = 1400) {
  const [val, setVal] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    let raf;
    const tick = (t) => {
      const p = Math.min(1, (t - start) / ms);
      const v = a + (target - a) * (1 - (1 - p) ** 3);
      setVal(v);
      from.current = v;
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return Math.round(val);
}

export const panel = { background: '#1f1f1f', border: '1px solid #2c2c2c', borderRadius: 28, padding: '2vh 1.5vw' };

export const sectionLabel = {
  fontFamily: BODY_FONT, fontWeight: 700, color: MUTED, letterSpacing: 0.3,
  fontSize: FS.label, marginBottom: '1.2vh',
};

// Rupees the short way for big tiles: ₹12.4L, ₹1.2Cr. Anything under a lakh stays in full.
export function fmtShort(n) {
  const v = Math.round(Number(n) || 0);
  const trim = (x) => String(Math.round(x * 10) / 10).replace(/\.0$/, '');
  if (v >= 1e7) return `₹${trim(v / 1e7)}Cr`;
  if (v >= 1e5) return `₹${trim(v / 1e5)}L`;
  return fmt(v);
}

export const ellipsis = { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' };

export function Panel({ title, children, style }) {
  return (
    <section style={{ ...panel, minHeight: 0, minWidth: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', ...style }}>
      {title && <div style={sectionLabel}>{title}</div>}
      {children}
    </section>
  );
}

export function Bar({ pct, height = 12, track = '#2a2a2a', color }) {
  const c = color || barColor(pct);
  return (
    <div style={{ background: track, borderRadius: 99, height, overflow: 'hidden' }}>
      <div style={{ width: `${Math.min(100, pct || 0)}%`, height: '100%', background: c, borderRadius: 99, transition: 'width 1.4s cubic-bezier(.2,.8,.2,1)', boxShadow: pct >= 100 ? `0 0 14px ${c}` : undefined }} />
    </div>
  );
}

// A big KPI block. tone: lemon (black text) | lavender | dark (outlined).
export function Kpi({ tone = 'dark', label, value, money, sub, target, pct, chip, grow = 1 }) {
  const shown = useCountUp(Number(value) || 0);
  const lemon = tone === 'lemon';
  const dark = tone === 'dark';
  const bg = lemon ? LEMON : dark ? '#1f1f1f' : LAVENDER;
  const fg = lemon ? INK : '#fff';
  return (
    <div style={{ position: 'relative', flex: grow, minWidth: 0, background: bg, color: fg, borderRadius: 28, padding: '1.8vh 1.6vw', overflow: 'hidden', border: dark ? '1px solid #2c2c2c' : 'none', boxShadow: dark ? undefined : `0 10px 50px ${bg}33` }}>
      <div style={{ position: 'absolute', right: -40, top: -40, width: 150, height: 150, borderRadius: '50%', border: `20px solid ${lemon ? '#00000014' : '#ffffff14'}` }} />
      <div style={{ fontFamily: BODY_FONT, fontWeight: 700, letterSpacing: 0.3, fontSize: FS.label, opacity: 0.9 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ fontFamily: DISPLAY_FONT, fontSize: FS.hero, lineHeight: 1.05, margin: '0.4vh 0' }}>{money ? fmtShort(shown) : shown.toLocaleString('en-IN')}</div>
        {chip != null && <Chip value={chip} light={!lemon} />}
      </div>
      {target ? (
        <>
          <div style={{ fontFamily: BODY_FONT, fontWeight: 500, fontSize: FS.caption, marginBottom: 8 }}>
            of {money ? fmtShort(target) : target} target · <b>{pct}%</b>{pct >= 100 ? ' 🔥' : ''}
          </div>
          <Bar pct={pct} height={14} track={lemon ? '#00000022' : '#ffffff33'} color={lemon ? INK : LEMON} />
        </>
      ) : sub ? <div style={{ fontFamily: BODY_FONT, opacity: 0.75, fontSize: FS.caption }}>{sub}</div> : null}
    </div>
  );
}

// Growth vs last month: ▲ 12% / ▼ 5%.
export function Chip({ value, light }) {
  if (value == null) return null;
  const up = value >= 0;
  return (
    <span style={{ fontFamily: BODY_FONT, fontWeight: 700, fontSize: FS.caption, padding: '2px 10px', borderRadius: 99, background: up ? '#22c55e' : '#ef4444', color: '#fff', opacity: light ? 1 : 0.95 }}>
      {up ? '▲' : '▼'} {Math.abs(value)}%
    </span>
  );
}

// Horizontal list of "name ... bar ... count".
export function RankedBars({ items, color = LAVENDER, unit = '' }) {
  const max = Math.max(1, ...items.map((i) => i.count));
  if (!items.length) return <div style={{ color: MUTED, fontSize: FS.label }}>Nothing yet this month</div>;
  return items.map((it, i) => (
    <div key={it.name} style={{ marginBottom: '1vh', animation: `slideUp .5s ${i * 0.07}s both` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontFamily: BODY_FONT, fontWeight: 700, fontSize: FS.caption }}>
        <span style={ellipsis}>{it.name}</span><span style={{ color: LEMON }}>{it.count}{unit}</span>
      </div>
      <Bar pct={(it.count / max) * 100} height={8} color={color} />
    </div>
  ));
}

export const Empty = ({ children }) => (
  <div style={{ flex: 1, display: 'grid', placeItems: 'center', color: MUTED, fontFamily: BODY_FONT, fontSize: FS.label, textAlign: 'center', padding: '4vh 2vw' }}>{children}</div>
);

// One line of text that shrinks to fit its box (down to `min` of its size) instead of being cut off.
// Past that it falls back to an ellipsis.
export function FitText({ children, min = 0.6, style }) {
  const outer = useRef(null);
  const inner = useRef(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const fit = () => {
      const o = outer.current; const i = inner.current;
      if (!o || !i) return;
      i.style.fontSize = '1em';
      const need = i.scrollWidth;
      setScale(need > o.clientWidth && need > 0 ? Math.max(min, o.clientWidth / need) : 1);
    };
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, [children, min]);
  return (
    <div ref={outer} style={{ minWidth: 0, ...ellipsis, ...style }}>
      <span ref={inner} style={{ fontSize: `${scale}em`, whiteSpace: 'nowrap' }}>{children}</span>
    </div>
  );
}
