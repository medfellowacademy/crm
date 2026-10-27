import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import dayjs from 'dayjs';
import { displayAPI } from '../api/api';
import { fmt } from '../utils/finance';

const POLL_MS = 15000;
const CELEBRATE_MS = 12000;
const GOLD = '#facc15';
const GREEN = '#22c55e';

const barColor = (pct) => (pct == null ? '#475569' : pct >= 100 ? GREEN : pct >= 60 ? '#38bdf8' : '#f59e0b');

// ── Confetti: a small self-contained canvas, no dependency ───────────────────
function Confetti({ burstKey }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !burstKey) return undefined;
    const ctx = canvas.getContext('2d');
    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
    resize();
    window.addEventListener('resize', resize);
    const colors = ['#facc15', '#22c55e', '#38bdf8', '#f472b6', '#fb923c', '#a78bfa', '#ffffff'];
    const pieces = Array.from({ length: 220 }, () => ({
      x: Math.random() * canvas.width, y: -20 - Math.random() * canvas.height * 0.6,
      w: 8 + Math.random() * 8, h: 10 + Math.random() * 10, c: colors[Math.floor(Math.random() * colors.length)],
      vx: -1.5 + Math.random() * 3, vy: 2.5 + Math.random() * 4, r: Math.random() * Math.PI, vr: -0.2 + Math.random() * 0.4,
    }));
    let raf;
    const end = performance.now() + CELEBRATE_MS - 1500;
    const frame = (t) => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      pieces.forEach((p) => {
        p.x += p.vx; p.y += p.vy; p.r += p.vr;
        if (p.y > canvas.height + 20 && t < end) { p.y = -20; p.x = Math.random() * canvas.width; }   // keep raining until the end
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillStyle = p.c; ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h); ctx.restore();
      });
      if (t < end || pieces.some((p) => p.y < canvas.height + 20)) raf = requestAnimationFrame(frame);
      else ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize); ctx.clearRect(0, 0, canvas.width, canvas.height); };
  }, [burstKey]);
  return <canvas ref={ref} style={{ position: 'fixed', inset: 0, zIndex: 60, pointerEvents: 'none' }} />;
}

// ── Sound: a short chime, only after someone clicked "Enable sound" once ─────
function playChime(ctx) {
  [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => {
    const o = ctx.createOscillator(); const g = ctx.createGain();
    o.type = 'triangle'; o.frequency.value = f;
    const t0 = ctx.currentTime + i * 0.16;
    g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(0.25, t0 + 0.03); g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.6);
    o.connect(g); g.connect(ctx.destination); o.start(t0); o.stop(t0 + 0.65);
  });
}

function Bar({ pct, height = 14 }) {
  return (
    <div style={{ background: '#1e293b', borderRadius: 99, height, overflow: 'hidden' }}>
      <div style={{ width: `${Math.min(100, pct || 0)}%`, height: '100%', background: barColor(pct), borderRadius: 99, transition: 'width 1.2s ease' }} />
    </div>
  );
}

function Big({ label, value, target, pct }) {
  return (
    <div style={{ flex: 1, minWidth: 320 }}>
      <div style={{ color: '#94a3b8', fontSize: 'clamp(14px,1.4vw,22px)', textTransform: 'uppercase', letterSpacing: 2 }}>{label}</div>
      <div style={{ fontSize: 'clamp(36px,5vw,84px)', fontWeight: 800, lineHeight: 1.05 }}>{value}</div>
      {target ? (
        <>
          <div style={{ color: '#cbd5e1', fontSize: 'clamp(14px,1.5vw,24px)', margin: '6px 0 10px' }}>
            Target {typeof target === 'number' && label.includes('Revenue') ? fmt(target) : target} · <b style={{ color: barColor(pct) }}>{pct}%</b>
          </div>
          <Bar pct={pct} height={18} />
        </>
      ) : <div style={{ color: '#64748b', fontSize: 'clamp(14px,1.4vw,22px)' }}>No target set</div>}
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
  const seen = useRef(null);                                // ids already shown; null until the first load
  const queue = useRef([]);
  const audio = useRef(null);
  const showing = useRef(false);

  const next = useCallback(() => {
    const sale = queue.current.shift();
    if (!sale) { showing.current = false; setCelebration(null); return; }
    showing.current = true;
    setCelebration(sale);
    setBurst((b) => b + 1);
    if (audio.current) { try { playChime(audio.current); } catch { /* sound is optional */ } }
    setTimeout(next, CELEBRATE_MS);
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

  useEffect(() => { document.title = 'MedFellow — Sales Screen'; }, []);

  const enableSound = () => {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      audio.current = audio.current || new Ctx();
      audio.current.resume?.();
      playChime(audio.current);
      setSoundOn(true);
    } catch { /* browser without audio: silently stay muted */ }
  };

  const page = { minHeight: '100vh', background: 'radial-gradient(circle at 20% 0%, #14325f 0%, #0b1220 55%)', color: '#f8fafc', padding: '2vh 3vw', fontFamily: 'system-ui, Segoe UI, sans-serif', boxSizing: 'border-box' };

  if (state === 'invalid') {
    return <div style={{ ...page, display: 'grid', placeItems: 'center', textAlign: 'center' }}>
      <div><div style={{ fontSize: 64 }}>🔒</div><h1>This screen link is no longer valid</h1><p style={{ color: '#94a3b8' }}>Ask an admin for the new link (Sales Targets page).</p></div></div>;
  }
  if (!data) {
    return <div style={{ ...page, display: 'grid', placeItems: 'center' }}><div style={{ fontSize: 28, color: '#94a3b8' }}>{state === 'offline' ? 'Connecting…' : 'Loading…'}</div></div>;
  }

  const { team, people, recent } = data;
  const top = people.slice(0, 10);

  return (
    <div style={page}>
      <Confetti burstKey={burst} />

      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: '2vh' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <div style={{ background: '#fff', borderRadius: 14, padding: '6px 12px' }}><img src="/medfellow-logo.png" alt="MedFellow Academy" style={{ height: 'clamp(36px,5vh,64px)', display: 'block' }} /></div>
          <div>
            <div style={{ fontSize: 'clamp(22px,3vw,48px)', fontWeight: 800 }}>Sales — {dayjs(`${data.month}-01`).format('MMMM YYYY')}</div>
            <div style={{ color: '#94a3b8', fontSize: 'clamp(12px,1.1vw,18px)' }}>
              {state === 'offline' ? '⚠ Reconnecting — showing last update ' : 'Live · updated '}{dayjs(data.generated_at).format('hh:mm:ss A')}
            </div>
          </div>
        </div>
        {!soundOn && <button onClick={enableSound} style={{ background: '#1e293b', color: '#cbd5e1', border: '1px solid #334155', borderRadius: 10, padding: '8px 14px', fontSize: 16, cursor: 'pointer' }}>🔔 Enable sound</button>}
      </header>

      <section style={{ display: 'flex', flexWrap: 'wrap', gap: '3vw', background: 'rgba(15,23,42,.7)', border: '1px solid #1e293b', borderRadius: 24, padding: '2.5vh 2.5vw', marginBottom: '2vh' }}>
        <Big label="Team Revenue" value={fmt(team.revenue)} target={team.revenue_target} pct={team.revenue_pct} />
        <Big label="Enrollments" value={team.enrolled} target={team.enrollment_target} pct={team.enrollment_pct} />
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 3fr) minmax(0, 2fr)', gap: '2vw' }}>
        <section style={{ background: 'rgba(15,23,42,.7)', border: '1px solid #1e293b', borderRadius: 24, padding: '2vh 1.6vw' }}>
          <div style={{ color: '#94a3b8', letterSpacing: 2, textTransform: 'uppercase', fontSize: 'clamp(13px,1.2vw,20px)', marginBottom: 10 }}>Leaderboard</div>
          {top.length === 0 && <div style={{ color: '#64748b', fontSize: 22 }}>No team members yet</div>}
          {top.map((p) => (
            <div key={p.name} style={{ display: 'grid', gridTemplateColumns: '3.2vw minmax(0,1.3fr) minmax(0,2fr)', alignItems: 'center', gap: 14, padding: '1vh 0', borderTop: '1px solid #1e293b' }}>
              <div style={{ fontSize: 'clamp(18px,2vw,34px)', textAlign: 'center' }}>{p.rank <= 3 && p.revenue > 0 ? ['🥇', '🥈', '🥉'][p.rank - 1] : p.rank}</div>
              <div>
                <div style={{ fontSize: 'clamp(16px,1.8vw,30px)', fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
                <div style={{ color: '#94a3b8', fontSize: 'clamp(12px,1.1vw,18px)' }}>{p.enrolled} enrolled{p.enrollment_target ? ` / ${p.enrollment_target}` : ''}</div>
              </div>
              <div>
                <div style={{ fontSize: 'clamp(14px,1.5vw,26px)', fontWeight: 700, marginBottom: 4 }}>
                  {fmt(p.revenue)}{p.revenue_target ? <span style={{ color: '#94a3b8', fontWeight: 400 }}> / {fmt(p.revenue_target)} · <b style={{ color: barColor(p.revenue_pct) }}>{p.revenue_pct}%</b></span> : null}
                </div>
                <Bar pct={p.revenue_pct} height={10} />
              </div>
            </div>
          ))}
        </section>

        <section style={{ background: 'rgba(15,23,42,.7)', border: '1px solid #1e293b', borderRadius: 24, padding: '2vh 1.6vw' }}>
          <div style={{ color: '#94a3b8', letterSpacing: 2, textTransform: 'uppercase', fontSize: 'clamp(13px,1.2vw,20px)', marginBottom: 10 }}>Latest enrollments</div>
          {recent.length === 0 && <div style={{ color: '#64748b', fontSize: 22 }}>No enrollments yet</div>}
          {recent.slice(0, 6).map((r) => (
            <div key={r.id} style={{ padding: '1.1vh 0', borderTop: '1px solid #1e293b' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 'clamp(15px,1.6vw,26px)', fontWeight: 700 }}>
                <span>🎓 {r.student}</span><span style={{ color: GOLD }}>{fmt(r.amount)}</span>
              </div>
              <div style={{ color: '#94a3b8', fontSize: 'clamp(12px,1.1vw,18px)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {r.course} · by {r.counselor} · {dayjs(r.at).format('DD MMM')}
              </div>
            </div>
          ))}
        </section>
      </div>

      {celebration && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(2,6,23,.82)', display: 'grid', placeItems: 'center', animation: 'pop .5s ease' }}>
          <div style={{ textAlign: 'center', padding: '5vh 6vw', maxWidth: '86vw' }}>
            <div style={{ fontSize: 'clamp(60px,10vw,160px)', lineHeight: 1 }}>🎉</div>
            <div style={{ fontSize: 'clamp(28px,5vw,80px)', fontWeight: 900, color: GOLD, textTransform: 'uppercase', letterSpacing: 3 }}>New Enrollment!</div>
            <div style={{ fontSize: 'clamp(24px,4vw,64px)', fontWeight: 800, margin: '2vh 0' }}>{celebration.student} joined</div>
            <div style={{ fontSize: 'clamp(16px,2.4vw,40px)', color: '#cbd5e1' }}>{celebration.course}</div>
            <div style={{ fontSize: 'clamp(20px,3vw,52px)', margin: '3vh 0', color: GREEN, fontWeight: 800 }}>{fmt(celebration.amount)}</div>
            <div style={{ fontSize: 'clamp(18px,2.6vw,44px)' }}>Closed by <b style={{ color: '#38bdf8' }}>{celebration.counselor}</b> 👏</div>
          </div>
        </div>
      )}
      <style>{'@keyframes pop { from { opacity: 0; transform: scale(.92); } to { opacity: 1; transform: scale(1); } }'}</style>
    </div>
  );
}
