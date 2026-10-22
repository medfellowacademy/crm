import React, { useMemo } from 'react';
import { Card, Row, Col, Table, Tag, Typography, Alert, Statistic, Empty, Progress } from 'antd';
import {
  ResponsiveContainer, ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend,
  BarChart, Cell,
} from 'recharts';
import dayjs from 'dayjs';
import { fmt } from '../../utils/finance';

const { Text } = Typography;
const AGING_COLORS = ['#faad14', '#fa8c16', '#f5222d', '#a8071a'];

export default function CollectionsTab({ data }) {
  const collections = useMemo(
    () => (data?.collections || []).map((r) => ({ ...r, label: dayjs(r.month + '-01').format('MMM YY') })),
    [data]
  );
  const thisMonth = collections[collections.length - 1];
  const dq = data?.data_quality || {};
  const aging = data?.aging || [];
  const hasAging = aging.some((a) => a.count > 0);

  return (
    <div>
      {dq.approx_dated_collections > 0 && (
        <Alert
          type="info" showIcon style={{ marginBottom: 16 }}
          message="Some collection dates are estimated"
          description={`${dq.approx_dated_collections} collection(s) have no recorded payment date, so they are placed on the enrollment date (registration) or EMI due date (EMIs). Use "Mark paid" on EMIs from now on to record the real date and method.`}
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}><Card><Statistic title={`Collected — ${thisMonth ? dayjs(thisMonth.month + '-01').format('MMM YYYY') : ''}`} value={thisMonth?.collected || 0} formatter={fmt} valueStyle={{ color: '#389e0d' }} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="Expected this month" value={thisMonth?.expected || 0} formatter={fmt} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="Total overdue" value={data?.overdue_total || 0} formatter={fmt} valueStyle={{ color: (data?.overdue_total || 0) > 0 ? '#cf1322' : undefined }} /></Card></Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="Collection rate" value={data?.summary?.collection_rate || 0} suffix="%" />
            <Progress percent={Math.min(100, data?.summary?.collection_rate || 0)} showInfo={false} size="small" />
          </Card>
        </Col>
      </Row>

      <Card title="Collected vs expected — last 12 months" style={{ marginBottom: 16 }}>
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={collections}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" fontSize={12} />
            <YAxis fontSize={12} tickFormatter={(v) => (v >= 100000 ? `${(v / 100000).toFixed(1)}L` : v)} />
            <RTooltip formatter={(v) => fmt(v)} />
            <Legend />
            <Bar dataKey="expected" name="Expected" fill="#d6e4ff" radius={[4, 4, 0, 0]} />
            <Bar dataKey="collected" name="Collected" fill="#52c41a" radius={[4, 4, 0, 0]} />
          </ComposedChart>
        </ResponsiveContainer>
      </Card>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={10}>
          <Card title="Overdue by age">
            {hasAging ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={aging}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="bucket" fontSize={12} />
                  <YAxis fontSize={12} tickFormatter={(v) => (v >= 100000 ? `${(v / 100000).toFixed(1)}L` : v)} />
                  <RTooltip formatter={(v, n, p) => [`${fmt(v)} (${p.payload.count} EMIs)`, 'Overdue']} />
                  <Bar dataKey="amount" radius={[4, 4, 0, 0]}>
                    {aging.map((_, i) => <Cell key={i} fill={AGING_COLORS[i]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <Empty description="Nothing overdue" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          </Card>
        </Col>
        <Col xs={24} md={14}>
          <Card title={`Due in the next 30 days (${data?.due_soon?.length || 0})`} styles={{ body: { padding: 0 } }}>
            <Table
              size="small" rowKey={(r) => `${r.lead_id}-${r.emi_index}`} pagination={{ pageSize: 6, hideOnSinglePage: true }}
              dataSource={data?.due_soon || []}
              locale={{ emptyText: <Empty description="No EMIs due soon" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
              columns={[
                { title: 'Lead', dataIndex: 'name' },
                { title: 'Counselor', dataIndex: 'counselor', responsive: ['md'] },
                { title: 'Due', dataIndex: 'due_date', render: (d, r) => (
                  <span>{dayjs(d).format('DD MMM')} <Tag color={r.days_until <= 3 ? 'orange' : 'default'}>{r.days_until === 0 ? 'today' : `in ${r.days_until}d`}</Tag></span>
                ) },
                { title: 'Amount', dataIndex: 'amount', align: 'right', render: fmt },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Card title="Collections by counselor" styles={{ body: { padding: 0 } }}>
        <Table
          size="small" rowKey="counselor" pagination={false} dataSource={data?.by_counselor || []}
          scroll={{ x: 'max-content' }}
          columns={[
            { title: 'Counselor', dataIndex: 'counselor' },
            { title: 'Enrolled', dataIndex: 'enrolled', align: 'center' },
            { title: 'Total fees', dataIndex: 'total', align: 'right', render: fmt },
            { title: 'Collected', dataIndex: 'collected', align: 'right', render: (v) => <Text strong style={{ color: '#389e0d' }}>{fmt(v)}</Text> },
            { title: 'Balance', dataIndex: 'balance', align: 'right', render: fmt },
            { title: 'Overdue', dataIndex: 'overdue', align: 'right', render: (v) => (v > 0 ? <Text type="danger">{fmt(v)}</Text> : '—') },
            { title: 'Collection rate', dataIndex: 'collection_rate', render: (v) => <Progress percent={Math.min(100, v)} size="small" style={{ minWidth: 110 }} /> },
          ]}
        />
      </Card>
    </div>
  );
}
