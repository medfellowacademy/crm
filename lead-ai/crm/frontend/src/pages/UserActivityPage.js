import React, { useState, useMemo } from 'react';
import { 
  Card, 
  Row, 
  Col, 
  Statistic, 
  Table, 
  Tag, 
  Avatar, 
  Typography, 
  Select, 
  DatePicker, 
  Button, 
  Space,
  Progress,
  Tooltip,
  Divider,
  Badge,
  Tabs
} from 'antd';
import { useQuery } from '@tanstack/react-query';
import { leadsAPI, usersAPI } from '../api/api';
import {
  UserOutlined,
  RiseOutlined,
  FallOutlined,
  DollarOutlined,
  PhoneOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FireOutlined,
  TrophyOutlined,
  TeamOutlined,
  LineChartOutlined,
  ReloadOutlined,
  FilterOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

const UserActivityPage = () => {
  const [selectedUser, setSelectedUser] = useState('all');
  const [dateRange, setDateRange] = useState([dayjs().subtract(30, 'days'), dayjs()]);
  const [activeTab, setActiveTab] = useState('overview');

  const { data: leadsData, isLoading: leadsLoading } = useQuery({
    queryKey: ['leads'],
    queryFn: () => leadsAPI.getAll().then(res => res.data)
  });
  const { data: usersData, isLoading: usersLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersAPI.getAll().then(res => res.data)
  });

  // Filter leads by date range
  const filterLeadsByDate = (leads) => {
    if (!leads || !dateRange || !dateRange[0] || !dateRange[1]) return [];
    return leads.filter(lead => {
      const leadDate = dayjs(lead.updated_at || lead.created_at);
      return leadDate.isAfter(dateRange[0]) && leadDate.isBefore(dateRange[1].add(1, 'day'));
    });
  };

  const filteredLeads = useMemo(() => 
    filterLeadsByDate(leadsData?.leads || []), 
    [leadsData, dateRange]
  );

  // Calculate user metrics
  const calculateUserMetrics = (userId) => {
    const userLeads = userId === 'all' 
      ? filteredLeads 
      : filteredLeads.filter(l => l.assigned_to === userId);

    const totalLeads = userLeads.length;
    const updatedLeads = userLeads.filter(l => {
      if (!dateRange || !dateRange[0] || !dateRange[1]) return false;
      const updated = dayjs(l.updated_at);
      return updated.isAfter(dateRange[0]) && updated.isBefore(dateRange[1].add(1, 'day'));
    }).length;

    const potentialLeads = userLeads.filter(l => 
      ['Hot', 'Warm'].includes(l.status)
    ).length;

    const enrolled = userLeads.filter(l => l.status === 'Enrolled').length;
    const hot = userLeads.filter(l => l.status === 'Hot').length;
    const warm = userLeads.filter(l => l.status === 'Warm').length;
    const followUp = userLeads.filter(l => l.status === 'Follow Up').length;
    const lost = userLeads.filter(l => 
      ['Not Interested', 'Not Answering', 'Junk'].includes(l.status)
    ).length;

    const totalRevenue = userLeads
      .filter(l => l.status === 'Enrolled')
      .reduce((sum, l) => sum + (l.actual_revenue || 0), 0);

    const expectedRevenue = userLeads
      .filter(l => ['Hot', 'Warm'].includes(l.status))
      .reduce((sum, l) => sum + (l.expected_revenue || 0), 0);

    const conversionRate = totalLeads > 0 ? ((enrolled / totalLeads) * 100).toFixed(1) : 0;

    const avgScore = userLeads.length > 0
      ? (userLeads.reduce((sum, l) => sum + (l.ai_score || 0), 0) / userLeads.length).toFixed(1)
      : 0;

    return {
      totalLeads,
      updatedLeads,
      potentialLeads,
      enrolled,
      hot,
      warm,
      followUp,
      lost,
      totalRevenue,
      expectedRevenue,
      conversionRate,
      avgScore,
      userLeads
    };
  };

  const metrics = calculateUserMetrics(selectedUser);

  // Get all users with metrics
  const usersWithMetrics = useMemo(() => {
    if (!usersData?.users) return [];
    
    return usersData.users.map(user => {
      const userMetrics = calculateUserMetrics(user.full_name);
      return {
        ...user,
        ...userMetrics
      };
    }).sort((a, b) => b.totalRevenue - a.totalRevenue);
  }, [usersData, filteredLeads, dateRange]);

  // Status distribution data for pie chart
  const statusDistribution = [
    { name: 'Enrolled', value: metrics.enrolled, color: '#52c41a' },
    { name: 'Hot', value: metrics.hot, color: '#ff4d4f' },
    { name: 'Warm', value: metrics.warm, color: '#faad14' },
    { name: 'Follow Up', value: metrics.followUp, color: '#1890ff' },
    { name: 'Lost', value: metrics.lost, color: '#8c8c8c' },
  ];

  // Daily activity data
  const getDailyActivity = () => {
    if (!dateRange || !dateRange[0] || !dateRange[1]) return [];
    
    const days = [];
    const start = dateRange[0];
    const end = dateRange[1];
    
    for (let d = start; d.isBefore(end) || d.isSame(end); d = d.add(1, 'day')) {
      const dayLeads = metrics.userLeads.filter(l => {
        const updated = dayjs(l.updated_at);
        return updated.isSame(d, 'day');
      });

      days.push({
        date: d.format('DD MMM'),
        updated: dayLeads.length,
        enrolled: dayLeads.filter(l => l.status === 'Enrolled').length,
        potential: dayLeads.filter(l => ['Hot', 'Warm'].includes(l.status)).length
      });
    }
    
    return days;
  };

  const dailyActivityData = getDailyActivity();

  // User leaderboard columns
  const leaderboardColumns = [
    {
      title: 'Rank',
      key: 'rank',
      width: 60,
      render: (_, __, index) => (
        <Avatar 
          size="small" 
          style={{ 
            backgroundColor: index === 0 ? '#faad14' : index === 1 ? '#d9d9d9' : index === 2 ? '#d48806' : '#1890ff' 
          }}
        >
          {index + 1}
        </Avatar>
      )
    },
    {
      title: 'User',
      dataIndex: 'full_name',
      key: 'full_name',
      render: (name, record) => (
        <Space>
          <Avatar style={{ backgroundColor: '#1890ff' }}>
            {name[0]}
          </Avatar>
          <div>
            <div><Text strong>{name}</Text></div>
            <Text type="secondary" style={{ fontSize: '12px' }}>{record.role}</Text>
          </div>
        </Space>
      )
    },
    {
      title: 'Total Leads',
      dataIndex: 'totalLeads',
      key: 'totalLeads',
      sorter: (a, b) => a.totalLeads - b.totalLeads,
      render: (val) => <Badge count={val} showZero style={{ backgroundColor: '#1890ff' }} />
    },
    {
      title: 'Updated',
      dataIndex: 'updatedLeads',
      key: 'updatedLeads',
      sorter: (a, b) => a.updatedLeads - b.updatedLeads,
      render: (val) => <Tag color="blue">{val}</Tag>
    },
    {
      title: 'Potential',
      dataIndex: 'potentialLeads',
      key: 'potentialLeads',
      sorter: (a, b) => a.potentialLeads - b.potentialLeads,
      render: (val) => <Tag color="orange">{val}</Tag>
    },
    {
      title: 'Enrolled',
      dataIndex: 'enrolled',
      key: 'enrolled',
      sorter: (a, b) => a.enrolled - b.enrolled,
      render: (val) => <Tag color="green">{val}</Tag>
    },
    {
      title: 'Revenue',
      dataIndex: 'totalRevenue',
      key: 'totalRevenue',
      sorter: (a, b) => a.totalRevenue - b.totalRevenue,
      render: (val) => <Text strong style={{ color: '#52c41a' }}>₹{val.toLocaleString()}</Text>
    },
    {
      title: 'Conversion',
      dataIndex: 'conversionRate',
      key: 'conversionRate',
      sorter: (a, b) => a.conversionRate - b.conversionRate,
      render: (val) => (
        <Progress 
          percent={parseFloat(val)} 
          size="small" 
          status={val > 20 ? 'success' : val > 10 ? 'normal' : 'exception'}
        />
      )
    },
    {
      title: 'Avg Score',
      dataIndex: 'avgScore',
      key: 'avgScore',
      sorter: (a, b) => a.avgScore - b.avgScore,
      render: (val) => (
        <Tag color={val > 70 ? 'green' : val > 40 ? 'orange' : 'default'}>
          {val}
        </Tag>
      )
    }
  ];

  return (
    <div style={{ padding: '24px', backgroundColor: '#f0f2f5', minHeight: '100vh' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Title level={2} style={{ marginBottom: 8 }}>
          <TeamOutlined /> User Activity Dashboard
        </Title>
        <Text type="secondary">
          Comprehensive metrics and performance analytics for all users
        </Text>
      </div>

      {/* Filters */}
      <Card style={{ marginBottom: 24 }}>
        <Space size="middle" wrap>
          <div>
            <Text strong style={{ marginRight: 8 }}><FilterOutlined /> Date Range:</Text>
            <RangePicker
              value={dateRange}
              onChange={setDateRange}
              format="DD MMM YYYY"
              style={{ width: 280 }}
              ranges={{
                'Today': [dayjs(), dayjs()],
                'Yesterday': [dayjs().subtract(1, 'day'), dayjs().subtract(1, 'day')],
                'Last 7 Days': [dayjs().subtract(7, 'days'), dayjs()],
                'Last 30 Days': [dayjs().subtract(30, 'days'), dayjs()],
                'This Month': [dayjs().startOf('month'), dayjs()],
                'Last Month': [dayjs().subtract(1, 'month').startOf('month'), dayjs().subtract(1, 'month').endOf('month')],
              }}
            />
          </div>
          
          <div>
            <Text strong style={{ marginRight: 8 }}><UserOutlined /> User:</Text>
            <Select
              value={selectedUser}
              onChange={setSelectedUser}
              style={{ width: 200 }}
              placeholder="Select user"
            >
              <Select.Option value="all">
                <TeamOutlined /> All Users
              </Select.Option>
              {usersData?.users?.map(user => (
                <Select.Option key={user.id} value={user.full_name}>
                  <Avatar size="small" style={{ marginRight: 8 }}>
                    {user.full_name[0]}
                  </Avatar>
                  {user.full_name}
                </Select.Option>
              ))}
            </Select>
          </div>

          <Button 
            icon={<ReloadOutlined />} 
            type="primary"
            onClick={() => window.location.reload()}
          >
            Refresh
          </Button>
        </Space>
      </Card>

      {/* Overview Metrics */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Total Leads"
              value={metrics.totalLeads}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Updated Leads"
              value={metrics.updatedLeads}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#faad14' }}
              suffix={
                <Text type="secondary" style={{ fontSize: '14px' }}>
                  / {metrics.totalLeads}
                </Text>
              }
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Potential Leads"
              value={metrics.potentialLeads}
              prefix={<FireOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Enrolled"
              value={metrics.enrolled}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
              suffix={
                <Text type="secondary" style={{ fontSize: '14px' }}>
                  ({metrics.conversionRate}%)
                </Text>
              }
            />
          </Card>
        </Col>
      </Row>

      {/* Revenue Metrics */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12}>
          <Card>
            <Statistic
              title="Total Revenue (Enrolled)"
              value={metrics.totalRevenue}
              prefix="₹"
              precision={0}
              valueStyle={{ color: '#52c41a', fontSize: '28px' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12}>
          <Card>
            <Statistic
              title="Expected Revenue (Potential)"
              value={metrics.expectedRevenue}
              prefix="₹"
              precision={0}
              valueStyle={{ color: '#faad14', fontSize: '28px' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Tabs for different views */}
      <Tabs 
        activeKey={activeTab} 
        onChange={setActiveTab}
        items={[
          {
            key: 'overview',
            label: <span><LineChartOutlined /> Overview</span>,
            children: (
              <>
                {/* Charts */}
                <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
                  <Col xs={24} lg={16}>
                    <Card title="Daily Activity Trend" bordered={false}>
                      <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={dailyActivityData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="date" />
                          <YAxis />
                          <RechartsTooltip />
                          <Legend />
                          <Line type="monotone" dataKey="updated" stroke="#1890ff" strokeWidth={2} name="Updated" />
                          <Line type="monotone" dataKey="potential" stroke="#faad14" strokeWidth={2} name="Potential" />
                          <Line type="monotone" dataKey="enrolled" stroke="#52c41a" strokeWidth={2} name="Enrolled" />
                        </LineChart>
                      </ResponsiveContainer>
                    </Card>
                  </Col>

                  <Col xs={24} lg={8}>
                    <Card title="Status Distribution" bordered={false}>
                      <ResponsiveContainer width="100%" height={300}>
                        <PieChart>
                          <Pie
                            data={statusDistribution}
                            cx="50%"
                            cy="50%"
                            labelLine={false}
                            label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                            outerRadius={80}
                            fill="#8884d8"
                            dataKey="value"
                          >
                            {statusDistribution.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.color} />
                            ))}
                          </Pie>
                          <RechartsTooltip />
                        </PieChart>
                      </ResponsiveContainer>
                    </Card>
                  </Col>
                </Row>

                {/* Performance Breakdown */}
                <Card title="Performance Breakdown" bordered={false}>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} sm={12} md={6}>
                      <Card size="small" style={{ backgroundColor: '#f6ffed', borderColor: '#b7eb8f' }}>
                        <Statistic
                          title="Enrolled"
                          value={metrics.enrolled}
                          valueStyle={{ color: '#52c41a' }}
                          prefix={<CheckCircleOutlined />}
                        />
                        <Progress 
                          percent={metrics.totalLeads > 0 ? (metrics.enrolled / metrics.totalLeads * 100).toFixed(1) : 0} 
                          strokeColor="#52c41a"
                          size="small"
                        />
                      </Card>
                    </Col>
                    <Col xs={24} sm={12} md={6}>
                      <Card size="small" style={{ backgroundColor: '#fff1f0', borderColor: '#ffccc7' }}>
                        <Statistic
                          title="Hot"
                          value={metrics.hot}
                          valueStyle={{ color: '#ff4d4f' }}
                          prefix={<FireOutlined />}
                        />
                        <Progress 
                          percent={metrics.totalLeads > 0 ? (metrics.hot / metrics.totalLeads * 100).toFixed(1) : 0} 
                          strokeColor="#ff4d4f"
                          size="small"
                        />
                      </Card>
                    </Col>
                    <Col xs={24} sm={12} md={6}>
                      <Card size="small" style={{ backgroundColor: '#fffbe6', borderColor: '#ffe58f' }}>
                        <Statistic
                          title="Warm"
                          value={metrics.warm}
                          valueStyle={{ color: '#faad14' }}
                          prefix={<RiseOutlined />}
                        />
                        <Progress 
                          percent={metrics.totalLeads > 0 ? (metrics.warm / metrics.totalLeads * 100).toFixed(1) : 0} 
                          strokeColor="#faad14"
                          size="small"
                        />
                      </Card>
                    </Col>
                    <Col xs={24} sm={12} md={6}>
                      <Card size="small" style={{ backgroundColor: '#f5f5f5', borderColor: '#d9d9d9' }}>
                        <Statistic
                          title="Lost"
                          value={metrics.lost}
                          valueStyle={{ color: '#8c8c8c' }}
                          prefix={<FallOutlined />}
                        />
                        <Progress 
                          percent={metrics.totalLeads > 0 ? (metrics.lost / metrics.totalLeads * 100).toFixed(1) : 0} 
                          strokeColor="#8c8c8c"
                          size="small"
                        />
                      </Card>
                    </Col>
                  </Row>
                </Card>
              </>
            )
          },
          {
            key: 'leaderboard',
            label: <span><TrophyOutlined /> Leaderboard</span>,
            children: (
              <Card title="User Performance Leaderboard" bordered={false}>
                <Table
                  columns={leaderboardColumns}
                  dataSource={usersWithMetrics}
                  rowKey="id"
                  pagination={{ pageSize: 10 }}
                  loading={usersLoading}
                />
              </Card>
            )
          }
        ]}
      />
    </div>
  );
};

export default UserActivityPage;
