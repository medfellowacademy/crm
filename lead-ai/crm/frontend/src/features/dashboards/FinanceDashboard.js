import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Card, Row, Col, Table, Tag, Space, Typography, Button, DatePicker, Empty } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { DollarSign, TrendingUp, AlertTriangle, FileText } from 'lucide-react';
import dayjs from 'dayjs';
import isBetween from 'dayjs/plugin/isBetween';
import { leadsAPI, analyticsAPI } from '../../api/api';
import { fmt, financeFor } from '../../utils/finance';

dayjs.extend(isBetween);

const { Text, Title } = Typography;

const KpiCard = ({ title, value, sub, icon: Icon, color }) => (
  <Card style={{ borderRadius: 12 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
      <div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>{title}</div>
        <div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div>
        {sub && <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>{sub}</div>}
      </div>
      <div style={{
        width: 44, height: 44, borderRadius: 10, background: `${color}18`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon size={22} color={color} />
      </div>
    </div>
  </Card>
);

const FinanceDashboard = () => {
  const navigate = useNavigate();
  const [dateRange, setDateRange] = useState([null, null]);

  // Same source of truth as the Payments page: fetch every enrolled lead
  // and derive all numbers via financeFor(), so this dashboard's totals can
  // never disagree with what Finance sees when they open Payments. The date
  // filter scopes by enrollment date (updated_at), not creation date — a
  // lead created months ago that just enrolled this week should count as
  // "this week's" revenue, matching how Payments filters.
  const { data: leadsResponse } = useQuery({
    queryKey: ['finance-dashboard-leads'],
    queryFn: () => leadsAPI.getAll({ status: 'Enrolled', limit: 10000 }).then(r => r.data),
  });
  const allLeads = leadsResponse?.leads || (Array.isArray(leadsResponse) ? leadsResponse : []);
  const leads = allLeads.filter(l => {
    if (!dateRange[0] || !dateRange[1]) return true;
    const d = dayjs(l.updated_at || l.created_at);
    return d.isBetween(dateRange[0], dateRange[1], 'day', '[]');
  });

  const dateParams = dateRange[0] && dateRange[1] ? {
    created_from: dateRange[0].startOf('day').toISOString(),
    created_to: dateRange[1].endOf('day').toISOString(),
  } : {};
  const { data: revenueByCountry = [] } = useQuery({
    queryKey: ['finance-revenue-by-country', dateParams.created_from, dateParams.created_to],
    queryFn: () => analyticsAPI.getRevenueByCountry(dateParams).then(res => res.data || []),
  });

  const finances = leads.map(financeFor);
  const totalRevenue   = finances.reduce((s, f) => s + f.total,     0);
  const totalCollected = finances.reduce((s, f) => s + f.collected, 0);
  const totalBalance   = finances.reduce((s, f) => s + f.balance,   0);
  const totalOverdue   = finances.reduce((s, f) => s + f.overdueAmount, 0);

  const recentLeads = [...leads]
    .sort((a, b) => dayjs(b.updated_at || b.created_at).unix() - dayjs(a.updated_at || a.created_at).unix())
    .slice(0, 8);

  const columns = [
    { title: 'Name', dataIndex: 'full_name', key: 'full_name', render: t => <Text strong>{t}</Text> },
    { title: 'Course', dataIndex: 'course_interested', key: 'course', render: t => t ? <Tag color="blue">{t}</Tag> : '—' },
    {
      title: 'Revenue', key: 'revenue',
      render: (_, r) => <Text style={{ color: '#10b981', fontWeight: 600 }}>{fmt(financeFor(r).total)}</Text>,
    },
    {
      title: 'Balance', key: 'balance',
      render: (_, r) => {
        const bal = financeFor(r).balance;
        return bal > 0 ? <Text style={{ color: '#dc2626' }}>{fmt(bal)}</Text> : <Tag color="green">Cleared</Tag>;
      },
    },
    { title: 'Enrolled', dataIndex: 'updated_at', key: 'updated_at', render: d => d ? dayjs(d).format('DD MMM YYYY') : '—' },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Finance Overview</Title>
          <Text type="secondary">Revenue, collections, and outstanding balances across enrolled leads</Text>
        </div>
        <Space direction="vertical" size={2}>
          <Text type="secondary" style={{ fontSize: 12 }}>Filter by enrollment date</Text>
          <DatePicker.RangePicker value={dateRange} onChange={v => setDateRange(v || [null, null])} allowClear />
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard title="Total Revenue" value={fmt(totalRevenue)} icon={DollarSign} color="#10b981" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard title="Collected" value={fmt(totalCollected)} icon={TrendingUp} color="#3b82f6" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard title="Balance Pending" value={fmt(totalBalance)} icon={FileText} color="#f59e0b" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Overdue" value={fmt(totalOverdue)}
            sub={finances.filter(f => f.overdueAmount > 0).length > 0 ? `${finances.filter(f => f.overdueAmount > 0).length} leads` : null}
            icon={AlertTriangle} color={totalOverdue > 0 ? '#ef4444' : '#9ca3af'}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} lg={12}>
          <Card
            title="Revenue by Country"
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
            extra={<Button size="small" type="link" icon={<ArrowRightOutlined />} onClick={() => navigate('/analytics')}>Full Breakdown</Button>}
          >
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 8 }}>
              Scoped by lead creation date (backend limitation) — may differ slightly from the KPI cards above, which are scoped by enrollment date.
            </Text>
            {revenueByCountry.length === 0 ? <Empty description="No revenue data" /> : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={revenueByCountry}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="country" tick={{ fontSize: 11 }} />
                  <YAxis />
                  <Tooltip formatter={v => fmt(v)} />
                  <Legend />
                  <Bar dataKey="total_revenue" name="Actual Revenue" fill="#10b981" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="expected_revenue" name="Expected Revenue" fill="#fbbf24" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card
            title="Recently Enrolled"
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
            extra={<Button size="small" type="link" icon={<ArrowRightOutlined />} onClick={() => navigate('/payments')}>Open Payments</Button>}
          >
            {recentLeads.length === 0 ? <Empty description="No enrolled leads" /> : (
              <Table
                dataSource={recentLeads.map(l => ({ ...l, key: l.lead_id }))}
                columns={columns}
                pagination={false}
                size="small"
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default FinanceDashboard;
