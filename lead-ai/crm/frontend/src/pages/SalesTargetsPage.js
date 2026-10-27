import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card, Row, Col, DatePicker, Table, Button, Modal, InputNumber, Space, Tag, Tabs, Checkbox,
  Typography, Result, Alert, Input, Popconfirm, Tooltip, message,
} from 'antd';
import { EditOutlined, CopyOutlined, DesktopOutlined, LinkOutlined, CameraOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { targetsAPI } from '../api/api';
import { fmt } from '../utils/finance';
import { fileToAvatarDataUrl } from '../utils/imageResize';
import { AuthAvatar } from '../components/targets/SalesAvatar';
import {
  LEMON, CHARCOAL, LAVENDER, INK, DISPLAY_FONT, barColor, loadBrandFonts,
} from '../components/targets/salesTheme';

const { Text } = Typography;
const errText = (e, fallback) => e?.response?.data?.detail || fallback;

const lemonBtn = { background: LEMON, borderColor: LEMON, color: INK, fontWeight: 700 };

function Meter({ pct, dark }) {
  return (
    <div style={{ background: dark ? '#ffffff26' : '#00000014', borderRadius: 99, height: 12, overflow: 'hidden' }}>
      <div style={{ width: `${Math.min(100, pct || 0)}%`, height: '100%', borderRadius: 99, background: dark ? LEMON : INK, transition: 'width 1s ease' }} />
    </div>
  );
}

function Kpi({ tone, label, value, target, pct, money, derived }) {
  const lemon = tone === 'lemon';
  const fg = lemon ? INK : '#fff';
  return (
    <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 22, padding: '20px 24px', background: lemon ? LEMON : LAVENDER, color: fg, height: '100%' }}>
      <div style={{ position: 'absolute', right: -30, top: -30, width: 120, height: 120, borderRadius: '50%', border: `16px solid ${lemon ? '#00000014' : '#ffffff26'}` }} />
      <div style={{ fontWeight: 700, letterSpacing: 2, textTransform: 'uppercase', fontSize: 12, opacity: 0.8 }}>{label}</div>
      <div style={{ fontFamily: DISPLAY_FONT, fontSize: 38, lineHeight: 1.15 }}>{value}</div>
      {target ? (
        <>
          <div style={{ fontSize: 13, margin: '4px 0 8px' }}>
            of {money ? fmt(target) : target} {derived ? 'combined target (sum of everyone)' : 'company target'} · <b>{pct}%</b>{pct >= 100 ? ' 🔥' : ''}
          </div>
          <Meter pct={pct} dark={!lemon} />
        </>
      ) : <div style={{ fontSize: 13, opacity: 0.75 }}>No company target set — use “Set targets”</div>}
    </div>
  );
}

function PaceCard({ company }) {
  const p = company?.pace;
  return (
    <div style={{ borderRadius: 22, padding: '20px 24px', background: CHARCOAL, color: '#fff', height: '100%' }}>
      <div style={{ fontWeight: 700, letterSpacing: 2, textTransform: 'uppercase', fontSize: 12, opacity: 0.7 }}>Month pace</div>
      {p ? (
        <>
          <div style={{ fontFamily: DISPLAY_FONT, fontSize: 38, lineHeight: 1.15 }}><span style={{ color: LEMON }}>{p.days_left}</span> <span style={{ fontSize: 16 }}>days left</span></div>
          {company.revenue_target > 0 && (
            <div style={{ color: p.on_track ? '#22c55e' : '#f59e0b', fontWeight: 700 }}>
              {p.on_track ? '✓ On track' : '⚠ Behind pace'} · need {fmt(Math.round(p.needed_per_day))}/day
            </div>
          )}
          <div style={{ opacity: 0.7, fontSize: 13 }}>On course for {fmt(Math.round(p.projected))} · {p.elapsed_pct}% of the month gone</div>
        </>
      ) : <div style={{ opacity: 0.7, marginTop: 8 }}>Pace shows for the current month.</div>}
    </div>
  );
}

function Achievement({ done, target, pct, money }) {
  if (!target) return <Text type="secondary">{money ? fmt(done) : done} · no target</Text>;
  return (
    <div style={{ minWidth: 170 }}>
      <div style={{ fontSize: 13 }}>
        <b>{money ? fmt(done) : done}</b> <Text type="secondary">of {money ? fmt(target) : target} · {pct}%</Text>
      </div>
      <div style={{ background: '#eee', borderRadius: 99, height: 8, overflow: 'hidden', marginTop: 4 }}>
        <div style={{ width: `${Math.min(100, pct || 0)}%`, height: '100%', background: pct >= 100 ? '#d4c800' : barColor(pct), borderRadius: 99 }} />
      </div>
    </div>
  );
}

// Click the avatar to upload a photo — your own, or anyone's if you can manage targets.
function PhotoPicker({ person, editable, onChanged }) {
  const input = useRef(null);
  const [busy, setBusy] = useState(false);
  const avatar = <AuthAvatar userId={person.user_id} version={person.avatar_v} name={person.name} size={44} ring={person.rank === 1 ? LEMON : LAVENDER} />;
  if (!editable || !person.user_id) return avatar;

  const pick = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setBusy(true);
    try {
      await targetsAPI.setAvatar(person.user_id, await fileToAvatarDataUrl(file));
      message.success('Photo updated');
      onChanged();
    } catch (err) {
      message.error(errText(err, err?.message || 'Could not upload the photo'));
    } finally { setBusy(false); }
  };
  const remove = async () => {
    try { await targetsAPI.removeAvatar(person.user_id); message.success('Photo removed'); onChanged(); } catch (err) { message.error(errText(err, 'Could not remove the photo')); }
  };

  return (
    <Space size={4}>
      <Tooltip title={person.avatar_v ? 'Change photo' : 'Add photo'}>
        <span style={{ position: 'relative', cursor: 'pointer', display: 'inline-block', opacity: busy ? 0.5 : 1 }} onClick={() => input.current?.click()}>
          {avatar}
          <CameraOutlined style={{ position: 'absolute', right: -4, bottom: -4, background: LEMON, color: INK, borderRadius: '50%', padding: 4, fontSize: 11 }} />
        </span>
      </Tooltip>
      {person.avatar_v > 0 && <Popconfirm title="Remove this photo?" onConfirm={remove}><Button size="small" type="text" danger>×</Button></Popconfirm>}
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={pick} />
    </Space>
  );
}

const money = (x) => ({
  min: 0, max: 10000000000, step: 50000, style: { width: '100%' }, value: x,
  formatter: (v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ','), parser: (v) => v.replace(/,/g, ''),
});

// Super Admin / Manager: set the company, each team's and each person's monthly target.
function TargetsModal({ month, open, onClose, onSaved }) {
  const [company, setCompany] = useState({ revenue_target: 0, enrollment_target: 0 });
  const [teams, setTeams] = useState([]);
  const [people, setPeople] = useState([]);
  const { data, isLoading } = useQuery({
    queryKey: ['targets-edit', month], enabled: open,
    queryFn: () => targetsAPI.get(month).then((r) => r.data), staleTime: 0,
  });
  useEffect(() => {
    if (!data) return;
    setCompany({ ...data.company });
    setTeams(data.teams.map((t) => ({ ...t })));
    setPeople(data.people.map((p) => ({ ...p })));
  }, [data]);

  const save = useMutation({
    mutationFn: () => targetsAPI.save(month, [
      { scope: 'company', subject: '', revenue_target: Number(company.revenue_target) || 0, enrollment_target: Number(company.enrollment_target) || 0 },
      ...teams.map((t) => ({ scope: 'team', subject: t.subject, revenue_target: Number(t.revenue_target) || 0, enrollment_target: Number(t.enrollment_target) || 0 })),
      ...people.map((p) => ({ scope: 'person', subject: p.subject, revenue_target: Number(p.revenue_target) || 0, enrollment_target: Number(p.enrollment_target) || 0 })),
    ]),
    onSuccess: () => { message.success('Targets saved'); onSaved(); onClose(); },
    onError: (e) => message.error(errText(e, 'Could not save targets')),
  });

  const copyPrevious = async () => {
    try {
      const prev = dayjs(`${month}-01`).subtract(1, 'month').format('YYYY-MM');
      const d = (await targetsAPI.get(prev)).data;
      const pick = (rows, from) => rows.map((r) => {
        const f = from.find((x) => x.subject === r.subject);
        return { ...r, revenue_target: f?.revenue_target || 0, enrollment_target: f?.enrollment_target || 0 };
      });
      setCompany({ ...d.company });
      setTeams((cur) => pick(cur, d.teams));
      setPeople((cur) => pick(cur, d.people));
      message.info(`Copied from ${dayjs(`${prev}-01`).format('MMM YYYY')} — review, then save`);
    } catch (e) { message.error(errText(e, 'Could not load last month')); }
  };

  const setRow = (setter) => (i, key, v) => setter((cur) => cur.map((r, j) => (j === i ? { ...r, [key]: v } : r)));
  const sum = (rows, k) => rows.reduce((a, r) => a + (Number(r[k]) || 0), 0);
  const cols = (setter) => [
    { title: 'Name', dataIndex: 'subject', render: (v, r) => <span>{v}{r.members ? <Text type="secondary"> · {r.members} people</Text> : null}</span> },
    { title: 'Revenue target (₹)', dataIndex: 'revenue_target', width: 190, render: (v, _, i) => (
      <InputNumber {...money(v)} onChange={(x) => setRow(setter)(i, 'revenue_target', x)} />
    ) },
    { title: 'Enrollments', dataIndex: 'enrollment_target', width: 120, render: (v, _, i) => (
      <InputNumber min={0} max={100000} precision={0} style={{ width: '100%' }} value={v} onChange={(x) => setRow(setter)(i, 'enrollment_target', x)} />
    ) },
  ];
  const peopleRev = sum(people, 'revenue_target');
  const hint = (label, rows) => (
    <Text type="secondary" style={{ display: 'block', margin: '8px 0' }}>
      {label} add up to <b>{fmt(sum(rows, 'revenue_target'))}</b> · {sum(rows, 'enrollment_target')} enrollments
      {Number(company.revenue_target) > 0 ? ` (company target ${fmt(company.revenue_target)})` : ''}
    </Text>
  );

  return (
    <Modal
      open={open} onCancel={onClose} width={720} destroyOnClose
      title={<span style={{ fontFamily: DISPLAY_FONT }}>Targets — {dayjs(`${month}-01`).format('MMMM YYYY')}</span>}
      okText="Save targets" onOk={() => save.mutate()} confirmLoading={save.isPending}
      okButtonProps={{ style: lemonBtn }}
      footer={(_, { OkBtn, CancelBtn }) => (
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Button icon={<CopyOutlined />} onClick={copyPrevious}>Copy last month</Button>
          <Space><CancelBtn /><OkBtn /></Space>
        </Space>
      )}
    >
      <Text type="secondary">Leave both at 0 to clear a target. A sale counts in the month the student was enrolled.</Text>
      <Tabs
        style={{ marginTop: 8 }}
        items={[
          {
            key: 'company', label: 'Company',
            children: (
              <div>
                <Text type="secondary">The overall goal for the whole company this month. It is its own number — it doesn't have to equal the sum of the teams.</Text>
                <Row gutter={16} style={{ marginTop: 12 }}>
                  <Col span={14}><div style={{ marginBottom: 4 }}>Revenue target (₹)</div><InputNumber {...money(company.revenue_target)} onChange={(x) => setCompany((c) => ({ ...c, revenue_target: x }))} /></Col>
                  <Col span={10}><div style={{ marginBottom: 4 }}>Enrollments</div><InputNumber min={0} max={100000} precision={0} style={{ width: '100%' }} value={company.enrollment_target} onChange={(x) => setCompany((c) => ({ ...c, enrollment_target: x }))} /></Col>
                </Row>
                {hint('Counselor targets', people)}
              </div>
            ),
          },
          {
            key: 'teams', label: `Teams (${teams.length})`,
            children: teams.length ? (
              <>
                <Text type="secondary">A team is a Manager or Team Leader plus everyone who reports to them.</Text>
                <Table style={{ marginTop: 8 }} size="small" loading={isLoading} pagination={false} rowKey="subject" dataSource={teams} columns={cols(setTeams)} />
                {hint('Team targets', teams)}
              </>
            ) : <Alert type="info" showIcon message="No teams yet" description="Teams appear once a Manager or Team Leader has people reporting to them (set “Reports to” on the Users page)." />,
          },
          {
            key: 'people', label: `Counselors (${people.length})`,
            children: (
              <>
                <Table size="small" loading={isLoading} pagination={false} rowKey="subject" dataSource={people} columns={cols(setPeople)} scroll={{ y: 340 }} />
                {hint('Counselor targets', people)}
                {Number(company.revenue_target) > 0 && peopleRev > Number(company.revenue_target) && (
                  <Alert type="warning" showIcon style={{ marginTop: 6 }} message="Counselor targets add up to more than the company target." />
                )}
              </>
            ),
          },
        ]}
      />
    </Modal>
  );
}

// Super Admin / Manager: the secret link the office TV opens, and what it shows.
function ScreenLink() {
  const queryClient = useQueryClient();
  const { data, isError, error } = useQuery({
    queryKey: ['targets-screen'], queryFn: () => targetsAPI.screen().then((r) => r.data), staleTime: 0, retry: false,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['targets-screen'] });
  const create = useMutation({
    mutationFn: () => targetsAPI.newScreen(), onSuccess: () => { message.success('New link created — the old one no longer works'); refresh(); },
    onError: (e) => message.error(errText(e, 'Could not create the link')),
  });
  const revoke = useMutation({
    mutationFn: () => targetsAPI.revokeScreen(), onSuccess: () => { message.success('Link disabled'); refresh(); },
    onError: (e) => message.error(errText(e, 'Could not disable the link')),
  });
  const [slides, setSlides] = useState(null);
  const [seconds, setSeconds] = useState(15);
  useEffect(() => {
    if (data?.settings) { setSlides(data.settings.slides); setSeconds(data.settings.seconds); }
  }, [data]);
  const saveSettings = useMutation({
    mutationFn: () => targetsAPI.saveScreenSettings({ slides, seconds: Number(seconds) || 15 }),
    onSuccess: () => { message.success('TV slides saved — the screen picks them up within a few seconds'); refresh(); },
    onError: (e) => message.error(errText(e, 'Could not save the slide settings')),
  });
  const url = data?.token ? `${window.location.origin}/display/${data.token}` : '';
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); message.success('Link copied'); } catch { message.error('Copy failed — select the link and copy it'); }
  };
  const available = data?.available_slides || [];
  const dirty = data?.settings && (JSON.stringify(slides) !== JSON.stringify(data.settings.slides) || Number(seconds) !== data.settings.seconds);

  return (
    <div style={{ marginTop: 16, borderRadius: 22, background: CHARCOAL, color: '#fff', padding: '20px 24px' }}>
      <div style={{ fontFamily: DISPLAY_FONT, fontSize: 20, color: LEMON, marginBottom: 6 }}><DesktopOutlined /> OFFICE TV SCREEN</div>
      {isError ? (
        <Alert type="warning" showIcon message={errText(error, 'Office screen is not available yet')} />
      ) : (
        <>
          <div style={{ color: '#bdbdbd' }}>
            Open this link in the browser on the office TV and press F11. Anyone with the link can see the sales numbers, so share it only
            inside the office. Creating a new link instantly disables the old one.
          </div>
          <div style={{ marginTop: 12 }}>
            {url ? (
              <Space.Compact style={{ width: '100%', maxWidth: 720 }}>
                <Input readOnly value={url} onFocus={(e) => e.target.select()} prefix={<LinkOutlined />} />
                <Button icon={<CopyOutlined />} onClick={copy}>Copy</Button>
                <Button style={lemonBtn} onClick={() => window.open(url, '_blank', 'noopener')}>Open</Button>
              </Space.Compact>
            ) : <Tag>No active link</Tag>}
          </div>
          <Space style={{ marginTop: 12 }}>
            {url ? (
              <Popconfirm title="Replace the link? The TV will stop working until you open the new one." onConfirm={() => create.mutate()}>
                <Button loading={create.isPending}>Create new link</Button>
              </Popconfirm>
            ) : <Button style={lemonBtn} loading={create.isPending} onClick={() => create.mutate()}>Create link</Button>}
            {url && <Popconfirm title="Disable the TV link?" onConfirm={() => revoke.mutate()}><Button danger loading={revoke.isPending}>Disable</Button></Popconfirm>}
          </Space>

          {url && slides && (
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid #333' }}>
              <div style={{ fontFamily: DISPLAY_FONT, color: LEMON, marginBottom: 8 }}>WHAT THE TV SHOWS</div>
              <div style={{ color: '#bdbdbd', marginBottom: 8 }}>The screen rotates through the slides you switch on. Arrow keys on the TV browser step through them.</div>
              <Checkbox.Group value={slides} onChange={(v) => setSlides(available.map((a) => a.key).filter((k) => v.includes(k)))}>
                <Space wrap size={[16, 8]}>
                  {available.map((a) => <Checkbox key={a.key} value={a.key}><span style={{ color: '#fff' }}>{a.title}</span></Checkbox>)}
                </Space>
              </Checkbox.Group>
              <div style={{ marginTop: 12 }}>
                <Space>
                  <span style={{ color: '#bdbdbd' }}>Seconds per slide</span>
                  <InputNumber min={data.min_seconds} max={data.max_seconds} value={seconds} onChange={setSeconds} />
                  <Button style={lemonBtn} disabled={!dirty || !slides.length} loading={saveSettings.isPending} onClick={() => saveSettings.mutate()}>Save TV settings</Button>
                </Space>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function SalesTargetsPage() {
  const queryClient = useQueryClient();
  const [month, setMonth] = useState(dayjs());
  const [editing, setEditing] = useState(false);
  const monthStr = month.format('YYYY-MM');
  useEffect(() => { loadBrandFonts(); }, []);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['targets-progress', monthStr],
    queryFn: () => targetsAPI.progress(monthStr).then((r) => r.data),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['targets-progress'] });

  const company = data?.company || {};
  const people = useMemo(() => data?.people || [], [data]);
  const teams = useMemo(() => data?.teams || [], [data]);
  const me = (data?.me || '').toLowerCase();

  if (isError) {
    return <Result status="warning" title="Couldn't load sales targets" subTitle={errText(error, '')} extra={<Button type="primary" onClick={() => refetch()}>Retry</Button>} />;
  }

  return (
    <div>
      <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 24, background: CHARCOAL, padding: '22px 28px', marginBottom: 16 }}>
        <div style={{ position: 'absolute', right: -60, top: -80, width: 260, height: 260, borderRadius: '50%', background: LAVENDER, opacity: 0.5, filter: 'blur(40px)' }} />
        <Space wrap style={{ width: '100%', justifyContent: 'space-between', position: 'relative' }}>
          <div>
            <div style={{ fontFamily: DISPLAY_FONT, fontSize: 'clamp(26px,4vw,46px)', lineHeight: 1 }}>
              <span style={{ color: LEMON }}>SALES </span>
              <span style={{ color: 'transparent', WebkitTextStroke: `2px ${LAVENDER}` }}>TARGETS</span>
            </div>
            <div style={{ color: '#bdbdbd', marginTop: 4 }}>{month.format('MMMM YYYY')} · company, team and counselor targets</div>
          </div>
          <Space wrap>
            <DatePicker picker="month" value={month} onChange={(v) => v && setMonth(v)} allowClear={false} />
            {data?.can_manage && <Button style={lemonBtn} icon={<EditOutlined />} onClick={() => setEditing(true)}>Set targets</Button>}
          </Space>
        </Space>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={9}><Kpi tone="lemon" label="Company revenue" value={isLoading ? '…' : fmt(company.revenue || 0)} target={company.revenue_target} pct={company.revenue_pct} money derived={company.derived} /></Col>
        <Col xs={24} md={9}><Kpi tone="lavender" label="Company enrollments" value={isLoading ? '…' : company.enrolled || 0} target={company.enrollment_target} pct={company.enrollment_pct} derived={company.derived} /></Col>
        <Col xs={24} md={6}><PaceCard company={company} /></Col>
      </Row>
      <div style={{ color: '#8c8c8c', fontSize: 12, margin: '6px 4px 0' }}>Revenue = booked fee of students enrolled this month.</div>

      {teams.length > 0 && (
        <Card title={<span style={{ fontFamily: DISPLAY_FONT }}>TEAMS</span>} style={{ marginTop: 16, borderRadius: 22 }}>
          <Row gutter={[16, 16]}>
            {teams.map((t, i) => (
              <Col xs={24} md={12} xl={8} key={t.name}>
                <div style={{ border: '1px solid #f0f0f0', borderRadius: 16, padding: 16, height: '100%' }}>
                  <Space align="center">
                    <AuthAvatar userId={t.user_id} version={t.avatar_v} name={t.name} size={40} ring={i === 0 && t.revenue > 0 ? LEMON : LAVENDER} />
                    <div><b>Team {t.name}</b><div style={{ color: '#8c8c8c', fontSize: 12 }}>{t.members} people · {t.enrolled} enrolled</div></div>
                  </Space>
                  <div style={{ marginTop: 12 }}><Achievement done={t.revenue} target={t.revenue_target} pct={t.revenue_pct} money /></div>
                  {t.enrollment_target > 0 && <div style={{ marginTop: 8 }}><Achievement done={t.enrolled} target={t.enrollment_target} pct={t.enrollment_pct} /></div>}
                </div>
              </Col>
            ))}
          </Row>
        </Card>
      )}

      <Card title={<span style={{ fontFamily: DISPLAY_FONT }}>LEADERBOARD</span>} style={{ marginTop: 16, borderRadius: 22 }} styles={{ body: { padding: 0 } }}>
        <Table
          loading={isLoading} size="middle" pagination={false} rowKey="name" dataSource={people} scroll={{ x: 'max-content' }}
          rowClassName={(r) => (me && r.name.toLowerCase() === me ? 'ant-table-row-selected' : '')}
          locale={{ emptyText: 'No team members yet' }}
          columns={[
            { title: '#', dataIndex: 'rank', width: 56, render: (v, r) => (v <= 3 && r.revenue > 0 ? ['👑', '🥈', '🥉'][v - 1] : v) },
            { title: '', key: 'photo', width: 90, render: (_, r) => (
              <PhotoPicker person={r} editable={data?.can_manage || String(r.user_id) === String(data?.me_id)} onChanged={refresh} />
            ) },
            { title: 'Name', dataIndex: 'name', render: (v) => <b>{v}</b> },
            { title: 'Revenue', key: 'rev', render: (_, r) => <Achievement done={r.revenue} target={r.revenue_target} pct={r.revenue_pct} money /> },
            { title: 'Enrollments', key: 'enr', render: (_, r) => <Achievement done={r.enrolled} target={r.enrollment_target} pct={r.enrollment_pct} /> },
          ]}
        />
      </Card>

      <Card title={<span style={{ fontFamily: DISPLAY_FONT }}>LATEST ENROLLMENTS</span>} style={{ marginTop: 16, borderRadius: 22 }} styles={{ body: { padding: 0 } }}>
        <Table
          loading={isLoading} size="small" pagination={false} rowKey="id" dataSource={data?.recent || []}
          locale={{ emptyText: 'No enrollments yet' }}
          columns={[
            { title: 'Student', dataIndex: 'student' },
            { title: 'Counselor', dataIndex: 'counselor', render: (v, r) => (
              <Space><AuthAvatar userId={r.counselor_id} version={r.avatar_v} name={v} size={26} ringWidth={2} ring={LAVENDER} />{v}</Space>
            ) },
            { title: 'Course', dataIndex: 'course', ellipsis: true },
            { title: 'Fee', dataIndex: 'amount', align: 'right', render: fmt },
            { title: 'Enrolled', dataIndex: 'at', render: (v) => dayjs(v).format('DD MMM YYYY') },
          ]}
        />
      </Card>

      {data?.can_manage && <ScreenLink />}
      {data?.can_manage && <TargetsModal month={monthStr} open={editing} onClose={() => setEditing(false)} onSaved={refresh} />}
    </div>
  );
}
