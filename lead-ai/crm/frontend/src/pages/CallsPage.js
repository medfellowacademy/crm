import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card, Table, Tag, Space, Typography, Segmented, DatePicker, Row, Col, Statistic,
  Button, Input, Modal, Alert, Popconfirm, message,
} from 'antd';
import { PhoneOutlined, CopyOutlined } from '@ant-design/icons';
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

export default function CallsPage() {
  const qc = useQueryClient();
  const [period, setPeriod] = useState('Today');
  const [custom, setCustom] = useState(null);
  const [label, setLabel] = useState('');
  const [pairing, setPairing] = useState(null);

  const [start, end] = rangeOf(period, custom);
  const params = { start: start.format('YYYY-MM-DD'), end: end.format('YYYY-MM-DD') };

  const summary = useQuery({
    queryKey: ['calls-summary', params.start, params.end],
    queryFn: () => callsAPI.summary(params).then((r) => r.data),
    placeholderData: (prev) => prev,
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

  const data = summary.data;
  const team = data?.team || {};
  const columns = [
    { title: 'Person', dataIndex: 'name', render: (v, r) => (
      <Space direction="vertical" size={0}>
        <Text strong>{v}</Text>
        {!r.phone_paired && <Text type="secondary" style={{ fontSize: 12 }}>No phone paired</Text>}
      </Space>) },
    { title: 'Calls made', dataIndex: 'made', sorter: (a, b) => a.made - b.made, defaultSortOrder: 'descend' },
    { title: 'Connected', dataIndex: 'connected', render: (v) => <Tag color="green">{v}</Tag> },
    { title: 'Not connected', dataIndex: 'not_connected', render: (v) => <Tag color="red">{v}</Tag> },
    { title: 'Connect %', dataIndex: 'connect_rate', render: (v) => `${v}%` },
    { title: 'Received', dataIndex: 'received' },
    { title: 'Missed', dataIndex: 'missed' },
    { title: 'Talk time', dataIndex: 'talk_seconds', render: mins, sorter: (a, b) => a.talk_seconds - b.talk_seconds },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space wrap>
          <Segmented options={PERIODS} value={period} onChange={setPeriod} />
          {period === 'Custom' && <DatePicker.RangePicker value={custom} onChange={setCustom} />}
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
          <Col xs={12} md={4}><Card><Statistic title="Received" value={team.received || 0} /></Card></Col>
          <Col xs={12} md={4}><Card><Statistic title="Talk time" value={mins(team.talk_seconds)} /></Card></Col>
        </Row>

        <Card title="Calls by person" size="small">
          <Table rowKey="email" size="small" loading={summary.isLoading} columns={columns}
            dataSource={data?.people || []} pagination={false} scroll={{ x: 700 }} />
          <Text type="secondary" style={{ fontSize: 12 }}>
            Counts come from each person's phone. Connected means the call was answered (talk time above zero).
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
                { title: 'Last sync', dataIndex: 'last_sync_at', render: (v) => (v ? dayjs(v).format('DD MMM, h:mm A') : <Tag>Never</Tag>) },
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
