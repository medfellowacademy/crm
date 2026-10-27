import React from 'react';
import dayjs from 'dayjs';
import { fmt } from '../../../utils/finance';
import { SalesAvatar } from '../SalesAvatar';
import {
  LEMON, LAVENDER, INK, MUTED, DISPLAY_FONT, BODY_FONT, barColor,
} from '../salesTheme';
import { Panel, Bar, Kpi, RankedBars, Empty, ellipsis, useCountUp } from './TvKit';

export const SLIDE_TITLES = {
  sales: 'Sales', teams: 'Teams', activity: 'Call report', analytics: 'Analytics',
  performance: 'Performance', attendance: 'Attendance', pipeline: 'Pipeline',
};

const row = { display: 'flex', gap: '1.4vw', minHeight: 0 };
const col = { display: 'flex', flexDirection: 'column', gap: '1.6vh', minHeight: 0, minWidth: 0 };
const MEDAL = ['👑', '🥈', '🥉'];

const inr = (n) => fmt(Math.round(n || 0));

// ── Sales ───────────────────────────────────────────────────────────────────
function Podium({ people, photo }) {
  const [first, second, third] = people;
  const slots = [
    { p: second, place: 2, size: '7vh', lift: 0, ring: '#d4d4d4' },
    { p: first, place: 1, size: '10vh', lift: '-1.2vh', ring: LEMON },
    { p: third, place: 3, size: '7vh', lift: 0, ring: LAVENDER },
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
              <div style={{ fontFamily: DISPLAY_FONT, fontSize: place === 1 ? 'clamp(16px,2vw,34px)' : 'clamp(15px,1.68vw,29px)', marginTop: 6, ...ellipsis }}>{p.name}</div>
              <div style={{ fontFamily: BODY_FONT, fontWeight: 700, color: place === 1 ? LEMON : '#fff', fontSize: place === 1 ? 'clamp(15px,1.8vw,30px)' : 'clamp(14px,1.56vw,26px)' }}>{fmt(p.revenue)}</div>
              <div style={{ fontFamily: BODY_FONT, color: MUTED, fontSize: 'clamp(13px,1.2vw,20px)' }}>{p.enrolled} enrolled{p.revenue_pct != null ? ` · ${p.revenue_pct}%` : ''}</div>
            </>
          ) : <div style={{ height: size }} />}
        </div>
      ))}
    </div>
  );
}

function PaceCard({ company }) {
  const p = company.pace;
  const big = { fontFamily: DISPLAY_FONT, fontSize: 'clamp(22px,3vw,56px)', lineHeight: 1.05 };
  const small = { fontFamily: BODY_FONT, color: MUTED, fontSize: 'clamp(13px,1.38vw,23px)' };
  return (
    <div style={{ flex: 0.9, minWidth: 0, background: '#1f1f1f', border: '1px solid #2c2c2c', borderRadius: 28, padding: '1.8vh 1.4vw', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 4 }}>
      <div style={{ ...small, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase' }}>Month pace</div>
      {p ? (
        <>
          <div style={big}><span style={{ color: LEMON }}>{p.days_left}</span> <span style={{ fontSize: '0.5em' }}>days left</span></div>
          {company.revenue_target > 0 && (
            <div style={{ fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(15px,1.68vw,29px)', color: p.on_track ? '#22c55e' : '#f59e0b' }}>
              {p.on_track ? '✓ On track' : '⚠ Behind pace'} · need {inr(p.needed_per_day)}/day
            </div>
          )}
          <div style={small}>On course for {inr(p.projected)}</div>
          <Bar pct={p.elapsed_pct} height={6} color="#525252" />
          <div style={{ ...small, fontSize: 'clamp(12px,1.08vw,18px)' }}>{p.elapsed_pct}% of the month gone</div>
        </>
      ) : <div style={small}>Month complete</div>}
    </div>
  );
}

export function SalesSlide({ data, photo, vh }) {
  const { company, people, recent } = data;
  const rest = people.slice(3, 3 + Math.max(0, Math.min(3, Math.floor((vh - 900) / 100))));
  return (
    <div style={{ ...col, height: '100%' }}>
      <div style={row}>
        <Kpi tone="lemon" label="Company revenue" value={company.revenue} money target={company.revenue_target} pct={company.revenue_pct} sub={company.derived ? 'Target = sum of everyone' : undefined} />
        <Kpi tone="lavender" label="Enrollments" value={company.enrolled} target={company.enrollment_target} pct={company.enrollment_pct} />
        <PaceCard company={company} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,2.1fr) minmax(0,1fr)', gap: '1.6vw', flex: 1, minHeight: 0 }}>
        <Panel title="Leaderboard" style={{ flex: 1 }}>
          {people.length === 0 && <div style={{ color: MUTED, fontSize: 22 }}>No team members yet</div>}
          {people.length > 0 && <Podium people={people} photo={photo} />}
          {rest.map((p) => (
            <div key={p.name} style={{ display: 'grid', gridTemplateColumns: '2.4vw 4.2vh minmax(0,1.2fr) minmax(0,2fr)', alignItems: 'center', gap: 14, padding: '0.7vh 0', borderTop: '1px solid #2c2c2c' }}>
              <div style={{ fontFamily: DISPLAY_FONT, color: MUTED, fontSize: 'clamp(16px,1.8vw,31px)', textAlign: 'center' }}>{p.rank}</div>
              <SalesAvatar name={p.name} src={photo(p)} size={36} ring={LAVENDER} ringWidth={2} style={{ width: '4.2vh', height: '4.2vh' }} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(16px,1.8vw,31px)', ...ellipsis }}>{p.name}</div>
                <div style={{ color: MUTED, fontSize: 'clamp(13px,1.14vw,19px)' }}>{p.enrolled} enrolled{p.enrollment_target ? ` / ${p.enrollment_target}` : ''}</div>
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 'clamp(15px,1.56vw,26px)', marginBottom: 4 }}>
                  {fmt(p.revenue)}{p.revenue_target ? <span style={{ color: MUTED, fontWeight: 500 }}> / {fmt(p.revenue_target)} · <b style={{ color: barColor(p.revenue_pct) }}>{p.revenue_pct}%</b></span> : null}
                </div>
                <Bar pct={p.revenue_pct} height={9} />
              </div>
            </div>
          ))}
        </Panel>
        <Panel title="Latest enrollments">
          {recent.length === 0 && <div style={{ color: MUTED, fontSize: 20 }}>No enrollments yet</div>}
          {recent.slice(0, 5).map((r, i) => (
            <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '1.1vh 0', borderTop: i ? '1px solid #2c2c2c' : 'none', animation: `slideUp .6s ${i * 0.08}s both` }}>
              <SalesAvatar name={r.counselor} src={photo({ user_id: r.counselor_id, avatar_v: r.avatar_v })} size={44} ring={i === 0 ? LEMON : LAVENDER} style={{ width: '5.2vh', height: '5.2vh' }} />
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontWeight: 700, fontSize: 'clamp(16px,1.8vw,30px)' }}>
                  <span style={ellipsis}>🎓 {r.student}</span>
                  <span style={{ color: LEMON, fontFamily: DISPLAY_FONT }}>{fmt(r.amount)}</span>
                </div>
                <div style={{ color: MUTED, fontSize: 'clamp(13px,1.14vw,19px)', ...ellipsis }}>{r.course} · {r.counselor} · {dayjs(r.at).format('DD MMM')}</div>
              </div>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}

// ── Teams ───────────────────────────────────────────────────────────────────
export function TeamsSlide({ data, photo }) {
  const { teams, company } = data;
  if (!teams.length) return <Empty>Teams appear here once team leaders have people reporting to them.</Empty>;
  const cols = teams.length > 4 ? 3 : teams.length > 1 ? 2 : 1;
  return (
    <div style={{ ...col, height: '100%' }}>
      <Panel style={{ padding: '1.4vh 1.5vw' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.4vw' }}>
          <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'clamp(16px,2vw,34px)', color: LEMON, whiteSpace: 'nowrap' }}>COMPANY</div>
          <div style={{ flex: 1 }}><Bar pct={company.revenue_pct} height={18} color={LEMON} /></div>
          <div style={{ fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(15px,1.8vw,31px)', whiteSpace: 'nowrap' }}>
            {fmt(company.revenue)}{company.revenue_target ? ` / ${fmt(company.revenue_target)} · ${company.revenue_pct}%` : ''}
          </div>
        </div>
      </Panel>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))`, gap: '1.4vw', flex: 1, minHeight: 0, gridAutoRows: 'minmax(0, 1fr)' }}>
        {teams.slice(0, 6).map((t, i) => (
          <Panel key={t.name} style={{ animation: `slideUp .6s ${i * 0.1}s both`, justifyContent: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: '1vh' }}>
              <SalesAvatar name={t.name} src={photo(t)} size={64} ring={i === 0 ? LEMON : LAVENDER} glow={i === 0} style={{ width: teams.length > 3 ? '6vh' : '8vh', height: teams.length > 3 ? '6vh' : '8vh' }} />
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'clamp(15px,1.8vw,32px)', ...ellipsis }}>{i === 0 && t.revenue > 0 ? '👑 ' : ''}Team {t.name}</div>
                <div style={{ color: MUTED, fontSize: 'clamp(13px,1.32vw,22px)' }}>{t.members} people · {t.enrolled} enrolled</div>
              </div>
              {t.revenue_pct != null && <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'clamp(22px,3.4vw,60px)', color: barColor(t.revenue_pct) }}>{t.revenue_pct}%</div>}
            </div>
            <div style={{ fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(15px,1.68vw,29px)', marginBottom: 4 }}>
              {fmt(t.revenue)}{t.revenue_target ? <span style={{ color: MUTED, fontWeight: 500 }}> / {fmt(t.revenue_target)}</span> : <span style={{ color: MUTED, fontWeight: 500 }}> · no target</span>}
            </div>
            <Bar pct={t.revenue_pct} height={12} />
            {t.enrollment_target > 0 && (
              <div style={{ marginTop: '1vh' }}>
                <div style={{ color: MUTED, fontSize: 'clamp(13px,1.26vw,20px)', marginBottom: 4 }}>{t.enrolled} of {t.enrollment_target} enrollments · {t.enrollment_pct}%</div>
                <Bar pct={t.enrollment_pct} height={8} color={LAVENDER} />
              </div>
            )}
          </Panel>
        ))}
      </div>
    </div>
  );
}

// ── Call report / activity ──────────────────────────────────────────────────
export function ActivitySlide({ data, photo, vh }) {
  const { today, week, people, active_today: active } = data;
  const rows = Math.min(8, Math.max(3, Math.floor((vh - 330) / 95)));
  const max = Math.max(1, ...people.map((p) => p.total));
  return (
    <div style={{ ...col, height: '100%' }}>
      <div style={row}>
        <Kpi tone="lemon" label="Calls today" value={today.calls} sub="logged in the CRM" />
        <Kpi tone="lavender" label="Follow-up updates today" value={today.updates} sub="notes & status updates" />
        <Kpi tone="dark" label="Active today" value={active} sub="people who logged work" />
        <Kpi tone="dark" label="This week" value={week.calls + week.updates} sub={`${week.calls} calls · ${week.updates} updates`} />
      </div>
      <Panel title="Who is working the leads today" style={{ flex: 1 }}>
        {people.length === 0 && <Empty>No activity logged yet today.</Empty>}
        {people.slice(0, rows).map((p, i) => (
          <div key={p.name} style={{ display: 'grid', gridTemplateColumns: '2.2vw 4.4vh minmax(0,1fr) minmax(0,3fr) 7vw', alignItems: 'center', gap: 12, padding: '0.7vh 0', borderTop: i ? '1px solid #2c2c2c' : 'none', animation: `slideUp .5s ${i * 0.06}s both` }}>
            <div style={{ fontFamily: DISPLAY_FONT, color: MUTED, fontSize: 'clamp(15px,1.68vw,29px)', textAlign: 'center' }}>{p.rank}</div>
            <SalesAvatar name={p.name} src={photo(p)} size={36} ring={i === 0 ? LEMON : LAVENDER} ringWidth={2} style={{ width: '4.4vh', height: '4.4vh' }} />
            <div style={{ fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(15px,1.68vw,29px)', ...ellipsis }}>{p.name}</div>
            <div style={{ display: 'flex', height: 14, borderRadius: 99, overflow: 'hidden', background: '#2a2a2a' }}>
              <div style={{ width: `${(p.calls / max) * 100}%`, background: LEMON, transition: 'width 1.2s' }} title="calls" />
              <div style={{ width: `${(p.updates / max) * 100}%`, background: LAVENDER, transition: 'width 1.2s' }} title="updates" />
            </div>
            <div style={{ textAlign: 'right', fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(14px,1.56vw,26px)' }}>
              {p.total}<span style={{ color: MUTED, fontWeight: 500, fontSize: '0.8em' }}> · wk {p.week_total}</span>
            </div>
          </div>
        ))}
        <div style={{ display: 'flex', gap: 18, marginTop: 'auto', paddingTop: '1vh', color: MUTED, fontFamily: BODY_FONT, fontSize: 'clamp(13px,1.26vw,20px)' }}>
          <span><b style={{ color: LEMON }}>■</b> calls</span><span><b style={{ color: LAVENDER }}>■</b> follow-up updates</span>
        </div>
      </Panel>
    </div>
  );
}

// ── Analytics ───────────────────────────────────────────────────────────────
function TrendChart({ trend }) {
  const maxIn = Math.max(1, ...trend.map((t) => t.leads_in));
  const maxEn = Math.max(1, ...trend.map((t) => t.enrolled));
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1.4vw', flex: 1, minHeight: 0, paddingTop: '1vh' }}>
      {trend.map((t, i) => (
        <div key={t.month} style={{ flex: 1, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', alignItems: 'center', minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: '85%', width: '100%', justifyContent: 'center' }}>
            <div title="leads in" style={{ width: '38%', height: `${(t.leads_in / maxIn) * 100}%`, minHeight: 3, background: LAVENDER, borderRadius: '8px 8px 0 0', animation: `grow .9s ${i * 0.08}s both`, transformOrigin: 'bottom' }} />
            <div title="enrolled" style={{ width: '38%', height: `${(t.enrolled / maxEn) * 100}%`, minHeight: 3, background: LEMON, borderRadius: '8px 8px 0 0', animation: `grow .9s ${i * 0.08 + 0.05}s both`, transformOrigin: 'bottom' }} />
          </div>
          <div style={{ fontFamily: BODY_FONT, color: i === trend.length - 1 ? LEMON : MUTED, fontWeight: 700, fontSize: 'clamp(12px,1.2vw,19px)', marginTop: 4 }}>{dayjs(`${t.month}-01`).format('MMM')}</div>
          <div style={{ fontFamily: BODY_FONT, color: '#fff', fontSize: 'clamp(12px,1.14vw,18px)' }}>{t.enrolled}</div>
        </div>
      ))}
    </div>
  );
}

export function AnalyticsSlide({ data }) {
  const g = data.growth || {};
  return (
    <div style={{ ...col, height: '100%' }}>
      <div style={row}>
        <Kpi tone="lemon" label="Leads in" value={data.leads_in} chip={g.leads_in} sub="new this month" />
        <Kpi tone="lavender" label="Enrolled" value={data.enrolled} chip={g.enrolled} sub="students closed" />
        <Kpi tone="dark" label="Revenue" value={data.revenue} money chip={g.revenue} sub="booked fees" />
        <Kpi tone="dark" label="Conversion" value={data.conversion} sub="enrolled ÷ leads in (%)" />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.5fr) minmax(0,1fr) minmax(0,1fr)', gap: '1.4vw', flex: 1, minHeight: 0 }}>
        <Panel title="Last 6 months · leads vs enrolled">
          <TrendChart trend={data.trend} />
          <div style={{ display: 'flex', gap: 18, color: MUTED, fontFamily: BODY_FONT, fontSize: 'clamp(12px,1.2vw,19px)', paddingTop: 4 }}>
            <span><b style={{ color: LAVENDER }}>■</b> leads in</span><span><b style={{ color: LEMON }}>■</b> enrolled</span>
          </div>
        </Panel>
        <Panel title="Top courses">
          {data.top_courses.length === 0 ? <Empty>No sales yet</Empty> : <RankedBars items={data.top_courses} color={LEMON} />}
        </Panel>
        <Panel title="Top countries · sources">
          <RankedBars items={data.top_countries.slice(0, 3)} color={LAVENDER} />
          <div style={{ height: 1, background: '#2c2c2c', margin: '0.6vh 0 1.2vh' }} />
          <RankedBars items={data.top_sources.slice(0, 3)} color="#7c4dcc" />
        </Panel>
      </div>
    </div>
  );
}

// ── Performance ─────────────────────────────────────────────────────────────
const HIGHLIGHT = {
  top_earner: { icon: '💰', title: 'Top earner', fmt: (h) => fmt(h.value) },
  most_enrollments: { icon: '🎓', title: 'Most enrollments', fmt: (h) => `${h.value} students` },
  biggest_deal: { icon: '💎', title: 'Biggest deal', fmt: (h) => fmt(h.value) },
  best_conversion: { icon: '🎯', title: 'Best conversion', fmt: (h) => `${h.value}%` },
  most_improved: { icon: '🚀', title: 'Most improved', fmt: (h) => `+${fmt(h.value)}` },
};

export function PerformanceSlide({ data, photo }) {
  const { highlights, anniversaries } = data;
  const compact = highlights.length > 3;
  return (
    <div style={{ ...col, height: '100%' }}>
      {highlights.length === 0 ? <Panel style={{ flex: 1 }}><Empty>Highlights appear once the first sale of the month closes.</Empty></Panel> : (
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(3, highlights.length)}, minmax(0,1fr))`, gap: '1.4vw', flex: 1, minHeight: 0, gridAutoRows: 'minmax(0, 1fr)' }}>
          {highlights.map((h, i) => {
            const meta = HIGHLIGHT[h.key] || { icon: '⭐', title: h.key, fmt: (x) => x.value };
            const first = i === 0;
            return (
              <div key={h.key} style={{ background: first ? LEMON : i % 2 ? LAVENDER : '#1f1f1f', color: first ? INK : '#fff', border: first || i % 2 ? 'none' : '1px solid #2c2c2c', borderRadius: 28, padding: compact ? '1vh 1vw' : '2vh 1.5vw', overflow: 'hidden', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', minWidth: 0, minHeight: 0, animation: `popIn .7s ${i * 0.12}s both` }}>
                <div style={{ fontFamily: BODY_FONT, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', fontSize: 'clamp(13px,1.32vw,23px)', opacity: 0.85, marginBottom: compact ? '0.4vh' : '1vh' }}>{meta.icon} {meta.title}</div>
                <SalesAvatar name={h.name} src={photo(h)} size={90} ring={first ? INK : LEMON} glow style={{ width: compact ? '8vh' : '11vh', height: compact ? '8vh' : '11vh' }} />
                <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'clamp(16px,2.2vw,38px)', marginTop: '1vh', maxWidth: '100%', ...ellipsis }}>{h.name}</div>
                <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'clamp(20px,2.8vw,50px)', color: first ? INK : LEMON }}>{meta.fmt(h)}</div>
                {h.detail && <div style={{ fontFamily: BODY_FONT, opacity: 0.8, fontSize: 'clamp(13px,1.32vw,22px)', maxWidth: '100%', ...ellipsis }}>{h.detail}</div>}
              </div>
            );
          })}
        </div>
      )}
      {anniversaries.length > 0 && (
        <Panel title="Work anniversaries" style={{ flex: '0 0 auto', padding: '1.2vh 1.5vw' }}>
          <div style={{ display: 'flex', gap: '2vw', flexWrap: 'wrap' }}>
            {anniversaries.slice(0, 4).map((a) => (
              <div key={a.name} style={{ display: 'flex', alignItems: 'center', gap: 12, animation: 'floatY 3s ease-in-out infinite' }}>
                <SalesAvatar name={a.name} src={photo(a)} size={48} ring={LAVENDER} style={{ width: '5.4vh', height: '5.4vh' }} />
                <div style={{ fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(15px,1.68vw,29px)' }}>
                  🎂 {a.name}
                  <div style={{ color: LEMON, fontWeight: 500, fontSize: '0.8em' }}>{a.years} {a.years === 1 ? 'year' : 'years'} · {a.days === 0 ? 'today!' : a.days === 1 ? 'tomorrow' : dayjs(a.date).format('ddd D MMM')}</div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

// ── Attendance ──────────────────────────────────────────────────────────────
function Ring({ pct }) {
  const r = 90;
  const c = 2 * Math.PI * r;
  const shown = useCountUp(pct);
  return (
    <div style={{ position: 'relative', width: 'min(40vh, 28vw)', aspectRatio: '1' }}>
      <svg viewBox="0 0 220 220" style={{ width: '100%', height: '100%', transform: 'rotate(-90deg)' }}>
        <circle cx="110" cy="110" r={r} fill="none" stroke="#2a2a2a" strokeWidth="22" />
        <circle cx="110" cy="110" r={r} fill="none" stroke={LEMON} strokeWidth="22" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(100, pct) / 100)} style={{ transition: 'stroke-dashoffset 1.6s cubic-bezier(.2,.8,.2,1)', filter: `drop-shadow(0 0 10px ${LEMON}88)` }} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', fontFamily: DISPLAY_FONT, fontSize: 'clamp(30px,6vw,110px)', color: LEMON }}>{shown}%</div>
    </div>
  );
}

export function AttendanceSlide({ data, photo }) {
  const people = data.people || [];
  const cols = people.length > 18 ? 3 : people.length > 8 ? 2 : 1;
  const rows = Math.max(1, Math.ceil(people.length / cols));
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,2.2fr)', gap: '1.6vw', height: '100%' }}>
      <Panel style={{ alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
        <Ring pct={data.present_pct} />
        <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'clamp(20px,2.6vw,48px)', marginTop: '1.4vh' }}>
          <span style={{ color: LAVENDER }}>{data.present}</span> of {data.total} in today
        </div>
      </Panel>
      <Panel title="Everyone">
        {people.length === 0 && <Empty>No team members yet.</Empty>}
        <div style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))`, gridTemplateRows: `repeat(${rows}, minmax(0,1fr))`, gridAutoFlow: 'column', overflow: 'hidden', columnGap: '1.4vw' }}>
          {people.map((p, i) => (
            <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: 12, minHeight: 0, minWidth: 0, borderTop: i % rows ? '1px solid #2c2c2c' : 'none', opacity: p.present ? 1 : 0.5, animation: `slideUp .5s ${Math.min(i, 12) * 0.04}s both` }}>
              <SalesAvatar name={p.name} src={photo(p)} size={64} ring={p.present ? (i === 0 ? LEMON : LAVENDER) : '#444'} glow={p.present && i === 0} style={{ width: `min(${rows > 8 ? 4.2 : 6}vh, 100%)`, height: `min(${rows > 8 ? 4.2 : 6}vh, 100%)`, aspectRatio: '1', flex: '0 0 auto' }} />
              <div style={{ fontFamily: DISPLAY_FONT, flex: 1, minWidth: 0, fontSize: `clamp(14px,${rows > 8 ? 1.3 : 1.7}vw,32px)`, ...ellipsis }}>{p.name}</div>
              <div style={{ fontFamily: BODY_FONT, fontWeight: 700, flex: '0 0 auto', color: p.present ? LEMON : MUTED, fontSize: `clamp(13px,${rows > 8 ? 1.1 : 1.4}vw,26px)` }}>{p.present ? p.time : 'Not in yet'}</div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

// ── Pipeline ────────────────────────────────────────────────────────────────
export function PipelineSlide({ data }) {
  const max = Math.max(1, ...data.statuses.map((s) => s.count));
  return (
    <div style={{ ...col, height: '100%' }}>
      <div style={row}>
        <Kpi tone="lemon" label="New leads today" value={data.new_today} sub="came in since midnight" />
        <Kpi tone="lavender" label="New this week" value={data.new_week} sub="since Monday" />
        <Kpi tone="dark" label="Total leads" value={data.total} sub="in the CRM" />
      </div>
      <Panel title="Where the leads are" style={{ flex: 1 }}>
        {data.statuses.length === 0 && <Empty>No leads yet.</Empty>}
        {data.statuses.map((s, i) => (
          <div key={s.name} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,4fr) 8vw', alignItems: 'center', gap: 14, padding: '0.7vh 0', animation: `slideUp .5s ${i * 0.06}s both` }}>
            <div style={{ fontFamily: BODY_FONT, fontWeight: 700, fontSize: 'clamp(15px,1.68vw,29px)', ...ellipsis }}>{s.name}</div>
            <Bar pct={(s.count / max) * 100} height={16} color={s.name === 'Enrolled' ? LEMON : LAVENDER} />
            <div style={{ fontFamily: DISPLAY_FONT, textAlign: 'right', fontSize: 'clamp(14px,1.7vw,30px)' }}>{s.count.toLocaleString('en-IN')}</div>
          </div>
        ))}
      </Panel>
    </div>
  );
}
