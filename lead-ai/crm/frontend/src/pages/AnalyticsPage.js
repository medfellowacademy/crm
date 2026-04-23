import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Row, Col, Card, Table, Spin } from 'antd';
import { BarChart, Bar, PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { analyticsAPI, leadsAPI, counselorsAPI } from '../api/api';

const COLORS = ['#ff4d4f', '#faad14', '#52c41a', '#1890ff', '#722ed1'];

const AnalyticsPage = () => {
  const { data: revenueByCountry, isLoading: revenueLoading } = useQuery({
    queryKey: ['revenueByCountry'],
    queryFn: () => analyticsAPI.getRevenueByCountry().then(res => res.data)
  });

  const { data: conversionFunnel } = useQuery({
    queryKey: ['conversionFunnel'],
    queryFn: () => analyticsAPI.getConversionFunnel().then(res => res.data)
  });

  const { data: leads } = useQuery({
    queryKey: ['allLeads'],
    queryFn: () => leadsAPI.getAll().then(res => res.data?.leads || [])
  });

  const { data: counselors } = useQuery({
    queryKey: ['counselors'],
    queryFn: () => counselorsAPI.getAll().then(res => res.data)
  });

  if (revenueLoading) {
    return <div style={{ textAlign: 'center', padding: '100px 0' }}><Spin size="large" /></div>;
  }

  // Lead source distribution
  const sourceData = {};
  leads?.forEach(lead => {
    sourceData[lead.source] = (sourceData[lead.source] || 0) + 1;
  });
  const sourceChartData = Object.entries(sourceData).map(([name, value]) => ({ name, value }));

  // Course interest distribution
  const courseData = {};
  leads?.forEach(lead => {
    courseData[lead.course_interested] = (courseData[lead.course_interested] || 0) + 1;
  });
  const courseChartData = Object.entries(courseData).map(([name, value]) => ({ 
    name: name.length > 20 ? name.substring(0, 20) + '...' : name, 
    value 
  }));

  const counselorColumns = [
    {
      title: 'Counselor',
      dataIndex: 'name',
      key: 'name',
      render: (text) => <strong>{text}</strong>,
    },
    {
      title: 'Total Leads',
      dataIndex: 'total_leads',
      key: 'total_leads',
      sorter: (a, b) => a.total_leads - b.total_leads,
    },
    {
      title: 'Conversions',
      dataIndex: 'total_conversions',
      key: 'total_conversions',
      sorter: (a, b) => a.total_conversions - b.total_conversions,
    },
    {
      title: 'Conversion Rate',
      dataIndex: 'conversion_rate',
      key: 'conversion_rate',
      render: (rate) => `${rate.toFixed(2)}%`,
      sorter: (a, b) => a.conversion_rate - b.conversion_rate,
    },
    {
      title: 'Specialization',
      dataIndex: 'specialization',
      key: 'specialization',
    },
  ];

  return (
    <div>
      <h1 style={{ marginBottom: '24px', fontSize: '28px', fontWeight: 600 }}>
        📈 Analytics & Insights
      </h1>

      {/* Revenue Analytics */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} lg={12}>
          <Card title="Revenue by Country" bordered={false}>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={revenueByCountry}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="country" />
                <YAxis />
                <Tooltip formatter={(value) => `₹${(value / 1000).toFixed(0)}K`} />
                <Legend />
                <Bar dataKey="total_revenue" fill="#52c41a" name="Actual Revenue" />
                <Bar dataKey="expected_revenue" fill="#faad14" name="Expected Revenue" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="Conversion Funnel" bordered={false}>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={conversionFunnel?.stages || []} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis dataKey="name" type="category" width={100} />
                <Tooltip />
                <Legend />
                <Bar dataKey="count" fill="#1890ff" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* Source & Course Analytics */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} lg={12}>
          <Card title="Lead Sources Distribution" bordered={false}>
            <ResponsiveContainer width="100%" height={350}>
              <PieChart>
                <Pie
                  data={sourceChartData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                  outerRadius={100}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {sourceChartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="Course Interest Distribution" bordered={false}>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={courseChartData.slice(0, 5)}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" angle={-45} textAnchor="end" height={100} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="value" fill="#722ed1" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* Counselor Performance */}
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card title="Counselor Performance" bordered={false}>
            <Table
              dataSource={counselors}
              columns={counselorColumns}
              rowKey="id"
              pagination={false}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default AnalyticsPage;
