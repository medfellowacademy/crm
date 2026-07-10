import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Card, Row, Col, Table, Tag, Space, Typography, Button, DatePicker, Empty } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { Users, Flame, TrendingUp, CalendarClock } from 'lucide-react';
import { dashboardAPI, adminAPI, counselorsAPI } from '../../api/api';

const { Text, Title } = Typography;

const STAGE_COLORS = { Fresh: '#94a3b8', 'Follow Up': '#f59e0b', Warm: '#fbbf24', Hot: '#ef4444', Enrolled: '#10b981' };

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

const SalesDashboard = () => {
  const navigate = useNavigate();
  const [dateRange, setDateRange] = useState([null, null]);
  const dateParams = dateRange[0] && dateRange[1] ? {
    created_from: dateRange[0].startOf('day').toISOString(),
    created_to: dateRange[1].endOf('day').toISOString(),
  } : {};
  const dateKey = [dateParams.created_from, dateParams.created_to];

  const { data: stats } = useQuery({
    queryKey: ['sales-dashboard-stats', ...dateKey],
    queryFn: () => dashboardAPI.getStats(dateParams).then(res => res.data),
  });

  const { data: funnel = [] } = useQuery({
    queryKey: ['sales-funnel'],
    queryFn: () => adminAPI.getFunnelAnalysis().then(res => res.data?.funnel || []),
  });

  const { data: leaderboard } = useQuery({
    queryKey: ['sales-leaderboard', ...dateKey],
    queryFn: () => counselorsAPI.getPerformanceComparison(dateParams).then(res => res.data),
  });

  const counselors = (leaderboard?.counselors || []).slice(0, 8);

  const columns = [
    { title: 'Counselor', dataIndex: 'name', key: 'name', render: t => <Text strong>{t}</Text> },
    { title: 'Leads', dataIndex: 'total_leads', key: 'total_leads' },
    { title: 'Enrolled', dataIndex: 'enrolled', key: 'enrolled', render: n => <Tag color="green">{n}</Tag> },
    {
      title: 'Conversion', dataIndex: 'conversion_rate', key: 'conversion_rate',
      render: v => `${v}%`, sorter: (a, b) => a.conversion_rate - b.conversion_rate, defaultSortOrder: 'descend',
    },
    {
      title: 'Avg Response', dataIndex: 'avg_response_hours', key: 'avg_response_hours',
      render: v => v != null ? `${v}h` : '—',
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Sales Overview</Title>
          <Text type="secondary">Pipeline health, follow-ups, and counselor performance</Text>
        </div>
        <Space direction="vertical" size={2}>
          <Text type="secondary" style={{ fontSize: 12 }}>Filter by lead creation date</Text>
          <DatePicker.RangePicker value={dateRange} onChange={v => setDateRange(v || [null, null])} allowClear />
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard title="Total Leads" value={(stats?.total_leads || 0).toLocaleString()} icon={Users} color="#3b82f6" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard title="Hot Leads" value={stats?.hot_leads || 0} icon={Flame} color="#ef4444" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard title="Conversion Rate" value={`${stats?.conversion_rate || 0}%`} icon={TrendingUp} color="#10b981" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Leads Today" value={stats?.leads_today || 0}
            sub={`${stats?.leads_this_week || 0} this week`}
            icon={CalendarClock} color="#8b5cf6"
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} lg={10}>
          <Card
            title="Pipeline Funnel"
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
            extra={<Button size="small" type="link" icon={<ArrowRightOutlined />} onClick={() => navigate('/pipeline')}>Open Pipeline</Button>}
          >
            {funnel.length === 0 ? <Empty description="No pipeline data" /> : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={funnel} layout="vertical" margin={{ left: 10, right: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="stage" width={80} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="count" radius={[0, 6, 6, 0]}>
                    {funnel.map((f, i) => <Cell key={i} fill={STAGE_COLORS[f.stage] || '#6366f1'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            title="Counselor Leaderboard"
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
            extra={<Button size="small" type="link" icon={<ArrowRightOutlined />} onClick={() => navigate('/team-performance')}>Full Comparison</Button>}
          >
            <Table
              dataSource={counselors.map(c => ({ ...c, key: c.name }))}
              columns={columns}
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card bordered={false} style={{ borderRadius: 12, textAlign: 'center' }}>
            <Space size="large" wrap>
              <Button onClick={() => navigate('/leads')}>All Leads</Button>
              <Button onClick={() => navigate('/followups')}>Today's Follow-ups</Button>
              <Button onClick={() => navigate('/pipeline')}>Pipeline Board</Button>
              <Button onClick={() => navigate('/lead-analysis')}>Lead Analysis</Button>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default SalesDashboard;
