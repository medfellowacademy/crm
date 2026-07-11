import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Typography, Button, Row, Col, Tag, Empty, Statistic, Spin } from 'antd';
import { ArrowLeftOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { DEPARTMENTS, userDepartments, ADMIN_ONLY_PAGES } from '../config/departments';
import { departmentsAPI } from '../api/api';
import SalesDashboard from '../features/dashboards/SalesDashboard';
import MarketingDashboard from '../features/dashboards/MarketingDashboard';
import FinanceDashboard from '../features/dashboards/FinanceDashboard';

const { Title, Text } = Typography;

// Departments with a live KPI dashboard render it above their page tiles;
// Operations/Administration are launcher-only for now.
const DEPT_DASHBOARDS = {
  sales: SalesDashboard,
  marketing: MarketingDashboard,
  finance: FinanceDashboard,
};

const fmt = (n) => `₹${Number(n || 0).toLocaleString('en-IN')}`;
const fmtCr = (n) => {
  const v = Number(n || 0);
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`;
  return fmt(v);
};

// KPI chips per department — each gets a title + value function over the kpis object
const DEPT_KPIS = {
  sales: [
    { label: 'Today\'s leads', val: (k) => k.leads_today, suffix: '' },
    { label: 'This week', val: (k) => k.leads_this_week, suffix: '' },
    { label: 'Conversion', val: (k) => `${k.conversion_rate}%`, raw: true },
  ],
  marketing: [
    { label: 'Meta this week', val: (k) => k.meta_leads_this_week, suffix: '' },
    { label: 'Web this week', val: (k) => k.website_leads_this_week, suffix: '' },
  ],
  finance: [
    { label: 'Total collected', val: (k) => fmtCr(k.total_collected), raw: true },
    { label: 'This month', val: (k) => fmtCr(k.collected_this_month), raw: true },
    { label: 'Enrolled', val: (k) => k.enrolled_count, suffix: ' leads' },
  ],
  operations: [
    { label: 'Present today', val: (k) => k.present_today, suffix: '' },
    { label: 'Total staff', val: (k) => k.total_staff, suffix: '' },
  ],
  administration: [
    { label: 'Total users', val: (k) => k.total_users, suffix: '' },
    { label: 'Active', val: (k) => k.active_users, suffix: '' },
  ],
};

// ── One department card in the hub grid ──────────────────────────────────────
const DepartmentCard = ({ dept, pageCount, kpis, kpiLoading, onOpen }) => {
  const Icon = dept.icon;
  const chips = DEPT_KPIS[dept.key] || [];

  return (
    <Card
      hoverable
      onClick={onOpen}
      style={{ borderRadius: 14, borderTop: `4px solid ${dept.color}`, height: '100%' }}
      bodyStyle={{ padding: 20 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
        <div style={{
          width: 52, height: 52, borderRadius: 12, background: `${dept.color}18`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <Icon size={26} color={dept.color} />
        </div>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>{dept.name}</div>
          <Tag style={{ marginTop: 2 }}>{pageCount} page{pageCount !== 1 ? 's' : ''}</Tag>
        </div>
      </div>

      <Text type="secondary" style={{ fontSize: 13 }}>{dept.description}</Text>

      {chips.length > 0 && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid #f0f0f0' }}>
          {kpiLoading ? (
            <Spin size="small" />
          ) : kpis ? (
            <Row gutter={[8, 8]}>
              {chips.map((chip) => (
                <Col key={chip.label}>
                  <div style={{
                    background: `${dept.color}10`,
                    borderRadius: 8,
                    padding: '4px 10px',
                    display: 'inline-flex',
                    flexDirection: 'column',
                    minWidth: 70,
                  }}>
                    <span style={{ fontSize: 11, color: '#8c8c8c', lineHeight: 1.2 }}>{chip.label}</span>
                    <span style={{ fontSize: 16, fontWeight: 700, color: dept.color, lineHeight: 1.4 }}>
                      {chip.raw ? chip.val(kpis) : `${chip.val(kpis)}${chip.suffix || ''}`}
                    </span>
                  </div>
                </Col>
              ))}
            </Row>
          ) : null}
        </div>
      )}
    </Card>
  );
};

// ── Per-department detail: page tiles + optional live dashboard ──────────────
const DepartmentDetail = ({ dept, pages, onBack }) => {
  const navigate = useNavigate();
  const Dashboard = DEPT_DASHBOARDS[dept.key];
  const Icon = dept.icon;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={onBack}>All Departments</Button>
        <div style={{
          width: 36, height: 36, borderRadius: 10, background: `${dept.color}18`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon size={19} color={dept.color} />
        </div>
        <Title level={4} style={{ margin: 0 }}>{dept.name}</Title>
      </div>

      {/* Page tiles */}
      <Row gutter={[12, 12]} style={{ marginBottom: 24 }}>
        {pages.map(page => {
          const PIcon = page.icon;
          return (
            <Col xs={12} sm={8} md={6} lg={4} key={page.key}>
              <Card
                hoverable
                onClick={() => navigate(page.key)}
                style={{ borderRadius: 10, textAlign: 'center' }}
                bodyStyle={{ padding: '18px 8px' }}
              >
                <PIcon size={22} color={dept.color} style={{ marginBottom: 8 }} />
                <div style={{ fontSize: 13, fontWeight: 600 }}>{page.label}</div>
              </Card>
            </Col>
          );
        })}
      </Row>

      {Dashboard && <Dashboard />}
    </div>
  );
};

// ── Hub ───────────────────────────────────────────────────────────────────────
const DepartmentsPage = () => {
  const [openDept, setOpenDept] = useState(null);
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const accessibleKeys = userDepartments(user);

  const { data: kpiData, isLoading: kpiLoading } = useQuery({
    queryKey: ['department-kpis'],
    queryFn: () => departmentsAPI.getKpis().then(r => r.data),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  const visiblePages = (dept) =>
    dept.pages.filter(p => user.role === 'Super Admin' || !ADMIN_ONLY_PAGES.includes(p.key));

  if (openDept && accessibleKeys.includes(openDept)) {
    const dept = DEPARTMENTS[openDept];
    return <DepartmentDetail dept={dept} pages={visiblePages(dept)} onBack={() => setOpenDept(null)} />;
  }

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <Title level={3} style={{ margin: 0 }}>Departments</Title>
        <Text type="secondary">Pick a department to see its pages and KPIs — one platform, every team</Text>
      </div>

      {accessibleKeys.length === 0 ? (
        <Empty description="No department access granted — ask your admin" />
      ) : (
        <Row gutter={[16, 16]}>
          {accessibleKeys.map(key => {
            const dept = DEPARTMENTS[key];
            return (
              <Col xs={24} sm={12} lg={8} key={key}>
                <DepartmentCard
                  dept={dept}
                  pageCount={visiblePages(dept).length}
                  kpis={kpiData?.[key] || null}
                  kpiLoading={kpiLoading}
                  onOpen={() => setOpenDept(key)}
                />
              </Col>
            );
          })}
        </Row>
      )}
    </div>
  );
};

export default DepartmentsPage;
