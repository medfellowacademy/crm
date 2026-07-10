import React from 'react';
import { Tabs, Typography } from 'antd';
import { TrendingUp, Megaphone, Wallet } from 'lucide-react';
import SalesDashboard from '../features/dashboards/SalesDashboard';
import MarketingDashboard from '../features/dashboards/MarketingDashboard';
import FinanceDashboard from '../features/dashboards/FinanceDashboard';

const { Title, Text } = Typography;

const TabLabel = ({ icon: Icon, label }) => (
  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
    <Icon size={15} />
    {label}
  </span>
);

// One platform, every department's own view — a Super Admin or Manager can
// flip between Sales / Marketing / Finance here instead of hunting through
// the full sidebar for the handful of pages each department actually cares
// about. Department-specific roles (Finance, Marketing, Counselor) still
// land directly on their own dashboard via RoleBasedDashboard — this page
// is the cross-department view for people who oversee more than one.
const DepartmentsPage = () => {
  const items = [
    { key: 'sales', label: <TabLabel icon={TrendingUp} label="Sales" />, children: <SalesDashboard /> },
    { key: 'marketing', label: <TabLabel icon={Megaphone} label="Marketing" />, children: <MarketingDashboard /> },
    { key: 'finance', label: <TabLabel icon={Wallet} label="Finance" />, children: <FinanceDashboard /> },
  ];

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <Title level={3} style={{ margin: 0 }}>Departments</Title>
        <Text type="secondary">Sales, Marketing, and Finance — each department's KPIs in one place</Text>
      </div>
      <Tabs defaultActiveKey="sales" items={items} size="large" />
    </div>
  );
};

export default DepartmentsPage;
