import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Row, Col, Card, Table, Spin, Tag, DatePicker, Space, Typography, Select, Avatar } from 'antd';
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, RadarChart, Radar, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis,
} from 'recharts';
import { analyticsAPI, leadsAPI, counselorsAPI, sourceAnalyticsAPI, callTimingAPI, usersAPI } from '../api/api';

const { Option } = Select;

/* ── palette ─────────────────────────────────────────── */
const PALETTE = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6'];
const SOURCE_COLORS = {
  Facebook: '#1877f2',
  Google: '#ea4335',
  Referral: '#10b981',
  'Walk-in': '#f59e0b',
  Instagram: '#e1306c',
  LinkedIn: '#0077b5',
  YouTube: '#ff0000',
  WhatsApp: '#25d366',
  Unknown: '#9ca3af',
};
const srcColor = (name) => SOURCE_COLORS[name] || PALETTE[Object.keys(SOURCE_COLORS).length % PALETTE.length];

/* ── custom tooltip ───────────────────────────────────── */
const MoneyTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-primary, #fff)', border: '1px solid var(--border-color, #e5e7eb)', borderRadius: 8, padding: '10px 14px', fontSize: 13 }}>
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color, marginBottom: 2 }}>
          {p.name}: {p.name.toLowerCase().includes('revenue') || p.name.toLowerCase().includes('₹')
            ? `₹${Number(p.value).toLocaleString('en-IN')}`
            : p.name.toLowerCase().includes('rate') || p.name.toLowerCase().includes('%')
            ? `${p.value}%`
            : p.value}
        </div>
      ))}
    </div>
  );
};

const PctTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-primary, #fff)', border: '1px solid var(--border-color, #e5e7eb)', borderRadius: 8, padding: '10px 14px', fontSize: 13 }}>
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color, marginBottom: 2 }}>
          {p.name}: {p.value}{p.name.includes('Rate') ? '%' : ''}
        </div>
      ))}
    </div>
  );
};

/* ── rank badge ───────────────────────────────────────── */
const Rank = ({ n }) => {
  const styles = [
    { background: '#fef9c3', color: '#854d0e', border: '1px solid #fde047' },  // gold
    { background: '#f1f5f9', color: '#475569', border: '1px solid #cbd5e1' },  // silver
    { background: '#fff7ed', color: '#9a3412', border: '1px solid #fdba74' },  // bronze
  ];
  const s = n <= 3 ? styles[n - 1] : { background: '#f9fafb', color: '#6b7280', border: '1px solid #e5e7eb' };
  return (
    <span style={{ ...s, borderRadius: 20, padding: '1px 8px', fontWeight: 700, fontSize: 12 }}>
      #{n}
    </span>
  );
};

/* ── main ─────────────────────────────────────────────── */
const AnalyticsPage = () => {
  const [sourceSort, setSourceSort] = useState('conversion_rate');
  const [dateRange, setDateRange] = useState([null, null]);
  const [selectedCounselor, setSelectedCounselor] = useState('all');
  const dateParams = dateRange[0] && dateRange[1] ? {
    created_from: dateRange[0].startOf('day').toISOString(),
    created_to: dateRange[1].endOf('day').toISOString(),
  } : {};
  const dateKey = [dateParams.created_from, dateParams.created_to];

  const { data: revenueByCountry, isLoading: revenueLoading } = useQuery({
    queryKey: ['revenueByCountry', ...dateKey],
    queryFn: () => analyticsAPI.getRevenueByCountry(dateParams).then(res => res.data),
  });

  const { data: conversionFunnel } = useQuery({
    queryKey: ['conversionFunnel', ...dateKey],
    queryFn: () => analyticsAPI.getConversionFunnel(dateParams).then(res => res.data),
  });

  // Fetching up to 2000 leads for chart data (source & course distribution).
  // These are lightweight columns only — no heavy AI text fields.
  const { data: leads } = useQuery({
    queryKey: ['analytics-leads-sample', ...dateKey],
    queryFn: () => leadsAPI.getAll({ limit: 10000, skip: 0, ...dateParams }).then(res => res.data?.leads || []),
    staleTime: 5 * 60 * 1000,
  });

  const { data: usersData } = useQuery({
    queryKey: ['users-analytics'],
    queryFn: () => usersAPI.getAll().then(res => res.data),
  });

  const { data: srcData, isLoading: srcLoading } = useQuery({
    queryKey: ['source-analytics', ...dateKey],
    queryFn: () => sourceAnalyticsAPI.getSourceAnalytics(dateParams).then(res => res.data),
    staleTime: 5 * 60 * 1000,
  });

  if (revenueLoading) {
    return <div style={{ textAlign: 'center', padding: '100px 0' }}><Spin size="large" /></div>;
  }

  /* ── existing charts data ───────────────────────────── */
  const sourceDistData = {};
  leads?.forEach(lead => { sourceDistData[lead.source] = (sourceDistData[lead.source] || 0) + 1; });
  const sourceDistChartData = Object.entries(sourceDistData).map(([name, value]) => ({ name, value }));

  const courseData = {};
  leads?.forEach(lead => { courseData[lead.course_interested] = (courseData[lead.course_interested] || 0) + 1; });
  const courseChartData = Object.entries(courseData).map(([name, value]) => ({
    name: name?.length > 20 ? name.substring(0, 20) + '…' : name,
    value,
  }));

  /* ── source analytics derived ───────────────────────── */
  const sources   = srcData?.sources    || [];
  const campaigns = srcData?.campaigns  || [];
  const summary   = srcData?.summary    || {};

  const sortedSources = [...sources].sort((a, b) => b[sourceSort] - a[sourceSort]);

  // bar chart data for conversion rate (top 8)
  const convRateData = sortedSources
    .slice(0, 8)
    .map(s => ({ name: s.source, 'Conversion Rate': s.conversion_rate, 'Total Leads': s.total_leads }));

  // bar chart data for revenue (top 8 by revenue)
  const revenueData = [...sources]
    .sort((a, b) => b.total_revenue - a.total_revenue)
    .slice(0, 8)
    .map(s => ({ name: s.source, 'Total Revenue': s.total_revenue, 'Avg Revenue': s.avg_revenue }));

  // radar chart for multi-dim comparison (top 5 sources by total leads)
  const top5 = [...sources].sort((a, b) => b.total_leads - a.total_leads).slice(0, 5);
  const maxLeads = Math.max(...top5.map(s => s.total_leads), 1);
  const maxRev = Math.max(...top5.map(s => s.total_revenue), 1);
  const maxConv = Math.max(...top5.map(s => s.conversion_rate), 1);
  const radarData = [
    { metric: 'Volume', ...Object.fromEntries(top5.map(s => [s.source, Math.round((s.total_leads / maxLeads) * 100)])) },
    { metric: 'Conversion', ...Object.fromEntries(top5.map(s => [s.source, Math.round((s.conversion_rate / maxConv) * 100)])) },
    { metric: 'Revenue', ...Object.fromEntries(top5.map(s => [s.source, Math.round((s.total_revenue / maxRev) * 100)])) },
    { metric: 'Hot Leads', ...Object.fromEntries(top5.map(s => [s.source, s.total_leads > 0 ? Math.round((s.hot_leads / s.total_leads) * 100) : 0])) },
  ];

  // Compute counselor performance from leads (date-filtered) grouped by assigned_to
  const users = Array.isArray(usersData) ? usersData : (usersData?.users || []);
  const counselorPerfRaw = useMemo(() => {
    const perf = {};
    (leads || []).forEach(lead => {
      const name = lead.assigned_to;
      if (!name) return;
      if (!perf[name]) {
        perf[name] = { name, total: 0, enrolled: 0, active: 0, lost: 0, revenue: 0, hot: 0 };
      }
      perf[name].total++;
      if (lead.status === 'Enrolled') { perf[name].enrolled++; perf[name].revenue += lead.potential_revenue || 0; }
      if (['Fresh', 'Follow Up', 'Warm', 'Hot'].includes(lead.status)) perf[name].active++;
      if (['Not Interested', 'Not Answering', 'Junk'].includes(lead.status)) perf[name].lost++;
      if (lead.status === 'Hot') perf[name].hot++;
    });
    return Object.values(perf).map(p => ({
      ...p,
      conversionRate: p.total > 0 ? ((p.enrolled / p.total) * 100).toFixed(1) : '0.0',
    })).sort((a, b) => b.total - a.total);
  }, [leads]);

  const counselorNames = counselorPerfRaw.map(c => c.name);
  const counselorPerf = selectedCounselor === 'all'
    ? counselorPerfRaw
    : counselorPerfRaw.filter(c => c.name === selectedCounselor);

  const counselorColumns = [
    {
      title: '#',
      key: 'rank',
      width: 48,
      render: (_, __, i) => <Rank n={i + 1} />,
    },
    {
      title: 'Counselor',
      dataIndex: 'name',
      key: 'name',
      render: t => (
        <Space>
          <Avatar size="small" style={{ backgroundColor: '#6366f1' }}>{t?.charAt(0)?.toUpperCase()}</Avatar>
          <strong>{t}</strong>
        </Space>
      ),
    },
    { title: 'Total Leads', dataIndex: 'total', key: 'total', sorter: (a, b) => a.total - b.total, align: 'center' },
    { title: 'Active', dataIndex: 'active', key: 'active', sorter: (a, b) => a.active - b.active, align: 'center', render: n => <Tag color="blue">{n}</Tag> },
    { title: 'Hot', dataIndex: 'hot', key: 'hot', sorter: (a, b) => a.hot - b.hot, align: 'center', render: n => <Tag color="red">{n}</Tag> },
    { title: 'Enrolled', dataIndex: 'enrolled', key: 'enrolled', sorter: (a, b) => a.enrolled - b.enrolled, align: 'center', render: n => <Tag color="green">{n}</Tag> },
    { title: 'Lost', dataIndex: 'lost', key: 'lost', sorter: (a, b) => a.lost - b.lost, align: 'center', render: n => <Tag color="default">{n}</Tag> },
    {
      title: 'Conv. Rate',
      dataIndex: 'conversionRate',
      key: 'conversionRate',
      sorter: (a, b) => parseFloat(a.conversionRate) - parseFloat(b.conversionRate),
      align: 'center',
      defaultSortOrder: 'descend',
      render: v => (
        <span style={{ color: v >= 30 ? '#10b981' : v >= 15 ? '#f59e0b' : '#ef4444', fontWeight: 700 }}>
          {v}%
        </span>
      ),
    },
    {
      title: 'Revenue (₹)',
      dataIndex: 'revenue',
      key: 'revenue',
      sorter: (a, b) => a.revenue - b.revenue,
      align: 'right',
      render: v => <span style={{ color: '#10b981', fontWeight: 600 }}>₹{Number(v).toLocaleString('en-IN')}</span>,
    },
  ];

  const sourceColumns = [
    {
      title: 'Rank',
      key: 'rank',
      width: 60,
      render: (_, __, i) => <Rank n={i + 1} />,
    },
    {
      title: 'Source',
      dataIndex: 'source',
      key: 'source',
      render: (src) => (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: srcColor(src), display: 'inline-block', flexShrink: 0 }} />
          <strong>{src}</strong>
        </span>
      ),
    },
    { title: 'Total Leads', dataIndex: 'total_leads', key: 'total_leads', sorter: (a, b) => a.total_leads - b.total_leads, align: 'center' },
    { title: 'Enrolled', dataIndex: 'enrolled', key: 'enrolled', sorter: (a, b) => a.enrolled - b.enrolled, align: 'center', render: n => <Tag color="green">{n}</Tag> },
    { title: 'Hot Leads', dataIndex: 'hot_leads', key: 'hot_leads', align: 'center', render: n => <Tag color="orange">{n}</Tag> },
    {
      title: 'Conversion Rate',
      dataIndex: 'conversion_rate',
      key: 'conversion_rate',
      sorter: (a, b) => a.conversion_rate - b.conversion_rate,
      align: 'center',
      defaultSortOrder: 'descend',
      render: (v) => (
        <span style={{ color: v >= 30 ? '#10b981' : v >= 15 ? '#f59e0b' : '#ef4444', fontWeight: 700 }}>
          {v}%
        </span>
      ),
    },
    {
      title: 'Total Revenue',
      dataIndex: 'total_revenue',
      key: 'total_revenue',
      sorter: (a, b) => a.total_revenue - b.total_revenue,
      align: 'right',
      render: v => <span style={{ color: '#10b981', fontWeight: 600 }}>₹{Number(v).toLocaleString('en-IN')}</span>,
    },
    {
      title: 'Avg Rev / Enrollment',
      dataIndex: 'avg_revenue',
      key: 'avg_revenue',
      sorter: (a, b) => a.avg_revenue - b.avg_revenue,
      align: 'right',
      render: v => v ? `₹${Number(v).toLocaleString('en-IN')}` : '—',
    },
    {
      title: 'ROI Score',
      dataIndex: 'roi_score',
      key: 'roi_score',
      sorter: (a, b) => a.roi_score - b.roi_score,
      align: 'center',
      render: v => (
        <Tag color={v >= 50 ? 'purple' : v >= 20 ? 'blue' : 'default'} style={{ fontWeight: 700 }}>
          {v}
        </Tag>
      ),
    },
  ];

  return (
    <div style={{ padding: '0 0 40px' }}>
      <div style={{ marginBottom: 28, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 700, margin: 0 }}>Analytics & Insights</h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: 4, marginBottom: 0 }}>
            Revenue, conversion, and source attribution across the CRM
          </p>
        </div>
        <Space direction="vertical" size={2}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Filter by lead creation date
          </Typography.Text>
          <DatePicker.RangePicker
            value={dateRange}
            onChange={v => setDateRange(v || [null, null])}
            allowClear
          />
        </Space>
      </div>

      {/* ── SOURCE ATTRIBUTION SECTION ────────────────────── */}
      <div style={{ marginBottom: 12 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 4, height: 20, background: '#6366f1', borderRadius: 2, display: 'inline-block' }} />
          Source Attribution Analytics
        </h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: 16, fontSize: 13 }}>
          Which channel brings the best leads? Ranked by conversion rate, revenue, and ROI.
        </p>
      </div>

      {/* Summary KPI strip */}
      {!srcLoading && sources.length > 0 && (() => {
        const bestConv = sortedSources[0];
        const bestRev = [...sources].sort((a, b) => b.total_revenue - a.total_revenue)[0];
        const bestRoi = [...sources].sort((a, b) => b.roi_score - a.roi_score)[0];
        return (
          <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
            {[
              { label: 'Best Conversion Source', value: bestConv?.source, sub: `${bestConv?.conversion_rate}% conversion rate`, color: '#6366f1' },
              { label: 'Highest Revenue Source', value: bestRev?.source, sub: `₹${Number(bestRev?.total_revenue || 0).toLocaleString('en-IN')} total`, color: '#10b981' },
              { label: 'Best ROI Source', value: bestRoi?.source, sub: `ROI score ${bestRoi?.roi_score}`, color: '#f59e0b' },
              { label: 'Overall Conversion Rate', value: `${summary.overall_conversion_rate}%`, sub: `${summary.total_enrolled} / ${summary.total_leads} enrolled`, color: '#3b82f6' },
            ].map((kpi, i) => (
              <Col xs={24} sm={12} lg={6} key={i}>
                <Card
                  style={{ borderRadius: 12, borderLeft: `4px solid ${kpi.color}`, height: '100%' }}
                  bodyStyle={{ padding: '14px 16px' }}
                >
                  <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                    {kpi.label}
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 800, color: kpi.color }}>{kpi.value}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{kpi.sub}</div>
                </Card>
              </Col>
            ))}
          </Row>
        );
      })()}

      {/* Charts row */}
      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        {/* Conversion rate by source */}
        <Col xs={24} lg={12}>
          <Card
            title={<span style={{ fontWeight: 700 }}>Conversion Rate by Source</span>}
            bordered={false}
            style={{ borderRadius: 12 }}
            loading={srcLoading}
          >
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={convRateData} layout="vertical" margin={{ left: 10, right: 30 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tickFormatter={v => `${v}%`} domain={[0, 'auto']} />
                <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 12 }} />
                <Tooltip content={<PctTooltip />} />
                <Bar dataKey="Conversion Rate" radius={[0, 6, 6, 0]}>
                  {convRateData.map((entry, index) => (
                    <Cell key={index} fill={srcColor(entry.name)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>

        {/* Revenue by source */}
        <Col xs={24} lg={12}>
          <Card
            title={<span style={{ fontWeight: 700 }}>Revenue by Source</span>}
            bordered={false}
            style={{ borderRadius: 12 }}
            loading={srcLoading}
          >
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={revenueData} layout="vertical" margin={{ left: 10, right: 30 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tickFormatter={v => `₹${(v / 1000).toFixed(0)}K`} />
                <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 12 }} />
                <Tooltip content={<MoneyTooltip />} />
                <Bar dataKey="Total Revenue" radius={[0, 6, 6, 0]}>
                  {revenueData.map((entry, index) => (
                    <Cell key={index} fill={srcColor(entry.name)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* Volume vs Conversion grouped bar + Radar */}
      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} lg={14}>
          <Card
            title={<span style={{ fontWeight: 700 }}>Volume vs Enrolled — by Source</span>}
            bordered={false}
            style={{ borderRadius: 12 }}
            loading={srcLoading}
          >
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={[...sources].sort((a, b) => b.total_leads - a.total_leads).slice(0, 8).map(s => ({
                  name: s.source,
                  'Total Leads': s.total_leads,
                  Enrolled: s.enrolled,
                  'Hot Leads': s.hot_leads,
                }))}
                margin={{ bottom: 20 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="Total Leads" fill="#c7d2fe" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Hot Leads" fill="#fbbf24" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Enrolled" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card
            title={<span style={{ fontWeight: 700 }}>Multi-Dimension Radar (Top 5 Sources)</span>}
            bordered={false}
            style={{ borderRadius: 12 }}
            loading={srcLoading}
          >
            <ResponsiveContainer width="100%" height={280}>
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="metric" tick={{ fontSize: 11 }} />
                <PolarRadiusAxis domain={[0, 100]} tick={false} />
                {top5.map((s, i) => (
                  <Radar
                    key={s.source}
                    name={s.source}
                    dataKey={s.source}
                    stroke={PALETTE[i % PALETTE.length]}
                    fill={PALETTE[i % PALETTE.length]}
                    fillOpacity={0.12}
                  />
                ))}
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* Full attribution table */}
      <Card
        title={<span style={{ fontWeight: 700 }}>Source Attribution — Full Breakdown</span>}
        bordered={false}
        style={{ borderRadius: 12, marginBottom: 32 }}
        loading={srcLoading}
      >
        <Table
          dataSource={sortedSources.map((s, i) => ({ ...s, key: s.source, _rank: i + 1 }))}
          columns={sourceColumns}
          pagination={false}
          size="middle"
          scroll={{ x: 900 }}
          rowClassName={(_, i) => i === 0 ? 'ant-table-row-selected' : ''}
        />
      </Card>

      {/* ── CAMPAIGN / UTM ATTRIBUTION ─────────────────────── */}
      {campaigns.length > 1 && (
        <>
          <div style={{ marginBottom: 12 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 4, height: 20, background: '#8b5cf6', borderRadius: 2, display: 'inline-block' }} />
              Campaign Performance
            </h2>
          </div>
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} lg={14}>
              <Card title="Campaign Conversion Rate" bordered={false} style={{ borderRadius: 12 }} loading={srcLoading}>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={campaigns.slice(0, 10).map(c => ({ name: c.label, 'Conv %': c.conversion_rate, Leads: c.total_leads }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis yAxisId="left" tick={{ fontSize: 10 }} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} />
                    <Tooltip content={<PctTooltip />} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar yAxisId="left" dataKey="Conv %" fill="#8b5cf6" radius={[4,4,0,0]} />
                    <Bar yAxisId="right" dataKey="Leads" fill="#d8b4fe" radius={[4,4,0,0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            </Col>
            <Col xs={24} lg={10}>
              <Card title="Campaign Revenue" bordered={false} style={{ borderRadius: 12 }} loading={srcLoading}>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={campaigns.slice(0, 8).map(c => ({ name: c.label, Revenue: c.total_revenue }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip content={<MoneyTooltip />} />
                    <Bar dataKey="Revenue" fill="#6366f1" radius={[4,4,0,0]}>
                      {campaigns.slice(0, 8).map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            </Col>
          </Row>
          <Card title="Campaign Attribution — Full Breakdown" bordered={false} style={{ borderRadius: 12, marginBottom: 32 }} loading={srcLoading}>
            <Table
              dataSource={campaigns.map((c, i) => ({ ...c, key: c.label, _rank: i + 1 }))}
              columns={[
                { title: '#', key: 'rank', width: 48, render: (_, __, i) => <Rank n={i + 1} /> },
                { title: 'Campaign', dataIndex: 'label', key: 'label', render: t => <strong>{t}</strong> },
                { title: 'Leads', dataIndex: 'total_leads', key: 'total_leads', sorter: (a, b) => a.total_leads - b.total_leads },
                { title: 'Enrolled', dataIndex: 'enrolled', key: 'enrolled', sorter: (a, b) => a.enrolled - b.enrolled },
                { title: 'Conv %', dataIndex: 'conversion_rate', key: 'conversion_rate', render: v => <Tag color={v >= 20 ? 'green' : v >= 10 ? 'orange' : 'default'}>{v}%</Tag>, sorter: (a, b) => a.conversion_rate - b.conversion_rate },
                { title: 'Revenue (₹)', dataIndex: 'total_revenue', key: 'total_revenue', render: v => `₹${Number(v).toLocaleString('en-IN')}`, sorter: (a, b) => a.total_revenue - b.total_revenue },
                { title: 'Avg AI Score', dataIndex: 'avg_ai_score', key: 'avg_ai_score', sorter: (a, b) => a.avg_ai_score - b.avg_ai_score },
              ]}
              pagination={false}
              size="small"
              scroll={{ x: 700 }}
            />
          </Card>
        </>
      )}

      {/* ── EXISTING ANALYTICS SECTION ────────────────────── */}
      <div style={{ marginBottom: 12 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 4, height: 20, background: '#10b981', borderRadius: 2, display: 'inline-block' }} />
          Revenue & Funnel Analytics
        </h2>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card title="Revenue by Country" bordered={false} style={{ borderRadius: 12 }}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={revenueByCountry}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="country" />
                <YAxis />
                <Tooltip formatter={(value) => `₹${(value / 1000).toFixed(0)}K`} />
                <Legend />
                <Bar dataKey="total_revenue" fill="#10b981" name="Actual Revenue" radius={[4, 4, 0, 0]} />
                <Bar dataKey="expected_revenue" fill="#fbbf24" name="Expected Revenue" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="Conversion Funnel" bordered={false} style={{ borderRadius: 12 }}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={conversionFunnel?.stages || []} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis dataKey="name" type="category" width={100} />
                <Tooltip />
                <Legend />
                <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card title="Lead Volume by Source" bordered={false} style={{ borderRadius: 12 }}>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={sourceDistChartData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                  outerRadius={100}
                  dataKey="value"
                >
                  {sourceDistChartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={srcColor(entry.name)} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="Course Interest Distribution" bordered={false} style={{ borderRadius: 12 }}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={courseChartData.slice(0, 5)}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" angle={-30} textAnchor="end" height={80} tick={{ fontSize: 11 }} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="value" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card
            title={<span style={{ fontWeight: 700 }}>Counselor Performance</span>}
            bordered={false}
            style={{ borderRadius: 12 }}
            extra={
              <Select
                value={selectedCounselor}
                onChange={setSelectedCounselor}
                style={{ width: 200 }}
                showSearch
                placeholder="Filter by counselor"
              >
                <Option value="all">All Counselors</Option>
                {counselorNames.map(n => (
                  <Option key={n} value={n}>{n}</Option>
                ))}
              </Select>
            }
          >
            {counselorPerf.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-secondary)' }}>
                No data for the selected date range
              </div>
            ) : (
              <Table
                dataSource={counselorPerf}
                columns={counselorColumns}
                rowKey="name"
                pagination={{ pageSize: 10, hideOnSinglePage: true }}
                size="middle"
                scroll={{ x: 700 }}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default AnalyticsPage;
