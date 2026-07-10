import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Card, Row, Col, Table, Tag, Space, Typography, Button, DatePicker, Empty } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { Globe, Share2, Target, TrendingUp } from 'lucide-react';
import { sourceAnalyticsAPI, leadsAPI, sheetsAPI } from '../../api/api';

const { Text, Title } = Typography;
const PALETTE = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6'];

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

const MarketingDashboard = () => {
  const navigate = useNavigate();
  const [dateRange, setDateRange] = useState([null, null]);
  const dateParams = dateRange[0] && dateRange[1] ? {
    created_from: dateRange[0].startOf('day').toISOString(),
    created_to: dateRange[1].endOf('day').toISOString(),
  } : {};
  const dateKey = [dateParams.created_from, dateParams.created_to];

  const { data: srcData } = useQuery({
    queryKey: ['marketing-source-analytics', ...dateKey],
    queryFn: () => sourceAnalyticsAPI.getSourceAnalytics(dateParams).then(res => res.data),
  });

  const { data: websiteLeads = [] } = useQuery({
    queryKey: ['marketing-website-leads'],
    queryFn: () => leadsAPI.getAll({ source: 'Website', limit: 2000 }).then(r => r.data?.leads || []),
  });

  const { data: metaStatus } = useQuery({
    queryKey: ['marketing-meta-status'],
    queryFn: () => sheetsAPI.status().then(r => r.data),
  });

  const sources = srcData?.sources || [];
  const summary = srcData?.summary || {};
  const bestSource = [...sources].sort((a, b) => b.conversion_rate - a.conversion_rate)[0];

  const volumeData = [...sources]
    .sort((a, b) => b.total_leads - a.total_leads)
    .slice(0, 8)
    .map(s => ({ name: s.source, leads: s.total_leads }));

  const columns = [
    { title: 'Source', dataIndex: 'source', key: 'source', render: t => <Text strong>{t}</Text> },
    { title: 'Leads', dataIndex: 'total_leads', key: 'total_leads', sorter: (a, b) => a.total_leads - b.total_leads, defaultSortOrder: 'descend' },
    { title: 'Enrolled', dataIndex: 'enrolled', key: 'enrolled', render: n => <Tag color="green">{n}</Tag> },
    { title: 'Conv %', dataIndex: 'conversion_rate', key: 'conversion_rate', render: v => `${v}%` },
    { title: 'Revenue', dataIndex: 'total_revenue', key: 'total_revenue', render: v => `₹${Number(v).toLocaleString('en-IN')}` },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Marketing Overview</Title>
          <Text type="secondary">Lead source attribution, campaigns, and channel performance</Text>
        </div>
        <Space direction="vertical" size={2}>
          <Text type="secondary" style={{ fontSize: 12 }}>Filter by lead creation date</Text>
          <DatePicker.RangePicker value={dateRange} onChange={v => setDateRange(v || [null, null])} allowClear />
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard title="Total Leads" value={(summary.total_leads || 0).toLocaleString()} icon={Target} color="#3b82f6" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Best Converting Source" value={bestSource?.source || '—'}
            sub={bestSource ? `${bestSource.conversion_rate}% conversion` : null}
            icon={TrendingUp} color="#10b981"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Website Leads" value={websiteLeads.length}
            sub={`${websiteLeads.filter(l => !l.assigned_to).length} unassigned`}
            icon={Globe} color="#8b5cf6"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KpiCard
            title="Meta Sync Status" value={metaStatus?.sync_status === 'running' ? 'Syncing…' : metaStatus?.enabled ? 'Active' : 'Not synced'}
            sub={metaStatus?.last_synced_at ? `Last: ${new Date(metaStatus.last_synced_at).toLocaleDateString()}` : null}
            icon={Share2} color="#f59e0b"
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} lg={10}>
          <Card
            title="Lead Volume by Source"
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
            extra={<Button size="small" type="link" icon={<ArrowRightOutlined />} onClick={() => navigate('/analytics')}>Full Analytics</Button>}
          >
            {volumeData.length === 0 ? <Empty description="No source data" /> : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={volumeData} margin={{ bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="leads" radius={[4, 4, 0, 0]}>
                    {volumeData.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            title="Source Attribution"
            bordered={false}
            style={{ borderRadius: 12, height: '100%' }}
          >
            <Table
              dataSource={sources.slice(0, 8).map(s => ({ ...s, key: s.source }))}
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
              <Button onClick={() => navigate('/website-leads')}>Website Leads</Button>
              <Button onClick={() => navigate('/meta-leads')}>Meta Leads</Button>
              <Button onClick={() => navigate('/analytics')}>Full Analytics</Button>
              <Button onClick={() => navigate('/conversion-time')}>Conversion Time</Button>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default MarketingDashboard;
