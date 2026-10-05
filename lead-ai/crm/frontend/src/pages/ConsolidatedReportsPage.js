import React, { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, Link } from 'react-router-dom';
import {
  Card, Row, Col, Statistic, DatePicker, Button, Typography, Spin, Empty, Table, Space, Tag,
  Segmented, Drawer, InputNumber, message, Tooltip,
} from 'antd';
import {
  ArrowUpOutlined, ArrowDownOutlined, DownloadOutlined, FileTextOutlined,
  TeamOutlined, GlobalOutlined, BookOutlined, ShareAltOutlined, FilterOutlined,
  UnorderedListOutlined, DollarOutlined, PrinterOutlined,
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
const FINANCE_ROLES = ['Super Admin', 'Finance'];

function GrowthTag({ pct, suffix }) {
  if (pct == null) return <Tag>New</Tag>;
  const up = pct >= 0;
  return (
    <Tag color={up ? 'green' : 'red'} icon={up ? <ArrowUpOutlined /> : <ArrowDownOutlined />}>
      {Math.abs(pct)}% {suffix}
    </Tag>
  );
}

function KpiCard({ title, kpi, compare, formatter, onView }) {
  const yoy = compare === 'year';
  return (
    <Card>
      <Statistic title={title} value={kpi?.value} formatter={formatter ? (v) => formatter(v) : undefined} />
      <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <GrowthTag pct={yoy ? kpi?.yoy_growth_pct : kpi?.growth_pct} suffix={yoy ? 'vs last year' : 'vs last month'} />
        {onView && (
          <Button size="small" type="link" icon={<UnorderedListOutlined />} onClick={onView} style={{ padding: 0 }}>
            View leads
          </Button>
        )}
      </div>
    </Card>
  );
}

function BreakdownChart({ title, icon, data, onBarClick, ordered }) {
  const rows = (data || []).slice(0, ordered ? 14 : 8);
  if (!rows.length) return (
    <Card title={<Space>{icon}{title}</Space>} size="small"><Empty description="No data" image={Empty.PRESENTED_IMAGE_SIMPLE} /></Card>
  );
  return (
    <Card
      title={<Space>{icon}{title}</Space>}
      size="small"
      extra={onBarClick ? <Text type="secondary" style={{ fontSize: 12 }}>click a bar to see leads</Text> : null}
    >
      <ResponsiveContainer width="100%" height={Math.max(120, rows.length * 34)}>
        <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={130} fontSize={12} interval={0} />
          <RTooltip />
          <Bar
            dataKey="count" radius={[0, 4, 4, 0]}
            cursor={onBarClick ? 'pointer' : undefined}
            onClick={onBarClick ? (d) => onBarClick(d.name) : undefined}
          >
            {rows.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
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

function LeadsDrawer({ monthStr, drill, onClose, onChange }) {
  const open = !!drill;
  const { data, isLoading } = useQuery({
    queryKey: ['consolidated-leads', monthStr, drill],
    queryFn: () => consolidatedReportsAPI.leads({ month: monthStr, ...drill }).then((r) => r.data),
    enabled: open,
  });

  const filterTags = drill
    ? ['source', 'country', 'course', 'employee', 'status'].filter((k) => drill[k])
    : [];

  const columns = [
    {
      title: 'Lead',
      key: 'name',
      render: (_, r) => <Link to={`/leads/${r.lead_id}`}>{r.full_name || r.lead_id}</Link>,
    },
    { title: 'Status', dataIndex: 'status', render: (v) => <Tag color={v === 'Enrolled' ? 'green' : 'default'}>{v}</Tag> },
    { title: 'Source', dataIndex: 'source' },
    { title: 'Country', dataIndex: 'country' },
    { title: 'Course', dataIndex: 'course_interested', ellipsis: true },
    { title: 'Owner', dataIndex: 'assigned_to' },
    {
      title: drill?.kind === 'closed' ? 'Enrolled' : 'Came in',
      key: 'date',
      render: (_, r) => {
        const d = drill?.kind === 'closed' ? (r.enrolled_at || r.updated_at) : r.created_at;
        return d ? dayjs(d).format('DD MMM YYYY') : '—';
      },
    },
    ...(drill?.kind === 'closed'
      ? [{ title: 'Revenue', dataIndex: 'actual_revenue', align: 'right', render: inr }]
      : []),
  ];

  return (
    <Drawer
      title={<Space><UnorderedListOutlined />Leads — {monthStr ? monthLabel(monthStr) : ''}</Space>}
      width={920}
      open={open}
      onClose={onClose}
      destroyOnClose
    >
      {drill && (
        <>
          <Space wrap style={{ marginBottom: 12 }}>
            <Segmented
              value={drill.kind}
              options={[{ label: 'Came in this month', value: 'in' }, { label: 'Closed this month', value: 'closed' }]}
              onChange={(kind) => onChange({ kind })}
            />
            {filterTags.map((k) => (
              <Tag
                key={k} closable icon={<FilterOutlined />}
                onClose={() => onChange({ [k]: undefined })}
              >
                {k}: {drill[k]}
              </Tag>
            ))}
          </Space>
          <div style={{ marginBottom: 12 }}>
            <Text strong>{data?.total ?? '…'}</Text> <Text type="secondary">leads</Text>
            {drill.kind === 'closed' && data && <Text type="secondary"> · {inr(data.revenue)} revenue</Text>}
            {data?.truncated && <Text type="warning"> · showing the first 500</Text>}
          </div>
          <Table
            size="small" rowKey={(r) => r.id || r.lead_id} loading={isLoading}
            dataSource={data?.leads || []} columns={columns}
            pagination={{ pageSize: 25, showSizeChanger: false }}
            scroll={{ x: 'max-content' }}
          />
        </>
      )}
    </Drawer>
  );
}

function SourceRoiCard({ rows, monthStr, canEdit }) {
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: (v) => consolidatedReportsAPI.setAdSpend({ month: monthStr, ...v }),
    onSuccess: () => {
      message.success('Ad spend saved');
      queryClient.invalidateQueries({ queryKey: ['consolidated-report', monthStr] });
    },
    onError: () => message.error('Could not save ad spend'),
  });

  const columns = [
    { title: 'Source', dataIndex: 'source' },
    {
      title: 'Ad spend',
      dataIndex: 'spend',
      align: 'right',
      render: (v, r) => canEdit ? (
        <InputNumber
          key={`${monthStr}-${r.source}-${v}`}
          min={0} defaultValue={v} style={{ width: 130 }} prefix="₹"
          onBlur={(e) => {
            const n = Number(String(e.target.value).replace(/[^0-9.]/g, '')) || 0;
            if (n !== v) save.mutate({ source: r.source, amount: n });
          }}
        />
      ) : inr(v),
    },
    { title: 'Enrolled', dataIndex: 'enrolled', align: 'center' },
    { title: 'Revenue', dataIndex: 'revenue', align: 'right', render: inr },
    {
      title: <Tooltip title="Ad spend ÷ enrollments">Cost / enrollment</Tooltip>,
      dataIndex: 'cost_per_enrollment',
      align: 'right',
      render: (v) => (v == null ? '—' : inr(v)),
    },
    {
      title: <Tooltip title="Revenue ÷ ad spend">ROI</Tooltip>,
      dataIndex: 'roi_multiple',
      align: 'right',
      render: (v) => (v == null ? '—' : <Tag color={v >= 1 ? 'green' : 'red'}>{v}x</Tag>),
    },
  ];

  return (
    <Card
      style={{ marginBottom: 20 }}
      title={<Space><DollarOutlined />Source ROI — {monthLabel(monthStr)}</Space>}
      extra={<Text type="secondary" style={{ fontSize: 12 }}>
        {canEdit ? 'Type the month\'s ad spend per source' : 'Ad spend is entered by Finance'}
      </Text>}
    >
      {rows?.length ? (
        <Table size="small" rowKey="source" pagination={false} dataSource={rows} columns={columns} scroll={{ x: 'max-content' }} />
      ) : <Empty description="No closed leads or ad spend this month" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
    </Card>
  );
}

const ConsolidatedReportsPage = () => {
  const [month, setMonth] = useState(dayjs());
  const [compare, setCompare] = useState('month');
  const [drill, setDrill] = useState(null);
  const navigate = useNavigate();

  const role = useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}')?.role; } catch { return undefined; }
  }, []);

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

  const openDrill = (next) => setDrill({ kind: 'in', ...next });
  const changeDrill = (patch) => setDrill((d) => ({ ...d, ...patch }));

  return (
    <div>
      <style>{`@media print {
        .ant-layout-sider, .ant-layout-header, .ant-drawer, .ant-segmented, .ant-picker, .ant-btn { display: none !important; }
        .ant-layout-content, .ant-layout { margin: 0 !important; padding: 0 !important; }
        .ant-card { break-inside: avoid; }
      }`}</style>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0 }}><FileTextOutlined /> Consolidated Reports</h1>
          <Text type="secondary">Monthly growth — leads in, leads closed, revenue — trended, with a full breakdown and the actual leads behind every number.</Text>
        </div>
        <Space wrap>
          <Segmented
            value={compare}
            onChange={setCompare}
            options={[{ label: 'vs Last Month', value: 'month' }, { label: 'vs Last Year', value: 'year' }]}
          />
          <DatePicker picker="month" value={month} onChange={(v) => v && setMonth(v)} allowClear={false} />
          <Button icon={<DownloadOutlined />} disabled={!trend.length} onClick={() => downloadTrendCsv(trend, monthStr)}>
            Export CSV
          </Button>
          <Button icon={<PrinterOutlined />} disabled={!trend.length} onClick={() => window.print()}>
            Print / Save PDF
          </Button>
        </Space>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
      ) : (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
            <Col xs={12} md={6}>
              <KpiCard title={`Leads In — ${monthLabel(monthStr)}`} kpi={kpis.leads_in} compare={compare}
                onView={() => openDrill({ kind: 'in' })} />
            </Col>
            <Col xs={12} md={6}>
              <KpiCard title="Leads Closed" kpi={kpis.leads_closed} compare={compare}
                onView={() => openDrill({ kind: 'closed' })} />
            </Col>
            <Col xs={12} md={6}>
              <KpiCard title="Revenue" kpi={kpis.revenue} compare={compare} formatter={inr}
                onView={() => openDrill({ kind: 'closed' })} />
            </Col>
            <Col xs={12} md={6}>
              <KpiCard title="Conversion Rate" kpi={kpis.conversion_rate} compare={compare} formatter={(v) => `${v}%`} />
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
                  <RTooltip formatter={(v, key) => (key === 'Revenue' ? inr(v) : v)} />
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
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} md={12}>
              <BreakdownChart title="Pipeline funnel (leads in, by status)" icon={<FilterOutlined />}
                data={data?.funnel_breakdown} ordered
                onBarClick={(status) => openDrill({ kind: 'in', status })} />
            </Col>
            <Col xs={24} md={12}>
              <BreakdownChart title="Sources (leads in)" icon={<ShareAltOutlined />} data={data?.source_breakdown}
                onBarClick={(source) => openDrill({ kind: 'in', source })} />
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
            <Col xs={24} md={12}>
              <BreakdownChart title="Countries (closed)" icon={<GlobalOutlined />} data={data?.country_breakdown}
                onBarClick={(country) => openDrill({ kind: 'closed', country })} />
            </Col>
            <Col xs={24} md={12}>
              <BreakdownChart title="Courses (closed)" icon={<BookOutlined />} data={data?.course_breakdown}
                onBarClick={(course) => openDrill({ kind: 'closed', course })} />
            </Col>
          </Row>

          <SourceRoiCard rows={data?.source_roi} monthStr={monthStr} canEdit={FINANCE_ROLES.includes(role)} />

          <Card title={<Space><TeamOutlined />Top performers — {monthLabel(monthStr)}</Space>}>
            {data?.top_employees?.length ? (
              <Table
                size="small" rowKey="name" pagination={false}
                dataSource={data.top_employees}
                columns={[
                  { title: 'Employee', dataIndex: 'name' },
                  { title: 'Enrolled', dataIndex: 'enrolled', align: 'center' },
                  { title: 'Revenue', dataIndex: 'revenue', align: 'right', render: inr },
                  {
                    title: '',
                    key: 'actions',
                    align: 'right',
                    render: (_, r) => (
                      <Space>
                        <Button size="small" onClick={() => openDrill({ kind: 'closed', employee: r.name })}>Leads</Button>
                        <Button
                          size="small" type="link"
                          onClick={() => navigate(`/employee-performance?employee=${encodeURIComponent(r.name)}&month=${monthStr}`)}
                        >
                          Full profile
                        </Button>
                      </Space>
                    ),
                  },
                ]}
              />
            ) : <Empty description="No enrollments this month" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          </Card>
        </>
      )}

      <LeadsDrawer monthStr={monthStr} drill={drill} onClose={() => setDrill(null)} onChange={changeDrill} />
    </div>
  );
};

export default ConsolidatedReportsPage;
