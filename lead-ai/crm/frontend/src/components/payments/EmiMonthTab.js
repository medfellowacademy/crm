import React, { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Card, Row, Col, Statistic, DatePicker, Table, Tag, Button, Space, Typography, Segmented, Empty, Result, Progress, Tooltip,
} from 'antd';
import { CheckOutlined, CommentOutlined, DownloadOutlined } from '@ant-design/icons';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend,
} from 'recharts';
import dayjs from 'dayjs';
import { paymentsAPI } from '../../api/api';
import { fmt } from '../../utils/finance';
import PayEmiModal from './PayEmiModal';
import { CommentsModal } from './PaymentComments';

const { Text } = Typography;
const STATUS = { paid: { color: 'green', label: 'Paid' }, pending: { color: 'blue', label: 'Pending' }, overdue: { color: 'red', label: 'Overdue' } };

export default function EmiMonthTab({ onChanged }) {
  const queryClient = useQueryClient();
  const [month, setMonth] = useState(dayjs());
  const [status, setStatus] = useState('all');
  const [pay, setPay] = useState(null);
  const [comments, setComments] = useState(null);

  const monthStr = month.format('YYYY-MM');
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['payments-emis', monthStr],
    queryFn: () => paymentsAPI.emis({ month: monthStr }).then((r) => r.data),
  });

  const rows = useMemo(() => (data?.rows || []).filter((r) => status === 'all' || r.status === status), [data, status]);
  const trend = useMemo(
    () => (data?.trend || []).map((t) => ({ ...t, label: dayjs(t.month + '-01').format('MMM YY') })),
    [data]
  );
  const s = data?.summary || {};

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['payments-emis'] });
    onChanged?.();
  };

  const exportCsv = () => {
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const header = ['Lead ID', 'Name', 'Counselor', 'EMI', 'Due date', 'Scheduled', 'Received', 'Status', 'Paid on', 'Method', 'Last comment'];
    const body = rows.map((r) => [r.lead_id, r.name, r.counselor, `${r.emi_index + 1}/${r.emi_count}`, r.due_date,
      r.scheduled, r.received, STATUS[r.status].label, r.paid_date || '', r.method || '', r.last_comment?.note || ''].map(esc).join(','));
    const blob = new Blob(['﻿' + [header.map(esc).join(','), ...body].join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `emis-${monthStr}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  if (isError) {
    return <Result status="warning" title="Couldn't load EMIs" extra={<Button type="primary" onClick={() => refetch()}>Retry</Button>} />;
  }

  const columns = [
    { title: 'Lead', key: 'lead', render: (_, r) => (
      <div><div style={{ fontWeight: 600 }}>{r.name}</div><Text type="secondary" style={{ fontSize: 12 }}>{r.phone}</Text></div>
    ) },
    { title: 'Counselor', dataIndex: 'counselor' },
    { title: 'Instalment', key: 'emi', render: (_, r) => r.label || `EMI ${r.emi_index + 1}` },
    { title: 'Due', dataIndex: 'due_date', sorter: (a, b) => a.due_date.localeCompare(b.due_date), defaultSortOrder: 'ascend',
      render: (d) => dayjs(d).format('DD MMM YYYY') },
    { title: 'Scheduled EMI', dataIndex: 'scheduled', align: 'right', sorter: (a, b) => a.scheduled - b.scheduled, render: fmt },
    { title: 'Received', key: 'received', align: 'right', render: (_, r) => {
      if (r.status !== 'paid') return <Text type="secondary">—</Text>;
      const short = r.scheduled - r.received;
      return (
        <span>
          <Text strong style={{ color: '#389e0d' }}>{fmt(r.received)}</Text>
          {short > 0 && <Tooltip title={`${fmt(short)} less than scheduled`}><Tag color="orange" style={{ marginLeft: 6 }}>short</Tag></Tooltip>}
          {short < 0 && <Tooltip title={`${fmt(-short)} more than scheduled`}><Tag color="blue" style={{ marginLeft: 6 }}>extra</Tag></Tooltip>}
        </span>
      );
    } },
    { title: 'Status', dataIndex: 'status', render: (v) => <Tag color={STATUS[v].color}>{STATUS[v].label}</Tag> },
    { title: 'Paid on', key: 'paid', render: (_, r) => (r.paid_date
      ? <span>{dayjs(r.paid_date).format('DD MMM')}{r.method ? <Text type="secondary"> · {r.method}</Text> : null}</span>
      : <Text type="secondary">—</Text>) },
    { title: 'Comments', key: 'comments', width: 230, render: (_, r) => (
      <div style={{ fontSize: 12 }}>
        {r.last_comment ? <div title={r.last_comment.note} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 210 }}>{r.last_comment.note}</div> : <Text type="secondary">No comments</Text>}
        <Button size="small" type="link" icon={<CommentOutlined />} style={{ padding: 0 }}
          onClick={() => setComments({ leadId: r.lead_id, name: r.name, count: r.comment_count })}>
          {r.comment_count ? `View / add (${r.comment_count})` : 'Add comment'}
        </Button>
      </div>
    ) },
    { title: '', key: 'actions', render: (_, r) => (r.status === 'paid' ? null : (
      <Button size="small" type="primary" icon={<CheckOutlined />}
        onClick={() => setPay({ leadId: r.lead_id, index: r.emi_index, name: r.name, amount: r.scheduled, dueDate: r.due_date, label: r.label })}>
        Mark paid
      </Button>
    )) },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space wrap>
          <DatePicker picker="month" value={month} onChange={(v) => v && setMonth(v)} allowClear={false} />
          <Segmented value={status} onChange={setStatus}
            options={[{ label: 'All', value: 'all' }, { label: 'Paid', value: 'paid' }, { label: 'Pending', value: 'pending' }, { label: 'Overdue', value: 'overdue' }]} />
        </Space>
        <Button icon={<DownloadOutlined />} onClick={exportCsv} disabled={!rows.length}>Export CSV</Button>
      </Space>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}><Card loading={isLoading}><Statistic title={`EMIs due — ${month.format('MMM YYYY')}`} value={s.scheduled || 0} formatter={fmt} suffix={<Text type="secondary" style={{ fontSize: 13 }}>{s.count || 0} EMIs</Text>} /></Card></Col>
        <Col xs={12} md={6}><Card loading={isLoading}><Statistic title="Actually received" value={s.received || 0} formatter={fmt} valueStyle={{ color: '#389e0d' }} suffix={<Text type="secondary" style={{ fontSize: 13 }}>{s.paid_count || 0} paid</Text>} /></Card></Col>
        <Col xs={12} md={6}><Card loading={isLoading}>
          <Statistic title="Still to collect" value={s.outstanding || 0} formatter={fmt} valueStyle={{ color: s.overdue_count ? '#cf1322' : undefined }} />
          {s.overdue_count > 0 && <Text type="danger" style={{ fontSize: 12 }}>{s.overdue_count} overdue · {fmt(s.overdue_amount)}</Text>}
        </Card></Col>
        <Col xs={12} md={6}><Card loading={isLoading}>
          <Statistic title="Collection rate" value={s.collection_rate || 0} suffix="%" />
          <Progress percent={Math.min(100, s.collection_rate || 0)} showInfo={false} size="small" />
          {s.shortfall > 0 && <Text type="warning" style={{ fontSize: 12 }}>{fmt(s.shortfall)} short on paid EMIs</Text>}
        </Card></Col>
      </Row>

      <Card title="Scheduled EMI value vs actually received — by due month" style={{ marginBottom: 16 }}
        extra={<Text type="secondary" style={{ fontSize: 12 }}>click a month to open it</Text>}>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={trend} onClick={(e) => e?.activePayload?.[0] && setMonth(dayjs(e.activePayload[0].payload.month + '-01'))}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" fontSize={12} />
            <YAxis fontSize={12} tickFormatter={(v) => (v >= 100000 ? `${(v / 100000).toFixed(1)}L` : v)} />
            <RTooltip formatter={(v) => fmt(v)} />
            <Legend />
            <Bar dataKey="scheduled" name="Scheduled EMI" fill="#d6e4ff" radius={[4, 4, 0, 0]} cursor="pointer" />
            <Bar dataKey="received" name="Received" fill="#52c41a" radius={[4, 4, 0, 0]} cursor="pointer" />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <Card styles={{ body: { padding: 0 } }}>
        <Table
          loading={isLoading} size="middle" rowKey={(r) => `${r.lead_id}-${r.emi_index}`}
          dataSource={rows} columns={columns} scroll={{ x: 'max-content' }}
          pagination={{ pageSize: 15, hideOnSinglePage: true }}
          locale={{ emptyText: <Empty description={`No EMIs ${status === 'all' ? '' : status + ' '}in ${month.format('MMM YYYY')}`} /> }}
          summary={(pageData) => (pageData.length ? (
            <Table.Summary.Row>
              <Table.Summary.Cell index={0} colSpan={4}><Text strong>Total ({rows.length})</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={4} align="right"><Text strong>{fmt(rows.reduce((a, r) => a + r.scheduled, 0))}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={5} align="right"><Text strong style={{ color: '#389e0d' }}>{fmt(rows.reduce((a, r) => a + r.received, 0))}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={6} colSpan={4} />
            </Table.Summary.Row>
          ) : null)}
        />
      </Card>

      <PayEmiModal target={pay} onClose={() => setPay(null)} onDone={refresh} />
      <CommentsModal target={comments} onClose={() => { setComments(null); refresh(); }} />
    </div>
  );
}
