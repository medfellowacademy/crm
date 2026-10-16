import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Card, Table, Tag, Space, Typography, Segmented, DatePicker, Drawer, Row, Col,
  Statistic, Empty, Spin, Avatar, Alert, Tooltip,
} from 'antd';
import {
  TrophyOutlined, GlobalOutlined, BookOutlined, RiseOutlined, UserOutlined, FireOutlined,
  ArrowUpOutlined, ArrowDownOutlined,
} from '@ant-design/icons';
import {
  ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, Legend,
} from 'recharts';
import dayjs from 'dayjs';
import { employeePerformanceAPI } from '../api/api';

const { Text, Title } = Typography;

const ROLE_COLOR = { 'Super Admin': 'red', Manager: 'purple', 'Team Leader': 'blue', Counselor: 'green' };

const inr = (n) => `₹${Number(n || 0).toLocaleString('en-IN')}`;
const PERIODS = ['This Week', 'This Month', 'Last Month', 'Overall', 'Custom'];

// Calendar days (not instants) so a timezone can never push a sale across a boundary.
function periodToRange(period, custom) {
  const now = dayjs();
  if (period === 'This Week') return [now.startOf('week'), now];
  if (period === 'This Month') return [now.startOf('month'), now];
  if (period === 'Last Month') {
    const m = now.subtract(1, 'month');
    return [m.startOf('month'), m.endOf('month')];
  }
  if (period === 'Custom' && custom?.[0] && custom?.[1]) return [custom[0], custom[1]];
  return [null, null]; // Overall
}

function VsTeam({ value, avg }) {
  if (!avg) return null;
  const pct = Math.round(((value - avg) / avg) * 100);
  const up = pct >= 0;
  return (
    <Tag color={up ? 'green' : 'red'} icon={up ? <ArrowUpOutlined /> : <ArrowDownOutlined />}>
      {Math.abs(pct)}% vs team avg
    </Tag>
  );
}

function EmployeeDrawer({ employee, team, onClose }) {
  const [grain, setGrain] = useState('Monthly');
  if (!employee) return null;

  const chartData = grain === 'Monthly'
    ? (employee.monthly || []).map((m) => ({ label: dayjs(m.month + '-01').format('MMM YY'), revenue: m.revenue, enrolled: m.enrolled }))
    : (employee.weekly || []).map((w) => ({ label: dayjs(w.week).format('D MMM'), revenue: w.revenue, enrolled: w.enrolled }));

  const breakdownCols = (label) => [
    { title: label, dataIndex: 'name', ellipsis: true },
    { title: 'Sales', dataIndex: 'count', align: 'right', width: 60 },
    { title: 'Revenue', dataIndex: 'revenue', align: 'right', render: inr, width: 110 },
  ];

  return (
    <Drawer
      title={<Space><UserOutlined />{employee.name}<Tag color="gold">#{employee.rank}</Tag></Space>}
      width={720}
      open={!!employee}
      onClose={onClose}
      destroyOnClose
    >
      <Space wrap style={{ marginBottom: 16 }}>
        <Tag color={ROLE_COLOR[employee.role] || 'default'}>{employee.role}</Tag>
        {employee.date_of_joining && (
          <Tag>Joined {dayjs(employee.date_of_joining).format('DD MMM YYYY')}{employee.tenure ? ` · ${employee.tenure}` : ''}</Tag>
        )}
      </Space>

      {(employee.undated_sales > 0 || employee.missing_revenue > 0) && (
        <Alert
          type="warning" showIcon style={{ marginBottom: 16 }}
          message="Some of this person's sales have incomplete data"
          description={[
            employee.undated_sales > 0 && `${employee.undated_sales} enrolled lead(s) have no enrollment date, so they are left out of the period/monthly numbers.`,
            employee.missing_revenue > 0 && `${employee.missing_revenue} sale(s) in this period have no revenue entered, so revenue and avg deal are understated.`,
          ].filter(Boolean).join(' ')}
        />
      )}

      <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
        <Col span={8}>
          <Card size="small">
            <Statistic title="Revenue (period)" value={employee.revenue} formatter={inr} valueStyle={{ color: '#389e0d', fontWeight: 700 }} />
            <VsTeam value={employee.revenue} avg={team?.avg_revenue_per_employee} />
          </Card>
        </Col>
        <Col span={8}><Card size="small"><Statistic title="Sales (period)" value={employee.enrolled} /></Card></Col>
        <Col span={8}><Card size="small"><Statistic title="Avg deal size" value={employee.avg_deal} formatter={inr} /></Card></Col>
        <Col span={8}>
          <Card size="small">
            <Statistic title="Win rate (all-time)" value={employee.win_rate} suffix="%" />
            <VsTeam value={employee.win_rate} avg={team?.avg_win_rate} />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small"><Statistic title="Avg days to close" value={employee.avg_days_to_close ?? '—'} /></Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic title="Active pipeline" value={employee.active_pipeline} />
            <Tag color="volcano" icon={<FireOutlined />}>{employee.hot_leads} hot</Tag>
          </Card>
        </Col>
      </Row>

      <Space style={{ marginBottom: 8, width: '100%', justifyContent: 'space-between' }}>
        <Title level={5} style={{ margin: 0 }}>Sales trend</Title>
        <Segmented options={['Monthly', 'Weekly']} value={grain} onChange={setGrain} />
      </Space>
      {chartData.length ? (
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" fontSize={12} />
            <YAxis yAxisId="left" fontSize={12} />
            <YAxis yAxisId="right" orientation="right" fontSize={12} allowDecimals={false} />
            <RTooltip formatter={(v, name) => (name === 'Revenue' ? inr(v) : v)} />
            <Legend />
            <Bar yAxisId="left" dataKey="revenue" name="Revenue" fill="#1677ff" radius={[4, 4, 0, 0]} />
            <Line yAxisId="right" type="monotone" dataKey="enrolled" name="Sales" stroke="#fa8c16" strokeWidth={2} dot={{ r: 3 }} />
          </ComposedChart>
        </ResponsiveContainer>
      ) : <Empty description="No dated sales yet" />}

      <Row gutter={16} style={{ marginTop: 24 }}>
        <Col span={12}>
          <Title level={5}><GlobalOutlined /> Countries (period)</Title>
          {employee.country_breakdown?.length ? (
            <Table size="small" pagination={false} rowKey="name" dataSource={employee.country_breakdown} columns={breakdownCols('Country')} />
          ) : <Text type="secondary">No data</Text>}
        </Col>
        <Col span={12}>
          <Title level={5}><BookOutlined /> Courses (period)</Title>
          {employee.course_breakdown?.length ? (
            <Table size="small" pagination={false} rowKey="name" dataSource={employee.course_breakdown} columns={breakdownCols('Course')} />
          ) : <Text type="secondary">No data</Text>}
        </Col>
      </Row>
    </Drawer>
  );
}

const EmployeePerformancePage = () => {
  // Deep link from Consolidated Reports: ?employee=Name&month=YYYY-MM opens
  // that employee's drawer with the period pre-set to that month.
  const [searchParams, setSearchParams] = useSearchParams();
  const linkedEmployee = searchParams.get('employee');
  const linkedMonth = searchParams.get('month');
  const linkedStart = linkedMonth && dayjs(linkedMonth + '-01').isValid() ? dayjs(linkedMonth + '-01') : null;

  const [period, setPeriod] = useState(linkedStart ? 'Custom' : 'This Month');
  const [customRange, setCustomRange] = useState(
    linkedStart ? [linkedStart.startOf('month'), linkedStart.endOf('month')] : [null, null]
  );
  const [selectedName, setSelectedName] = useState(null);

  const [from, to] = useMemo(() => periodToRange(period, customRange), [period, customRange]);
  const dateFrom = from ? from.format('YYYY-MM-DD') : undefined;
  const dateTo = to ? to.format('YYYY-MM-DD') : undefined;

  const { data, isLoading } = useQuery({
    queryKey: ['employee-performance', dateFrom, dateTo],
    queryFn: () => employeePerformanceAPI.get({ date_from: dateFrom, date_to: dateTo }).then((r) => r.data),
  });

  const employees = useMemo(() => data?.employees || [], [data]);
  const team = data?.team;
  const quality = data?.data_quality;
  const selected = useMemo(() => employees.find((e) => e.name === selectedName) || null, [employees, selectedName]);

  useEffect(() => {
    if (!linkedEmployee || !employees.length) return;
    if (employees.some((e) => e.name === linkedEmployee)) setSelectedName(linkedEmployee);
    setSearchParams({}, { replace: true });
  }, [linkedEmployee, employees, setSearchParams]);

  const columns = [
    {
      title: '#', dataIndex: 'rank', width: 52, align: 'center',
      render: (v) => (v <= 3 ? <Tag color={['gold', 'default', 'orange'][v - 1]}>{v}</Tag> : v),
    },
    {
      title: 'Employee',
      key: 'employee',
      render: (_, r) => (
        <Space>
          <Avatar size={32} style={{ backgroundColor: '#1677ff' }}>{r.name?.charAt(0)?.toUpperCase()}</Avatar>
          <div>
            <div style={{ fontWeight: 600 }}>{r.name}</div>
            <Tag color={ROLE_COLOR[r.role] || 'default'} style={{ marginTop: 2 }}>{r.role}</Tag>
          </div>
        </Space>
      ),
    },
    {
      title: 'Joined',
      key: 'joined',
      render: (_, r) => r.date_of_joining
        ? <div><div>{dayjs(r.date_of_joining).format('DD MMM YYYY')}</div><Text type="secondary" style={{ fontSize: 12 }}>{r.tenure}</Text></div>
        : <Text type="secondary">Not set</Text>,
    },
    {
      title: 'Sales', dataIndex: 'enrolled', align: 'center',
      sorter: (a, b) => a.enrolled - b.enrolled,
      render: (v, r) => (
        <Space size={4}>
          <Tag color="green">{v}</Tag>
          {(r.undated_sales > 0 || r.missing_revenue > 0) && (
            <Tooltip title={`${r.undated_sales} undated · ${r.missing_revenue} without revenue`}>
              <Text type="warning">!</Text>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: 'Revenue', dataIndex: 'revenue', align: 'right',
      sorter: (a, b) => (a.revenue || 0) - (b.revenue || 0),
      defaultSortOrder: 'descend',
      render: (v) => <Text strong style={{ color: '#389e0d' }}>{inr(v)}</Text>,
    },
    { title: 'Avg deal', dataIndex: 'avg_deal', align: 'right', sorter: (a, b) => a.avg_deal - b.avg_deal, render: (v) => (v ? inr(v) : '—') },
    {
      title: <Tooltip title="Enrolled ÷ all leads ever assigned">Win rate</Tooltip>,
      dataIndex: 'win_rate', align: 'center', sorter: (a, b) => a.win_rate - b.win_rate, render: (v) => `${v}%`,
    },
    { title: 'Days to close', dataIndex: 'avg_days_to_close', align: 'center', render: (v) => (v == null ? '—' : v) },
    {
      title: 'Pipeline', key: 'pipeline', align: 'center',
      sorter: (a, b) => a.active_pipeline - b.active_pipeline,
      render: (_, r) => <span>{r.active_pipeline} <Tag color="volcano" style={{ marginLeft: 4 }}>{r.hot_leads} hot</Tag></span>,
    },
    {
      title: 'Strongest country', key: 'top_country',
      render: (_, r) => r.top_country ? <Tag icon={<GlobalOutlined />}>{r.top_country.name} ({r.top_country.count})</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Strongest course', key: 'top_course',
      render: (_, r) => r.top_course ? <Tag icon={<BookOutlined />}>{r.top_course.name} ({r.top_course.count})</Tag> : <Text type="secondary">—</Text>,
    },
  ];

  const periodLabel = period === 'Custom' && dateFrom ? `${dateFrom} → ${dateTo}` : period;

  return (
    <div>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0 }}><TrophyOutlined style={{ color: '#faad14' }} /> Employee Performance</h1>
          <Text type="secondary">Sales, revenue, deal quality and pipeline health per employee. A sale counts on the day it was enrolled.</Text>
        </div>
        <Space wrap>
          <Segmented options={PERIODS} value={period} onChange={setPeriod} />
          {period === 'Custom' && (
            <DatePicker.RangePicker value={customRange} onChange={(v) => setCustomRange(v || [null, null])} />
          )}
        </Space>
      </div>

      {(quality?.undated_sales > 0 || quality?.sales_without_revenue > 0) && (
        <Alert
          type="warning" showIcon closable style={{ marginBottom: 16 }}
          message="Some sales have incomplete data"
          description={[
            quality.undated_sales > 0 && `${quality.undated_sales} enrolled lead(s) have no enrollment date anywhere (not even in the activity log) and are excluded from period numbers.`,
            quality.sales_without_revenue > 0 && `${quality.sales_without_revenue} sale(s) in this period have no revenue entered, so revenue is understated.`,
            'Fix them on the lead (set Actual Revenue / Enrolled Date) and this page updates.',
          ].filter(Boolean).join(' ')}
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={12} md={6}>
          <Card><Statistic title={`Revenue — ${periodLabel}`} loading={isLoading} value={team?.revenue || 0} formatter={inr}
            valueStyle={{ color: '#389e0d', fontWeight: 700 }} prefix={<RiseOutlined />} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title={`Sales — ${periodLabel}`} loading={isLoading} value={team?.enrolled || 0} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="Avg revenue / employee" loading={isLoading} value={team?.avg_revenue_per_employee || 0} formatter={inr} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="Avg win rate (all-time)" loading={isLoading} value={team?.avg_win_rate || 0} suffix="%" /></Card>
        </Col>
      </Row>

      <Card styles={{ body: { padding: 0 } }}>
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
        ) : employees.length === 0 ? (
          <Empty description="No employees to show" style={{ padding: 40 }} />
        ) : (
          <Table
            rowKey="id"
            dataSource={employees}
            columns={columns}
            pagination={{ pageSize: 20 }}
            scroll={{ x: 'max-content' }}
            onRow={(r) => ({ onClick: () => setSelectedName(r.name), style: { cursor: 'pointer' } })}
          />
        )}
      </Card>

      <EmployeeDrawer employee={selected} team={team} onClose={() => setSelectedName(null)} />
    </div>
  );
};

export default EmployeePerformancePage;
