import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card, Table, Tag, Space, Typography, Segmented, DatePicker, Row, Col, Statistic,
  Button, Input, Modal, Alert, Popconfirm, Switch, Tooltip, message,
} from 'antd';
import { PhoneOutlined, CopyOutlined, DownloadOutlined, LinkOutlined } from '@ant-design/icons';
import {
  ResponsiveContainer, ComposedChart, BarChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend,
} from 'recharts';
import dayjs from 'dayjs';
import { callsAPI } from '../api/api';

const { Text, Paragraph } = Typography;
const PERIODS = ['Today', 'Yesterday', 'This Week', 'This Month', 'Custom'];

function rangeOf(period, custom) {
  const now = dayjs();
  if (period === 'Today') return [now, now];
  if (period === 'Yesterday') return [now.subtract(1, 'day'), now.subtract(1, 'day')];
  if (period === 'This Week') return [now.startOf('week'), now];
  if (period === 'This Month') return [now.startOf('month'), now];
  if (custom?.[0] && custom?.[1]) return [custom[0], custom[1]];
  return [now, now];
}

const mins = (sec) => {
  const s = Number(sec || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
};
const clock = (sec) => {
  const s = Number(sec || 0);
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
};

// A phone that has not reported for a while is the usual reason a person's count looks low.
function SyncBadge({ row }) {
  if (!row.phone_paired) return <Tag>No phone</Tag>;
  if (!row.last_sync_at) return <Tag color="orange">Never synced</Tag>;
  const hrs = dayjs().diff(dayjs(row.last_sync_at), 'hour', true);
  const text = dayjs(row.last_sync_at).format('DD/MM, h:mm A');
  return <Tooltip title={`Last sync ${text}`}><Tag color={hrs > 6 ? 'red' : 'green'}>{hrs > 6 ? `Stale · ${text}` : 'Live'}</Tag></Tooltip>;
}

function downloadCsv(people, team, range) {
  const head = ['Name', 'Email', 'Calls made', 'Connected', 'Not connected', 'Connect %', 'Received', 'Missed',
    'Calls to leads', 'Unique leads', 'Talk time (min)', 'Avg talk (sec)'];
  const line = (r) => [r.name, r.email, r.made, r.connected, r.not_connected, r.connect_rate, r.received, r.missed,
    r.lead_calls, r.unique_leads, Math.round(r.talk_seconds / 60), r.avg_talk_seconds];
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const rows = [head, ...people.map(line), line({ name: 'TEAM', email: '', ...team })];
  const blob = new Blob([rows.map((r) => r.map(esc).join(',')).join('\n')], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `calls_${range}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function CallsPage() {
  const qc = useQueryClient();
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem('user') || '{}'); } catch (e) { stored = {}; }
  const isAdmin = stored.role === 'Super Admin';
  const [period, setPeriod] = useState('Today');
  const [custom, setCustom] = useState(null);
  const [leadsOnly, setLeadsOnly] = useState(false);
  const [person, setPerson] = useState(null);
  const [label, setLabel] = useState('');
  const [pairing, setPairing] = useState(null);

  const [start, end] = rangeOf(period, custom);
  const params = { start: start.format('YYYY-MM-DD'), end: end.format('YYYY-MM-DD'), leads_only: leadsOnly, ...(person ? { user_email: person.email } : {}) };

  const summary = useQuery({
    queryKey: ['calls-summary', params],
    queryFn: () => callsAPI.summary(params).then((r) => r.data),
    placeholderData: (prev) => prev,
    refetchInterval: 60 * 1000,
  });
  const devices = useQuery({ queryKey: ['calls-devices'], queryFn: () => callsAPI.devices().then((r) => r.data) });

  const pair = useMutation({
    mutationFn: () => callsAPI.pair(label).then((r) => r.data),
    onSuccess: (d) => { setPairing(d); setLabel(''); qc.invalidateQueries({ queryKey: ['calls-devices'] }); },
    onError: () => message.error('Could not create a pairing code. Please retry.'),
  });
  const revoke = useMutation({
    mutationFn: (id) => callsAPI.revoke(id),
    onSuccess: () => { message.success('Phone removed'); qc.invalidateQueries({ queryKey: ['calls-devices'] }); },
  });
  const rematch = useMutation({
    mutationFn: () => callsAPI.rematch().then((r) => r.data),
    onSuccess: (d) => { message.success(`${d.linked} earlier calls linked to leads`); qc.invalidateQueries({ queryKey: ['calls-summary'] }); },
    onError: () => message.error('Could not link calls. Please retry.'),
  });

  const data = summary.data;
  const team = data?.team || {};
  const people = data?.people || [];
  const multiDay = (data?.trend || []).length > 1;
  const columns = [
    { title: 'Person', dataIndex: 'name', render: (v, r) => (
      <Space direction="vertical" size={0}>
        {isAdmin && !person ? <a onClick={() => setPerson(r)}>{v}</a> : <Text strong>{v}</Text>}
        <SyncBadge row={r} />
      </Space>) },
    { title: 'Made', dataIndex: 'made', sorter: (a, b) => a.made - b.made, defaultSortOrder: 'descend' },
    { title: 'Connected', dataIndex: 'connected', render: (v) => <Tag color="green">{v}</Tag>, sorter: (a, b) => a.connected - b.connected },
    { title: 'Not connected', dataIndex: 'not_connected', render: (v) => <Tag color="red">{v}</Tag> },
    { title: 'Connect %', dataIndex: 'connect_rate', render: (v) => `${v}%`, sorter: (a, b) => a.connect_rate - b.connect_rate },
    { title: <Tooltip title="Different leads dialled">Leads called</Tooltip>, dataIndex: 'unique_leads', sorter: (a, b) => a.unique_leads - b.unique_leads },
    { title: <Tooltip title="Calls to numbers that are not CRM leads (personal or unknown)">Other calls</Tooltip>,
      render: (_, r) => r.made - r.lead_calls },
    { title: 'Received', dataIndex: 'received' },
    { title: 'Missed', dataIndex: 'missed' },
    { title: 'Talk time', dataIndex: 'talk_seconds', render: mins, sorter: (a, b) => a.talk_seconds - b.talk_seconds },
    { title: 'Avg call', dataIndex: 'avg_talk_seconds', render: clock },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space wrap>
          <Segmented options={PERIODS} value={period} onChange={setPeriod} />
          {period === 'Custom' && <DatePicker.RangePicker value={custom} onChange={setCustom} />}
          <Tooltip title="Count only calls to numbers that belong to a CRM lead">
            <span><Switch checked={leadsOnly} onChange={setLeadsOnly} /> <Text>Lead calls only</Text></span>
          </Tooltip>
          {person && <Tag closable color="blue" onClose={() => setPerson(null)}>{person.name}</Tag>}
          <Button icon={<DownloadOutlined />} disabled={!people.length}
            onClick={() => downloadCsv(people, team, `${params.start}_${params.end}`)}>Export CSV</Button>
          {isAdmin && (
            <Tooltip title="Link calls saved before a lead existed to that lead">
              <Button icon={<LinkOutlined />} loading={rematch.isPending} onClick={() => rematch.mutate()}>Link calls to leads</Button>
            </Tooltip>)}
        </Space>

        {summary.isError && (
          <Alert type="error" showIcon message="Call counts could not be loaded"
            action={<Button size="small" onClick={() => summary.refetch()}>Retry</Button>} />
        )}

        <Row gutter={[12, 12]}>
          <Col xs={12} md={4}><Card><Statistic title="Calls made" value={team.made || 0} /></Card></Col>
          <Col xs={12} md={4}><Card><Statistic title="Connected" value={team.connected || 0} valueStyle={{ color: '#389e0d' }} /></Card></Col>
          <Col xs={12} md={4}><Card><Statistic title="Not connected" value={team.not_connected || 0} valueStyle={{ color: '#cf1322' }} /></Card></Col>
          <Col xs={12} md={4}><Card><Statistic title="Connect rate" value={team.connect_rate || 0} suffix="%" /></Card></Col>
          <Col xs={12} md={4}><Card><Statistic title="Leads called" value={team.unique_leads || 0} /></Card></Col>
          <Col xs={12} md={4}><Card><Statistic title="Talk time" value={mins(team.talk_seconds)} /></Card></Col>
        </Row>

        <Row gutter={[12, 12]}>
          {multiDay && (
            <Col xs={24} lg={12}>
              <Card size="small" title="Calls per day">
                <ResponsiveContainer width="100%" height={220}>
                  <ComposedChart data={data.trend}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tickFormatter={(d) => dayjs(d).format('DD/MM')} />
                    <YAxis allowDecimals={false} />
                    <RTooltip labelFormatter={(d) => dayjs(d).format('ddd, DD/MM')} />
                    <Legend />
                    <Bar dataKey="made" name="Made" fill="#91caff" />
                    <Line dataKey="connected" name="Connected" stroke="#389e0d" strokeWidth={2} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </Card>
            </Col>)}
          <Col xs={24} lg={multiDay ? 12 : 24}>
            <Card size="small" title="When calls are made (IST hour)">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={(data?.hourly || []).filter((h) => h.hour >= 7 && h.hour <= 22)}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" tickFormatter={(h) => `${h % 12 || 12}${h < 12 ? 'a' : 'p'}`} />
                  <YAxis allowDecimals={false} />
                  <RTooltip labelFormatter={(h) => `${h % 12 || 12}:00 ${h < 12 ? 'AM' : 'PM'}`} />
                  <Legend />
                  <Bar dataKey="made" name="Made" fill="#91caff" />
                  <Bar dataKey="connected" name="Connected" fill="#52c41a" />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </Col>
        </Row>

        <Card title="Calls by person" size="small">
          <Table rowKey="email" size="small" loading={summary.isLoading} columns={columns}
            dataSource={people} pagination={false} scroll={{ x: 900 }} />
          <Text type="secondary" style={{ fontSize: 12 }}>
            Connected means the call was answered for at least {data?.min_connected_sec ?? 5} seconds. Counts come from each person's phone and refresh every few minutes.
            A red "Stale" tag means that phone has not reported for over 6 hours.
          </Text>
        </Card>

        <Card title="My phone" size="small">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              Install the MedFellow Calls app on your phone, then pair it with a one-time code. Only the call
              type, number, time and duration are sent. Never audio.
            </Paragraph>
            <Space wrap>
              <Input placeholder="Phone name (e.g. Redmi Note)" value={label} onChange={(e) => setLabel(e.target.value)}
                maxLength={60} style={{ width: 240 }} />
              <Button type="primary" icon={<PhoneOutlined />} loading={pair.isPending} onClick={() => pair.mutate()}>
                Pair a phone
              </Button>
            </Space>
            <Table rowKey="id" size="small" loading={devices.isLoading} pagination={false}
              dataSource={(devices.data || []).filter((d) => !d.revoked)}
              locale={{ emptyText: 'No phone paired yet' }}
              columns={[
                { title: 'Phone', dataIndex: 'label', render: (v) => v || 'Phone' },
                { title: 'Owner', dataIndex: 'user_email' },
                { title: 'Last sync', dataIndex: 'last_sync_at', render: (v) => (v ? dayjs(v).format('DD/MM, h:mm A') : <Tag>Never</Tag>) },
                { title: '', render: (_, r) => (
                  <Popconfirm title="Remove this phone? It will stop syncing." onConfirm={() => revoke.mutate(r.id)}>
                    <Button size="small" danger>Remove</Button>
                  </Popconfirm>) },
              ]} />
          </Space>
        </Card>
      </Space>

      <Modal open={!!pairing} title="Pairing code" onCancel={() => setPairing(null)} footer={
        <Button type="primary" onClick={() => setPairing(null)}>Done</Button>}>
        <Paragraph>Type this code into the app. It is shown only once.</Paragraph>
        <Input.TextArea readOnly autoSize value={pairing?.token || ''} />
        <Button style={{ marginTop: 8 }} icon={<CopyOutlined />}
          onClick={() => { navigator.clipboard?.writeText(pairing?.token || ''); message.success('Copied'); }}>
          Copy
        </Button>
      </Modal>
    </div>
  );
}
