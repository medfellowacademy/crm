import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Card, Row, Col, Statistic, DatePicker, Button, Typography, Spin, Empty, Table, Space, Tag,
} from 'antd';
import {
  ArrowUpOutlined, ArrowDownOutlined, DownloadOutlined, FileTextOutlined,
  TeamOutlined, GlobalOutlined, BookOutlined, ShareAltOutlined,
} from '@ant-design/icons';
import {
  ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, Legend, BarChart, Cell,
} from 'recharts';
import dayjs from 'dayjs';
import { consolidatedReportsAPI } from '../api/api';

const { Text } = Typography;

const inr = (n) => `₹${Number(n || 0).toLocaleString('en-IN')}`;
const monthLabel = (ym) => dayjs(ym + '-01').format('MMM YYYY');
const PALETTE = ['#1677ff', '#52c41a', '#faad14', '#eb2f96', '#722ed1', '#13c2c2', '#fa541c'];

function GrowthTag({ pct }) {
  if (pct == null) return <Tag>New</Tag>;
  const up = pct >= 0;
  return (
    <Tag color={up ? 'green' : 'red'} icon={up ? <ArrowUpOutlined /> : <ArrowDownOutlined />}>
      {Math.abs(pct)}% vs last month
    </Tag>
  );
}

function KpiCard({ title, value, growth, formatter }) {
  return (
    <Card>
      <Statistic title={title} value={value} formatter={formatter ? (v) => formatter(v) : undefined} />
      <div style={{ marginTop: 6 }}><GrowthTag pct={growth} /></div>
    </Card>
  );
}

function BreakdownChart({ title, icon, data }) {
  if (!data?.length) return (
    <Card title={<Space>{icon}{title}</Space>} size="small"><Empty description="No data" image={Empty.PRESENTED_IMAGE_SIMPLE} /></Card>
  );
  return (
    <Card title={<Space>{icon}{title}</Space>} size="small">
      <ResponsiveContainer width="100%" height={Math.max(120, data.length * 34)}>
        <BarChart data={data.slice(0, 8)} layout="vertical" margin={{ left: 8, right: 16 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={130} fontSize={12} interval={0} />
          <RTooltip />
          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
            {data.slice(0, 8).map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}

function downloadTrendCsv(trend, selectedMonth) {
  const header = 'Month,Leads In,Leads Closed,Revenue,Conversion Rate %\n';
  const body = trend.map((r) => `${r.month},${r.leads_in},${r.leads_closed},${r.revenue},${r.conversion_rate}`).join('\n');
  const blob = new Blob([header + body], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `consolidated-report-${selectedMonth}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const ConsolidatedReportsPage = () => {
  const [month, setMonth] = useState(dayjs());

  const monthStr = month.format('YYYY-MM');
  const { data, isLoading } = useQuery({
    queryKey: ['consolidated-report', monthStr],
    queryFn: () => consolidatedReportsAPI.get({ month: monthStr, months: 12 }).then((r) => r.data),
  });

  const trend = data?.trend || [];
  const kpis = data?.kpis || {};

  const trendChartData = useMemo(
    () => trend.map((r) => ({ ...r, monthLabel: monthLabel(r.month) })),
    [trend]
  );

  const growthChartData = useMemo(() => trend.map((r, i) => {
    const prev = trend[i - 1];
    const pct = prev && prev.revenue ? Math.round(((r.revenue - prev.revenue) / prev.revenue) * 1000) / 10 : null;
    return { monthLabel: monthLabel(r.month), growth: pct };
  }), [trend]);

  return (
    <div>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0 }}><FileTextOutlined /> Consolidated Reports</h1>
          <Text type="secondary">Monthly growth — leads in, leads closed, revenue — trended, with a full breakdown for any month you pick.</Text>
        </div>
        <Space>
          <DatePicker picker="month" value={month} onChange={(v) => v && setMonth(v)} allowClear={false} />
          <Button icon={<DownloadOutlined />} disabled={!trend.length} onClick={() => downloadTrendCsv(trend, monthStr)}>
            Export CSV
          </Button>
        </Space>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
      ) : (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
            <Col xs={12} md={6}>
              <KpiCard title={`Leads In — ${monthLabel(monthStr)}`} value={kpis.leads_in?.value} growth={kpis.leads_in?.growth_pct} />
            </Col>
            <Col xs={12} md={6}>
              <KpiCard title="Leads Closed" value={kpis.leads_closed?.value} growth={kpis.leads_closed?.growth_pct} />
            </Col>
            <Col xs={12} md={6}>
              <KpiCard title="Revenue" value={kpis.revenue?.value} growth={kpis.revenue?.growth_pct} formatter={inr} />
            </Col>
            <Col xs={12} md={6}>
              <KpiCard title="Conversion Rate" value={kpis.conversion_rate?.value} growth={kpis.conversion_rate?.growth_pct} formatter={(v) => `${v}%`} />
            </Col>
          </Row>

          <Card title="12-month trend — leads in vs. leads closed vs. revenue" style={{ marginBottom: 20 }}>
            {trendChartData.length ? (
              <ResponsiveContainer width="100%" height={320}>
                <ComposedChart data={trendChartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="monthLabel" fontSize={12} />
                  <YAxis yAxisId="left" fontSize={12} />
                  <YAxis yAxisId="right" orientation="right" fontSize={12} />
                  <RTooltip formatter={(v, key) => (key === 'revenue' ? inr(v) : v)} />
                  <Legend />
                  <Bar yAxisId="left" dataKey="leads_in" name="Leads In" fill="#91caff" radius={[4, 4, 0, 0]} />
                  <Bar yAxisId="left" dataKey="leads_closed" name="Leads Closed" fill="#52c41a" radius={[4, 4, 0, 0]} />
                  <Line yAxisId="right" type="monotone" dataKey="revenue" name="Revenue" stroke="#fa8c16" strokeWidth={2.5} dot={{ r: 3 }} />
                </ComposedChart>
              </ResponsiveContainer>
            ) : <Empty description="No data yet" />}
          </Card>

          <Card title="Month-over-month revenue growth %" style={{ marginBottom: 20 }}>
            {growthChartData.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={growthChartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="monthLabel" fontSize={12} />
                  <YAxis fontSize={12} unit="%" />
                  <RTooltip formatter={(v) => (v == null ? 'No prior month' : `${v}%`)} />
                  <Bar dataKey="growth" radius={[4, 4, 0, 0]}>
                    {growthChartData.map((d, i) => (
                      <Cell key={i} fill={d.growth == null ? '#d9d9d9' : d.growth >= 0 ? '#52c41a' : '#f5222d'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <Empty description="No data yet" />}
          </Card>

          <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>
            Breakdown for {monthLabel(monthStr)}
          </Text>
          <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
            <Col xs={24} md={8}>
              <BreakdownChart title="Sources (leads in)" icon={<ShareAltOutlined />} data={data?.source_breakdown} />
            </Col>
            <Col xs={24} md={8}>
              <BreakdownChart title="Countries (closed)" icon={<GlobalOutlined />} data={data?.country_breakdown} />
            </Col>
            <Col xs={24} md={8}>
              <BreakdownChart title="Courses (closed)" icon={<BookOutlined />} data={data?.course_breakdown} />
            </Col>
          </Row>

          <Card title={<Space><TeamOutlined />Top performers — {monthLabel(monthStr)}</Space>}>
            {data?.top_employees?.length ? (
              <Table
                size="small" rowKey="name" pagination={false}
                dataSource={data.top_employees}
                columns={[
                  { title: 'Employee', dataIndex: 'name' },
                  { title: 'Enrolled', dataIndex: 'enrolled', align: 'center' },
                  { title: 'Revenue', dataIndex: 'revenue', align: 'right', render: inr },
                ]}
              />
            ) : <Empty description="No enrollments this month" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          </Card>
        </>
      )}
    </div>
  );
};

export default ConsolidatedReportsPage;
