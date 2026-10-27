import React, { useEffect, useRef, useState } from 'react';
import { fmt } from '../../../utils/finance';
import {
  LEMON, LAVENDER, INK, MUTED, DISPLAY_FONT, BODY_FONT, barColor,
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
  fontFamily: BODY_FONT, fontWeight: 700, color: MUTED, letterSpacing: 3, textTransform: 'uppercase',
  fontSize: 'clamp(13px,1.26vw,22px)', marginBottom: '1.2vh',
};

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
export function Kpi({ tone = 'dark', label, value, money, sub, target, pct, chip }) {
  const shown = useCountUp(Number(value) || 0);
  const lemon = tone === 'lemon';
  const dark = tone === 'dark';
  const bg = lemon ? LEMON : dark ? '#1f1f1f' : LAVENDER;
  const fg = lemon ? INK : '#fff';
  return (
    <div style={{ position: 'relative', flex: 1, minWidth: 0, background: bg, color: fg, borderRadius: 28, padding: '1.8vh 1.6vw', overflow: 'hidden', border: dark ? '1px solid #2c2c2c' : 'none', boxShadow: dark ? undefined : `0 10px 50px ${bg}33` }}>
      <div style={{ position: 'absolute', right: -40, top: -40, width: 150, height: 150, borderRadius: '50%', border: `20px solid ${lemon ? '#00000014' : '#ffffff14'}` }} />
      <div style={{ fontFamily: BODY_FONT, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', fontSize: 'clamp(13px,1.32vw,23px)', opacity: 0.8 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'clamp(28px,4.2vw,80px)', lineHeight: 1.05, margin: '0.4vh 0' }}>{money ? fmt(shown) : shown.toLocaleString('en-IN')}</div>
        {chip != null && <Chip value={chip} light={!lemon} />}
      </div>
      {target ? (
        <>
          <div style={{ fontFamily: BODY_FONT, fontWeight: 500, fontSize: 'clamp(14px,1.5vw,25px)', marginBottom: 8 }}>
            of {money ? fmt(target) : target} target · <b>{pct}%</b>{pct >= 100 ? ' 🔥' : ''}
          </div>
          <Bar pct={pct} height={14} track={lemon ? '#00000022' : '#ffffff33'} color={lemon ? INK : LEMON} />
        </>
      ) : sub ? <div style={{ fontFamily: BODY_FONT, opacity: 0.75, fontSize: 'clamp(14px,1.5vw,25px)' }}>{sub}</div> : null}
    </div>
  );
}

// Growth vs last month: ▲ 12% / ▼ 5%.
export function Chip({ value, light }) {
  if (value == null) return null;
  const up = value >= 0;
  return (
    <span style={{ fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(13px,1.32vw,23px)', padding: '2px 10px', borderRadius: 99, background: up ? '#22c55e' : '#ef4444', color: '#fff', opacity: light ? 1 : 0.95 }}>
      {up ? '▲' : '▼'} {Math.abs(value)}%
    </span>
  );
}

// Horizontal list of "name ... bar ... count".
export function RankedBars({ items, color = LAVENDER, unit = '' }) {
  const max = Math.max(1, ...items.map((i) => i.count));
  if (!items.length) return <div style={{ color: MUTED, fontSize: 'clamp(15px,1.56vw,26px)' }}>Nothing yet this month</div>;
  return items.map((it, i) => (
    <div key={it.name} style={{ marginBottom: '1vh', animation: `slideUp .5s ${i * 0.07}s both` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(14px,1.5vw,25px)' }}>
        <span style={ellipsis}>{it.name}</span><span style={{ color: LEMON }}>{it.count}{unit}</span>
      </div>
      <Bar pct={(it.count / max) * 100} height={8} color={color} />
    </div>
  ));
}

export const Empty = ({ children }) => (
  <div style={{ flex: 1, display: 'grid', placeItems: 'center', color: MUTED, fontFamily: BODY_FONT, fontSize: 'clamp(16px,1.8vw,30px)', textAlign: 'center', padding: '4vh 2vw' }}>{children}</div>
);
