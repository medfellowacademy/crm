import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Card, Table, Tag, Space, Typography, Segmented, DatePicker, Drawer, Row, Col,
  Statistic, Empty, Spin, Avatar,
} from 'antd';
import {
  TrophyOutlined, GlobalOutlined, BookOutlined, RiseOutlined, UserOutlined,
} from '@ant-design/icons';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip,
} from 'recharts';
import dayjs from 'dayjs';
import { employeePerformanceAPI } from '../api/api';

const { Text, Title } = Typography;

const ROLE_COLOR = { 'Super Admin': 'red', Manager: 'purple', 'Team Leader': 'blue', Counselor: 'green' };

const inr = (n) => `₹${Number(n || 0).toLocaleString('en-IN')}`;

const PERIODS = ['This Week', 'This Month', 'Overall', 'Custom'];

function periodToRange(period, custom) {
  const now = dayjs();
  if (period === 'This Week') return [now.startOf('week'), now.endOf('day')];
  if (period === 'This Month') return [now.startOf('month'), now.endOf('day')];
  if (period === 'Custom' && custom?.[0] && custom?.[1]) return [custom[0].startOf('day'), custom[1].endOf('day')];
  return [null, null]; // Overall
}

function EmployeeTrendDrawer({ employee, onClose }) {
  if (!employee) return null;
  const chartData = (employee.monthly || []).map((m) => ({
    month: dayjs(m.month + '-01').format('MMM YY'),
    revenue: m.revenue,
    enrolled: m.enrolled,
  }));

  return (
    <Drawer
      title={<Space><UserOutlined />{employee.name}</Space>}
      width={640}
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

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col span={8}><Card size="small"><Statistic title="Leads (book)" value={employee.total_leads} /></Card></Col>
        <Col span={8}><Card size="small"><Statistic title="Enrolled" value={employee.enrolled} valueStyle={{ color: '#389e0d' }} /></Card></Col>
        <Col span={8}><Card size="small"><Statistic title="Revenue" value={employee.revenue} formatter={inr} valueStyle={{ color: '#389e0d', fontWeight: 700 }} /></Card></Col>
      </Row>

      <Title level={5}>Monthly trend (last 12 months of sales)</Title>
      {chartData.length ? (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="month" fontSize={12} />
            <YAxis fontSize={12} />
            <RTooltip formatter={(v, key) => (key === 'revenue' ? inr(v) : v)} />
            <Bar dataKey="revenue" fill="#1677ff" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      ) : <Empty description="No enrolled sales yet" />}

      <Row gutter={16} style={{ marginTop: 24 }}>
        <Col span={12}>
          <Title level={5}><GlobalOutlined /> Countries (enrolled)</Title>
          {employee.country_breakdown?.length ? (
            <Table
              size="small" pagination={false} rowKey="name"
              dataSource={employee.country_breakdown}
              columns={[{ title: 'Country', dataIndex: 'name' }, { title: 'Sales', dataIndex: 'count', align: 'right', width: 70 }]}
            />
          ) : <Text type="secondary">No data</Text>}
        </Col>
        <Col span={12}>
          <Title level={5}><BookOutlined /> Courses (enrolled)</Title>
          {employee.course_breakdown?.length ? (
            <Table
              size="small" pagination={false} rowKey="name"
              dataSource={employee.course_breakdown}
              columns={[{ title: 'Course', dataIndex: 'name', ellipsis: true }, { title: 'Sales', dataIndex: 'count', align: 'right', width: 70 }]}
            />
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
  const [selected, setSelected] = useState(null);

  const [dateFrom, dateTo] = useMemo(() => periodToRange(period, customRange), [period, customRange]);

  const { data, isLoading } = useQuery({
    queryKey: ['employee-performance', dateFrom?.toISOString(), dateTo?.toISOString()],
    queryFn: () => employeePerformanceAPI.get({
      date_from: dateFrom ? dateFrom.toISOString() : undefined,
      date_to: dateTo ? dateTo.toISOString() : undefined,
    }).then((r) => r.data),
  });

  const employees = data?.employees || [];

  useEffect(() => {
    if (!linkedEmployee || !employees.length) return;
    const match = employees.find((e) => e.name === linkedEmployee);
    if (match) setSelected(match);
    setSearchParams({}, { replace: true });
  }, [linkedEmployee, employees, setSearchParams]);

  const totals = useMemo(() => ({
    revenue: employees.reduce((s, e) => s + (e.revenue || 0), 0),
    enrolled: employees.reduce((s, e) => s + (e.enrolled || 0), 0),
    avgConversion: employees.length
      ? Math.round((employees.reduce((s, e) => s + (e.conversion_rate || 0), 0) / employees.length) * 10) / 10
      : 0,
  }), [employees]);

  const columns = [
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
    { title: 'Leads (book)', dataIndex: 'total_leads', align: 'center' },
    { title: 'Enrolled', dataIndex: 'enrolled', align: 'center', render: (v) => <Tag color="green">{v}</Tag> },
    { title: 'Conversion', dataIndex: 'conversion_rate', align: 'center', render: (v) => `${v}%` },
    {
      title: 'Revenue',
      dataIndex: 'revenue',
      align: 'right',
      sorter: (a, b) => (a.revenue || 0) - (b.revenue || 0),
      defaultSortOrder: 'descend',
      render: (v) => <Text strong style={{ color: '#389e0d' }}>{inr(v)}</Text>,
    },
    {
      title: 'Strongest country',
      key: 'top_country',
      render: (_, r) => r.top_country ? <Tag icon={<GlobalOutlined />}>{r.top_country.name} ({r.top_country.count})</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Strongest course',
      key: 'top_course',
      render: (_, r) => r.top_course ? <Tag icon={<BookOutlined />} style={{ maxWidth: 220 }}>{r.top_course.name} ({r.top_course.count})</Tag> : <Text type="secondary">—</Text>,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0 }}><TrophyOutlined style={{ color: '#faad14' }} /> Employee Performance</h1>
          <Text type="secondary">Sales, revenue, and where each employee is strongest — by country and course.</Text>
        </div>
        <Space wrap>
          <Segmented options={PERIODS} value={period} onChange={setPeriod} />
          {period === 'Custom' && (
            <DatePicker.RangePicker value={customRange} onChange={(v) => setCustomRange(v || [null, null])} />
          )}
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={12} sm={8}>
          <Card><Statistic title={`Revenue — ${period}`} loading={isLoading} value={totals.revenue} formatter={inr}
            valueStyle={{ color: '#389e0d', fontWeight: 700 }} prefix={<RiseOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8}>
          <Card><Statistic title={`Enrolled — ${period}`} loading={isLoading} value={totals.enrolled} /></Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card><Statistic title="Avg conversion rate" loading={isLoading} value={totals.avgConversion} suffix="%" /></Card>
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
            onRow={(r) => ({ onClick: () => setSelected(r), style: { cursor: 'pointer' } })}
          />
        )}
      </Card>

      <EmployeeTrendDrawer employee={selected} onClose={() => setSelected(null)} />
    </div>
  );
};

export default EmployeePerformancePage;
