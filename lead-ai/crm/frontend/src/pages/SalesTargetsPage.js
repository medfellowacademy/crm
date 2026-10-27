import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card, Row, Col, Statistic, DatePicker, Table, Progress, Button, Modal, InputNumber, Space, Tag,
  Typography, Result, Alert, Input, Popconfirm, message,
} from 'antd';
import { TrophyOutlined, EditOutlined, CopyOutlined, DesktopOutlined, LinkOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { targetsAPI } from '../api/api';
import { fmt } from '../utils/finance';

const { Text, Title } = Typography;

const barColor = (pct) => (pct == null ? '#d9d9d9' : pct >= 100 ? '#16a34a' : pct >= 60 ? '#1677ff' : '#faad14');
const errText = (e, fallback) => e?.response?.data?.detail || fallback;

function Achievement({ done, target, pct, money }) {
  if (!target) return <Text type="secondary">{money ? fmt(done) : done} · no target</Text>;
  return (
    <div style={{ minWidth: 170 }}>
      <div style={{ fontSize: 13 }}>
        <b>{money ? fmt(done) : done}</b> <Text type="secondary">of {money ? fmt(target) : target} · {pct}%</Text>
      </div>
      <Progress percent={Math.min(100, pct || 0)} showInfo={false} size="small" strokeColor={barColor(pct)} />
    </div>
  );
}

// Super Admin / Manager: set each person's monthly target.
function TargetsModal({ month, open, onClose, onSaved }) {
  const [rows, setRows] = useState([]);
  const { data, isLoading } = useQuery({
    queryKey: ['targets-edit', month], enabled: open,
    queryFn: () => targetsAPI.get(month).then((r) => r.data), staleTime: 0,
  });
  useEffect(() => { if (data) setRows(data.people.map((p) => ({ ...p }))); }, [data]);

  const save = useMutation({
    mutationFn: () => targetsAPI.save(month, rows.map((r) => ({
      counselor: r.counselor, revenue_target: Number(r.revenue_target) || 0, enrollment_target: Number(r.enrollment_target) || 0,
    }))),
    onSuccess: () => { message.success('Targets saved'); onSaved(); onClose(); },
    onError: (e) => message.error(errText(e, 'Could not save targets')),
  });

  const copyPrevious = async () => {
    try {
      const prev = dayjs(`${month}-01`).subtract(1, 'month').format('YYYY-MM');
      const res = await targetsAPI.get(prev);
      const byName = Object.fromEntries(res.data.people.map((p) => [p.counselor, p]));
      setRows((cur) => cur.map((r) => ({ ...r, revenue_target: byName[r.counselor]?.revenue_target || 0, enrollment_target: byName[r.counselor]?.enrollment_target || 0 })));
      message.info(`Copied from ${dayjs(`${prev}-01`).format('MMM YYYY')} — review, then save`);
    } catch (e) { message.error(errText(e, 'Could not load last month')); }
  };

  const set = (i, key, v) => setRows((cur) => cur.map((r, j) => (j === i ? { ...r, [key]: v } : r)));
  const totalRev = rows.reduce((a, r) => a + (Number(r.revenue_target) || 0), 0);
  const totalEnr = rows.reduce((a, r) => a + (Number(r.enrollment_target) || 0), 0);

  return (
    <Modal
      open={open} onCancel={onClose} width={680} destroyOnClose
      title={`Targets — ${dayjs(`${month}-01`).format('MMMM YYYY')}`}
      okText="Save targets" onOk={() => save.mutate()} confirmLoading={save.isPending}
      footer={(_, { OkBtn, CancelBtn }) => (
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Button icon={<CopyOutlined />} onClick={copyPrevious}>Copy last month</Button>
          <Space><CancelBtn /><OkBtn /></Space>
        </Space>
      )}
    >
      <Text type="secondary">Leave both at 0 to clear someone's target. A sale counts in the month the student was enrolled.</Text>
      <Table
        style={{ marginTop: 12 }} size="small" loading={isLoading} pagination={false} rowKey="counselor" dataSource={rows}
        scroll={{ y: 380 }}
        columns={[
          { title: 'Team member', dataIndex: 'counselor' },
          { title: 'Revenue target (₹)', dataIndex: 'revenue_target', width: 190, render: (v, _, i) => (
            <InputNumber min={0} max={10000000000} step={50000} style={{ width: '100%' }} value={v}
              formatter={(x) => `${x}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} parser={(x) => x.replace(/,/g, '')}
              onChange={(x) => set(i, 'revenue_target', x)} />
          ) },
          { title: 'Enrollments', dataIndex: 'enrollment_target', width: 120, render: (v, _, i) => (
            <InputNumber min={0} max={100000} precision={0} style={{ width: '100%' }} value={v} onChange={(x) => set(i, 'enrollment_target', x)} />
          ) },
        ]}
        summary={() => (
          <Table.Summary.Row>
            <Table.Summary.Cell index={0}><Text strong>Team total</Text></Table.Summary.Cell>
            <Table.Summary.Cell index={1}><Text strong>{fmt(totalRev)}</Text></Table.Summary.Cell>
            <Table.Summary.Cell index={2}><Text strong>{totalEnr}</Text></Table.Summary.Cell>
          </Table.Summary.Row>
        )}
      />
    </Modal>
  );
}

// Super Admin / Manager: the secret link the office TV opens.
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
  const url = data?.token ? `${window.location.origin}/display/${data.token}` : '';
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); message.success('Link copied'); } catch { message.error('Copy failed — select the link and copy it'); }
  };

  return (
    <Card title={<span><DesktopOutlined /> Office TV screen</span>} style={{ marginTop: 16 }}>
      {isError ? (
        <Alert type="warning" showIcon message={errText(error, 'Office screen is not available yet')} />
      ) : (
        <>
          <Text type="secondary">
            Open this link in the browser on the office TV and press F11. Anyone with the link can see the sales numbers, so share it only
            inside the office. Creating a new link instantly disables the old one.
          </Text>
          <div style={{ marginTop: 12 }}>
            {url ? (
              <Space.Compact style={{ width: '100%', maxWidth: 720 }}>
                <Input readOnly value={url} onFocus={(e) => e.target.select()} prefix={<LinkOutlined />} />
                <Button icon={<CopyOutlined />} onClick={copy}>Copy</Button>
                <Button type="primary" onClick={() => window.open(url, '_blank', 'noopener')}>Open</Button>
              </Space.Compact>
            ) : <Tag>No active link</Tag>}
          </div>
          <Space style={{ marginTop: 12 }}>
            {url ? (
              <Popconfirm title="Replace the link? The TV will stop working until you open the new one." onConfirm={() => create.mutate()}>
                <Button loading={create.isPending}>Create new link</Button>
              </Popconfirm>
            ) : <Button type="primary" loading={create.isPending} onClick={() => create.mutate()}>Create link</Button>}
            {url && <Popconfirm title="Disable the TV link?" onConfirm={() => revoke.mutate()}><Button danger loading={revoke.isPending}>Disable</Button></Popconfirm>}
          </Space>
        </>
      )}
    </Card>
  );
}

export default function SalesTargetsPage() {
  const queryClient = useQueryClient();
  const [month, setMonth] = useState(dayjs());
  const [editing, setEditing] = useState(false);
  const monthStr = month.format('YYYY-MM');

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['targets-progress', monthStr],
    queryFn: () => targetsAPI.progress(monthStr).then((r) => r.data),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['targets-progress'] });

  const team = data?.team || {};
  const people = useMemo(() => data?.people || [], [data]);
  const me = (data?.me || '').toLowerCase();

  if (isError) {
    return <Result status="warning" title="Couldn't load sales targets" subTitle={errText(error, '')} extra={<Button type="primary" onClick={() => refetch()}>Retry</Button>} />;
  }

  return (
    <div>
      <Space wrap style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}><TrophyOutlined /> Sales Targets</Title>
        <Space wrap>
          <DatePicker picker="month" value={month} onChange={(v) => v && setMonth(v)} allowClear={false} />
          {data?.can_manage && <Button type="primary" icon={<EditOutlined />} onClick={() => setEditing(true)}>Set targets</Button>}
        </Space>
      </Space>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card loading={isLoading}>
            <Statistic title="Team revenue (booked fees of students enrolled this month)" value={team.revenue || 0} formatter={fmt} />
            <Achievement done={team.revenue || 0} target={team.revenue_target} pct={team.revenue_pct} money />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card loading={isLoading}>
            <Statistic title="Team enrollments" value={team.enrolled || 0} />
            <Achievement done={team.enrolled || 0} target={team.enrollment_target} pct={team.enrollment_pct} />
          </Card>
        </Col>
      </Row>

      <Card title="Leaderboard" style={{ marginTop: 16 }} styles={{ body: { padding: 0 } }}>
        <Table
          loading={isLoading} size="middle" pagination={false} rowKey="name" dataSource={people} scroll={{ x: 'max-content' }}
          rowClassName={(r) => (me && r.name.toLowerCase() === me ? 'ant-table-row-selected' : '')}
          locale={{ emptyText: 'No team members yet' }}
          columns={[
            { title: '#', dataIndex: 'rank', width: 56, render: (v) => (v <= 3 ? ['🥇', '🥈', '🥉'][v - 1] : v) },
            { title: 'Name', dataIndex: 'name', render: (v) => <b>{v}</b> },
            { title: 'Revenue', key: 'rev', render: (_, r) => <Achievement done={r.revenue} target={r.revenue_target} pct={r.revenue_pct} money /> },
            { title: 'Enrollments', key: 'enr', render: (_, r) => <Achievement done={r.enrolled} target={r.enrollment_target} pct={r.enrollment_pct} /> },
          ]}
        />
      </Card>

      <Card title="Latest enrollments" style={{ marginTop: 16 }} styles={{ body: { padding: 0 } }}>
        <Table
          loading={isLoading} size="small" pagination={false} rowKey="id" dataSource={data?.recent || []}
          locale={{ emptyText: 'No enrollments yet' }}
          columns={[
            { title: 'Student', dataIndex: 'student' },
            { title: 'Counselor', dataIndex: 'counselor' },
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
