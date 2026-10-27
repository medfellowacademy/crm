import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import dayjs from 'dayjs';
import { displayAPI } from '../api/api';
import { fmt } from '../utils/finance';
import { SalesAvatar } from '../components/targets/SalesAvatar';
import {
  LEMON, CHARCOAL, LAVENDER, INK, MUTED, DISPLAY_FONT, BODY_FONT, barColor, loadBrandFonts,
} from '../components/targets/salesTheme';

const POLL_MS = 15000;
const CELEBRATE_MS = 14000;
// Drop a file at frontend/public/celebration.mp4 and it plays behind every celebration.
const CELEBRATION_VIDEO = '/celebration.mp4';

// ── Count-up: numbers roll to their new value instead of jumping ─────────────
function useCountUp(target, ms = 1400) {
  const [val, setVal] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    let raf;
    const tick = (t) => {
      const p = Math.min(1, (t - start) / ms);
      const eased = 1 - (1 - p) ** 3;
      const v = a + (target - a) * eased;
      setVal(v);
      from.current = v;
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return Math.round(val);
}

// ── Confetti in brand colours: squares, dots and triangles ───────────────────
function Confetti({ burstKey }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !burstKey) return undefined;
    const ctx = canvas.getContext('2d');
    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
    resize();
    window.addEventListener('resize', resize);
    const colors = [LEMON, LEMON, LAVENDER, LAVENDER, '#ffffff', '#c9a6ff', '#fff77a'];
    const make = (fromCannon, side) => ({
      x: fromCannon ? (side ? canvas.width + 10 : -10) : Math.random() * canvas.width,
      y: fromCannon ? canvas.height * (0.55 + Math.random() * 0.4) : -20 - Math.random() * canvas.height * 0.5,
      w: 8 + Math.random() * 10, h: 10 + Math.random() * 12, c: colors[Math.floor(Math.random() * colors.length)],
      vx: fromCannon ? (side ? -1 : 1) * (6 + Math.random() * 12) : -1.5 + Math.random() * 3,
      vy: fromCannon ? -(10 + Math.random() * 14) : 2.5 + Math.random() * 4,
      r: Math.random() * Math.PI, vr: -0.25 + Math.random() * 0.5, shape: Math.floor(Math.random() * 3), cannon: fromCannon,
    });
    const pieces = [
      ...Array.from({ length: 140 }, () => make(false)),
      ...Array.from({ length: 90 }, () => make(true, 0)),
      ...Array.from({ length: 90 }, () => make(true, 1)),
    ];
    let raf;
    const end = performance.now() + CELEBRATE_MS - 2500;
    const frame = (t) => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      pieces.forEach((p) => {
        if (p.cannon) { p.vy += 0.35; p.vx *= 0.985; if (p.vy > 3) p.cannon = false; }
        p.x += p.vx; p.y += p.vy; p.r += p.vr;
        if (!p.cannon && p.y > canvas.height + 20 && t < end) { p.y = -20; p.x = Math.random() * canvas.width; p.vx = -1.5 + Math.random() * 3; }
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillStyle = p.c;
        if (p.shape === 0) ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        else if (p.shape === 1) { ctx.beginPath(); ctx.arc(0, 0, p.w / 2, 0, Math.PI * 2); ctx.fill(); }
        else { ctx.beginPath(); ctx.moveTo(0, -p.h / 2); ctx.lineTo(p.w / 2, p.h / 2); ctx.lineTo(-p.w / 2, p.h / 2); ctx.closePath(); ctx.fill(); }
        ctx.restore();
      });
      if (t < end || pieces.some((p) => p.y < canvas.height + 20)) raf = requestAnimationFrame(frame);
      else ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize); ctx.clearRect(0, 0, canvas.width, canvas.height); };
  }, [burstKey]);
  return <canvas ref={ref} style={{ position: 'fixed', inset: 0, zIndex: 80, pointerEvents: 'none' }} />;
}

// ── Sound: a short chime, only after someone clicked "Enable sound" once ────
function playChime(ctx) {
  [523.25, 659.25, 783.99, 1046.5, 1318.5].forEach((f, i) => {
    const o = ctx.createOscillator(); const g = ctx.createGain();
    o.type = 'triangle'; o.frequency.value = f;
    const t0 = ctx.currentTime + i * 0.14;
    g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(0.28, t0 + 0.03); g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.7);
    o.connect(g); g.connect(ctx.destination); o.start(t0); o.stop(t0 + 0.75);
  });
}

function Bar({ pct, height = 12, track = '#2a2a2a', color }) {
  const c = color || barColor(pct);
  return (
    <div style={{ background: track, borderRadius: 99, height, overflow: 'hidden' }}>
      <div style={{ width: `${Math.min(100, pct || 0)}%`, height: '100%', background: c, borderRadius: 99, transition: 'width 1.4s cubic-bezier(.2,.8,.2,1)', boxShadow: pct >= 100 ? `0 0 14px ${c}` : undefined }} />
    </div>
  );
}

// A big KPI block. `tone` picks the brand colour: lemon (black text) or lavender.
function Kpi({ tone, label, value, money, target, pct }) {
  const shown = useCountUp(value);
  const lemon = tone === 'lemon';
  const bg = lemon ? LEMON : LAVENDER;
  const fg = lemon ? INK : '#fff';
  return (
    <div style={{ position: 'relative', flex: 1, minWidth: 0, background: bg, color: fg, borderRadius: 28, padding: '1.8vh 1.6vw', overflow: 'hidden', boxShadow: `0 10px 50px ${bg}33` }}>
      <div style={{ position: 'absolute', right: -40, top: -40, width: 160, height: 160, borderRadius: '50%', border: `22px solid ${lemon ? '#00000014' : '#ffffff22'}` }} />
      <div style={{ fontFamily: BODY_FONT, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', fontSize: 'clamp(12px,1.2vw,20px)', opacity: 0.8 }}>{label}</div>
      <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'clamp(30px,4.4vw,84px)', lineHeight: 1.05, margin: '0.4vh 0' }}>{money ? fmt(shown) : shown}</div>
      {target ? (
        <>
          <div style={{ fontFamily: BODY_FONT, fontWeight: 500, fontSize: 'clamp(13px,1.3vw,22px)', marginBottom: 8 }}>
            of {money ? fmt(target) : target} target · <b>{pct}%</b>{pct >= 100 ? ' 🔥' : ''}
          </div>
          <Bar pct={pct} height={14} track={lemon ? '#00000022' : '#ffffff33'} color={lemon ? INK : LEMON} />
        </>
      ) : <div style={{ fontFamily: BODY_FONT, opacity: 0.7, fontSize: 'clamp(13px,1.3vw,22px)' }}>No target set</div>}
    </div>
  );
}

const MEDAL = ['👑', '🥈', '🥉'];

function Podium({ people, photo }) {
  const [first, second, third] = people;
  const slots = [
    { p: second, place: 2, size: '9vh', lift: 0, ring: '#d4d4d4' },
    { p: first, place: 1, size: '13vh', lift: '-1.2vh', ring: LEMON },
    { p: third, place: 3, size: '9vh', lift: 0, ring: LAVENDER },
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr 1fr', gap: '1.2vw', alignItems: 'end', marginBottom: '1vh' }}>
      {slots.map(({ p, place, size, lift, ring }) => (
        <div key={place} style={{ transform: `translateY(${lift})`, textAlign: 'center', background: place === 1 ? `linear-gradient(180deg, ${LEMON}22, transparent)` : 'transparent', borderRadius: 22, padding: '1.2vh 0.6vw', animation: `slideUp .8s ${place * 0.12}s both` }}>
          {p ? (
            <>
              <div style={{ fontSize: place === 1 ? 'clamp(22px,2.6vw,44px)' : 'clamp(16px,1.8vw,30px)', lineHeight: 1, marginBottom: 4, animation: place === 1 ? 'floatY 2.4s ease-in-out infinite' : undefined }}>{MEDAL[place - 1]}</div>
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <SalesAvatar name={p.name} src={photo(p)} size={place === 1 ? 150 : 100} style={{ width: size, height: size }} ring={ring} ringWidth={place === 1 ? 5 : 3} glow={place === 1} />
              </div>
              <div style={{ fontFamily: DISPLAY_FONT, fontSize: place === 1 ? 'clamp(16px,2vw,34px)' : 'clamp(13px,1.4vw,24px)', marginTop: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
              <div style={{ fontFamily: BODY_FONT, fontWeight: 700, color: place === 1 ? LEMON : '#fff', fontSize: place === 1 ? 'clamp(15px,1.8vw,30px)' : 'clamp(12px,1.3vw,22px)' }}>{fmt(p.revenue)}</div>
              <div style={{ fontFamily: BODY_FONT, color: MUTED, fontSize: 'clamp(11px,1vw,17px)' }}>{p.enrolled} enrolled{p.revenue_pct != null ? ` · ${p.revenue_pct}%` : ''}</div>
            </>
          ) : <div style={{ height: size }} />}
        </div>
      ))}
    </div>
  );
}

export default function OfficeScreenPage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [state, setState] = useState('loading');           // loading | ok | offline | invalid
  const [celebration, setCelebration] = useState(null);
  const [burst, setBurst] = useState(0);
  const [soundOn, setSoundOn] = useState(false);
  const [videoOk, setVideoOk] = useState(true);
  const [now, setNow] = useState(dayjs());
  const [vh, setVh] = useState(typeof window === 'undefined' ? 1080 : window.innerHeight);
  const seen = useRef(null);                                // ids already shown; null until the first load
  const queue = useRef([]);
  const audio = useRef(null);
  const showing = useRef(false);
  const timers = useRef([]);

  const photo = useCallback((p) => (p && p.user_id && p.avatar_v ? displayAPI.avatarUrl(token, p.user_id, p.avatar_v) : null), [token]);

  const next = useCallback(() => {
    const sale = queue.current.shift();
    if (!sale) { showing.current = false; setCelebration(null); return; }
    showing.current = true;
    setVideoOk(true);
    setCelebration(sale);
    setBurst((b) => b + 1);
    if (audio.current) { try { playChime(audio.current); } catch { /* sound is optional */ } }
    timers.current.push(setTimeout(next, CELEBRATE_MS));
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await displayAPI.feed(token);
      const d = res.data;
      setData(d);
      setState('ok');
      const ids = (d.recent || []).map((r) => r.id);
      if (seen.current === null) {
        seen.current = new Set(ids);                        // first load: don't celebrate history
      } else {
        const fresh = (d.recent || []).filter((r) => !seen.current.has(r.id)).reverse();   // oldest first
        fresh.forEach((r) => seen.current.add(r.id));
        if (fresh.length) {
          queue.current.push(...fresh);
          if (!showing.current) next();
        }
      }
    } catch (e) {
      setState(e?.response?.status === 404 ? 'invalid' : 'offline');   // keep showing the last numbers when offline
    }
  }, [token, next]);

  useEffect(() => {
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    loadBrandFonts();
    document.title = 'MedFellow — Sales Screen';
    const clock = setInterval(() => setNow(dayjs()), 1000);
    const onResize = () => setVh(window.innerHeight);
    window.addEventListener('resize', onResize);
    const pending = timers.current;
    return () => { clearInterval(clock); window.removeEventListener('resize', onResize); pending.forEach(clearTimeout); };
  }, []);

  const enableSound = () => {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      audio.current = audio.current || new Ctx();
      audio.current.resume?.();
      playChime(audio.current);
      setSoundOn(true);
    } catch { /* browser without audio: silently stay muted */ }
  };

  const page = {
    height: '100vh', background: CHARCOAL, color: '#fff', fontFamily: BODY_FONT, boxSizing: 'border-box',
    padding: '2vh 2.4vw 0', position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column',
  };

  if (state === 'invalid') {
    return (
      <div style={{ ...page, display: 'grid', placeItems: 'center', textAlign: 'center' }}>
        <div>
          <div style={{ fontSize: 64 }}>🔒</div>
          <h1 style={{ fontFamily: DISPLAY_FONT, color: LEMON }}>This screen link is no longer valid</h1>
          <p style={{ color: MUTED }}>Ask an admin for the new link (Sales Targets page).</p>
        </div>
      </div>
    );
  }
  if (!data) {
    return <div style={{ ...page, display: 'grid', placeItems: 'center' }}><div style={{ fontFamily: DISPLAY_FONT, fontSize: 28, color: LEMON }}>{state === 'offline' ? 'Connecting…' : 'Loading…'}</div></div>;
  }

  const { team, people, recent } = data;
  const monthLabel = dayjs(`${data.month}-01`).format('MMMM YYYY').toUpperCase();
  // only as many rows below the podium as fit the screen, so nothing is cut off mid-row
  const rest = people.slice(3, 3 + Math.max(0, Math.min(5, Math.floor((vh - 640) / 58))));
  const ticker = recent.length
    ? recent.map((r) => `🎓 ${r.student} joined ${r.course} — closed by ${r.counselor}`).join('   ✦   ')
    : 'Every enrollment shows up here the moment it happens';
  const strip = `SALES ${monthLabel}   ✦   ${fmt(team.revenue)} REVENUE   ✦   ${team.enrolled} ENROLLMENTS   ✦   ${ticker}   ✦   `;

  const panel = { background: '#1f1f1f', border: '1px solid #2c2c2c', borderRadius: 28, padding: '2vh 1.5vw' };
  const label = { fontFamily: BODY_FONT, fontWeight: 700, color: MUTED, letterSpacing: 3, textTransform: 'uppercase', fontSize: 'clamp(11px,1.05vw,18px)', marginBottom: '1.2vh' };

  return (
    <div style={page}>
      <style>{`
        @keyframes blobA { 0%,100% { transform: translate(0,0) scale(1); } 50% { transform: translate(8vw,6vh) scale(1.25); } }
        @keyframes blobB { 0%,100% { transform: translate(0,0) scale(1.1); } 50% { transform: translate(-7vw,-8vh) scale(.9); } }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes marquee { from { transform: translateX(0); } to { transform: translateX(-50%); } }
        @keyframes livePulse { 0% { box-shadow: 0 0 0 0 #ff3b3b99; } 100% { box-shadow: 0 0 0 14px #ff3b3b00; } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(40px); } to { opacity: 1; } }
        @keyframes floatY { 0%,100% { transform: translateY(0) rotate(-4deg); } 50% { transform: translateY(-10px) rotate(4deg); } }
        @keyframes popIn { 0% { opacity: 0; transform: scale(.55) rotate(-4deg); } 60% { opacity: 1; transform: scale(1.06) rotate(1deg); } 100% { transform: scale(1) rotate(0); } }
        @keyframes ring { 0% { transform: scale(.9); opacity: .9; } 100% { transform: scale(1.7); opacity: 0; } }
        @keyframes shine { from { background-position: 200% 0; } to { background-position: -200% 0; } }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideIn { from { opacity: 0; transform: translateX(-60px) skewX(-8deg); } to { opacity: 1; transform: none; } }
      `}</style>

      {/* living background */}
      <div aria-hidden style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0 }}>
        <div style={{ position: 'absolute', width: '42vw', height: '42vw', left: '-10vw', top: '-12vw', background: LAVENDER, opacity: 0.28, filter: 'blur(90px)', borderRadius: '50%', animation: 'blobA 18s ease-in-out infinite' }} />
        <div style={{ position: 'absolute', width: '36vw', height: '36vw', right: '-10vw', bottom: '-10vw', background: LEMON, opacity: 0.14, filter: 'blur(100px)', borderRadius: '50%', animation: 'blobB 22s ease-in-out infinite' }} />
        <div style={{ position: 'absolute', right: '6vw', top: '10vh', width: '9vw', height: '9vw', border: `2px dashed ${LEMON}55`, borderRadius: '50%', animation: 'spin 40s linear infinite' }} />
        <div style={{ position: 'absolute', inset: 0, backgroundImage: 'radial-gradient(#ffffff0d 1px, transparent 1px)', backgroundSize: '28px 28px' }} />
      </div>

      <Confetti burstKey={burst} />

      <div style={{ position: 'relative', zIndex: 1, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: '1.6vh' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.4vw' }}>
            <div style={{ background: LEMON, borderRadius: 18, padding: '6px 14px' }}><img src="/medfellow-logo.png" alt="MedFellow Academy" style={{ height: 'clamp(34px,5vh,62px)', display: 'block', mixBlendMode: 'multiply' }} /></div>
            <div>
              <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'clamp(26px,4.4vw,78px)', lineHeight: 1, letterSpacing: 1 }}>
                <span style={{ color: LEMON }}>SALES</span>{' '}
                <span style={{ color: 'transparent', WebkitTextStroke: `2px ${LAVENDER}` }}>{monthLabel.split(' ')[0]}</span>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            {!soundOn && <button onClick={enableSound} style={{ background: 'transparent', color: LEMON, border: `2px solid ${LEMON}`, borderRadius: 99, padding: '6px 16px', fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(12px,1.1vw,18px)', cursor: 'pointer' }}>🔔 Enable sound</button>}
            <div style={{ textAlign: 'right' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end', fontWeight: 700, fontSize: 'clamp(12px,1.1vw,18px)', letterSpacing: 2 }}>
                <span style={{ width: 12, height: 12, borderRadius: '50%', background: state === 'offline' ? '#f59e0b' : '#ff3b3b', animation: 'livePulse 1.4s infinite' }} />
                {state === 'offline' ? 'RECONNECTING' : 'LIVE'}
              </div>
              <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'clamp(18px,2.2vw,38px)' }}>{now.format('hh:mm A')}</div>
            </div>
          </div>
        </header>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,2.1fr) minmax(0,1fr)', gap: '1.6vw', flex: 1, minHeight: 0 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.6vh', minWidth: 0, minHeight: 0 }}>
            <div style={{ display: 'flex', gap: '1.4vw', flexWrap: 'wrap' }}>
              <Kpi tone="lemon" label="Team revenue" value={team.revenue} money target={team.revenue_target} pct={team.revenue_pct} />
              <Kpi tone="lavender" label="Enrollments" value={team.enrolled} target={team.enrollment_target} pct={team.enrollment_pct} />
            </div>

            <section style={{ ...panel, flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <div style={label}>Leaderboard</div>
              {people.length === 0 && <div style={{ color: MUTED, fontSize: 22 }}>No team members yet</div>}
              {people.length > 0 && <Podium people={people} photo={photo} />}
              {rest.map((p) => (
                <div key={p.name} style={{ display: 'grid', gridTemplateColumns: '2.4vw 4.2vh minmax(0,1.2fr) minmax(0,2fr)', alignItems: 'center', gap: 14, padding: '0.9vh 0', borderTop: '1px solid #2c2c2c' }}>
                  <div style={{ fontFamily: DISPLAY_FONT, color: MUTED, fontSize: 'clamp(14px,1.5vw,26px)', textAlign: 'center' }}>{p.rank}</div>
                  <SalesAvatar name={p.name} src={photo(p)} size={36} ring={LAVENDER} ringWidth={2} style={{ width: '4.2vh', height: '4.2vh' }} />
                  <div>
                    <div style={{ fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(14px,1.5vw,26px)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
                    <div style={{ color: MUTED, fontSize: 'clamp(11px,0.95vw,16px)' }}>{p.enrolled} enrolled{p.enrollment_target ? ` / ${p.enrollment_target}` : ''}</div>
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 'clamp(13px,1.3vw,22px)', marginBottom: 4 }}>
                      {fmt(p.revenue)}{p.revenue_target ? <span style={{ color: MUTED, fontWeight: 500 }}> / {fmt(p.revenue_target)} · <b style={{ color: barColor(p.revenue_pct) }}>{p.revenue_pct}%</b></span> : null}
                    </div>
                    <Bar pct={p.revenue_pct} height={9} />
                  </div>
                </div>
              ))}
            </section>
          </div>

          <section style={{ ...panel, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, overflow: 'hidden' }}>
            <div style={label}>Latest enrollments</div>
            {recent.length === 0 && <div style={{ color: MUTED, fontSize: 20 }}>No enrollments yet</div>}
            {recent.slice(0, 6).map((r, i) => (
              <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '1.2vh 0', borderTop: i ? '1px solid #2c2c2c' : 'none', animation: `slideUp .6s ${i * 0.08}s both` }}>
                <SalesAvatar name={r.counselor} src={photo({ user_id: r.counselor_id, avatar_v: r.avatar_v })} size={44} ring={i === 0 ? LEMON : LAVENDER} style={{ width: '5.4vh', height: '5.4vh' }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontWeight: 700, fontSize: 'clamp(14px,1.5vw,25px)' }}>
                    <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>🎓 {r.student}</span>
                    <span style={{ color: LEMON, fontFamily: DISPLAY_FONT }}>{fmt(r.amount)}</span>
                  </div>
                  <div style={{ color: MUTED, fontSize: 'clamp(11px,0.95vw,16px)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {r.course} · {r.counselor} · {dayjs(r.at).format('DD MMM')}
                  </div>
                </div>
              </div>
            ))}
          </section>
        </div>
      </div>

      {/* scrolling ticker */}
      <div style={{ position: 'relative', zIndex: 1, margin: '1.2vh -2.4vw 0', flex: '0 0 auto', background: LEMON, color: INK, overflow: 'hidden', whiteSpace: 'nowrap', padding: '1vh 0' }}>
        <div style={{ display: 'inline-block', fontFamily: DISPLAY_FONT, fontSize: 'clamp(14px,1.7vw,28px)', animation: `marquee ${Math.max(30, strip.length / 3)}s linear infinite` }}>
          <span>{strip}</span><span>{strip}</span>
        </div>
      </div>

      {/* new-enrollment celebration */}
      {celebration && (
        <div key={celebration.id} style={{ position: 'fixed', inset: 0, zIndex: 70, background: INK, display: 'grid', placeItems: 'center', animation: 'fadeIn .4s ease', overflow: 'hidden' }}>
          {videoOk && (
            <video src={CELEBRATION_VIDEO} autoPlay muted loop playsInline onError={() => setVideoOk(false)}
              style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.4 }} />
          )}
          {/* rotating light rays */}
          <div aria-hidden style={{ position: 'absolute', width: '220vmax', height: '220vmax', left: '50%', top: '50%', marginLeft: '-110vmax', marginTop: '-110vmax', background: `repeating-conic-gradient(${LEMON}33 0deg 10deg, transparent 10deg 30deg)`, animation: 'spin 28s linear infinite', maskImage: 'radial-gradient(circle, #000 0%, transparent 62%)', WebkitMaskImage: 'radial-gradient(circle, #000 0%, transparent 62%)' }} />
          <div aria-hidden style={{ position: 'absolute', width: '60vmin', height: '60vmin', borderRadius: '50%', background: LAVENDER, filter: 'blur(110px)', opacity: 0.55 }} />

          <div style={{ position: 'relative', textAlign: 'center', padding: '2vh 4vw', maxWidth: '92vw', maxHeight: '98vh', animation: 'popIn .8s cubic-bezier(.2,.9,.3,1.2) both' }}>
            <div style={{ position: 'relative', display: 'inline-block', marginBottom: '1.2vh' }}>
              {[0, 0.6, 1.2].map((d) => (
                <span key={d} style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: `4px solid ${LAVENDER}`, animation: `ring 2.4s ${d}s ease-out infinite` }} />
              ))}
              <SalesAvatar name={celebration.counselor} src={photo({ user_id: celebration.counselor_id, avatar_v: celebration.avatar_v })} size={200} ring={LEMON} ringWidth={8} glow style={{ width: 'min(20vh, 24vw)', height: 'min(20vh, 24vw)' }} />
              <span style={{ position: 'absolute', right: -14, bottom: -6, fontSize: 'min(5vw, 8vh)', animation: 'floatY 2s ease-in-out infinite' }}>🎉</span>
            </div>
            <div style={{ fontFamily: BODY_FONT, fontWeight: 700, letterSpacing: 6, color: LAVENDER, fontSize: 'min(1.8vw, 2.8vh)', textTransform: 'uppercase' }}>Closed by</div>
            <div style={{ fontFamily: DISPLAY_FONT, color: '#fff', fontSize: 'min(4vw, 6.4vh)', lineHeight: 1.05, animation: 'slideIn .7s .25s both' }}>{celebration.counselor}</div>
            <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'min(7.4vw, 11.5vh)', lineHeight: 1, margin: '1vh 0', textTransform: 'uppercase', background: `linear-gradient(100deg, ${LEMON} 30%, #fff 50%, ${LEMON} 70%)`, backgroundSize: '200% 100%', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', animation: 'slideIn .8s .4s both, shine 3s 1.2s linear infinite' }}>
              New Enrollment!
            </div>
            <div style={{ fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'min(3.2vw, 5vh)' }}>{celebration.student} just joined</div>
            <div style={{ fontFamily: BODY_FONT, color: '#d4d4d4', fontSize: 'min(2vw, 3.1vh)', margin: '0.4vh 0 1.4vh' }}>{celebration.course}</div>
            <Amount value={celebration.amount} />
          </div>
        </div>
      )}
    </div>
  );
}

function Amount({ value }) {
  const shown = useCountUp(value, 1800);
  return (
    <div style={{ display: 'inline-block', background: LAVENDER, color: '#fff', fontFamily: DISPLAY_FONT, fontSize: 'min(4vw, 6.4vh)', padding: '0.4vh 2vw', borderRadius: 99, boxShadow: `0 0 60px ${LAVENDER}aa`, animation: 'popIn .7s .8s both' }}>
      {fmt(shown)}
    </div>
  );
}
