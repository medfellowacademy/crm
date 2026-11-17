import React, { lazy } from 'react';
import ReportHub from './ReportHub';

const tabs = [
  { key: 'employees', label: 'Employee performance', Component: lazy(() => import('./EmployeePerformancePage')) },
  { key: 'team', label: 'Team comparison', Component: lazy(() => import('./TeamPerformancePage')) },
];

export default function PeopleReportsPage() {
  return <ReportHub title="People reports" subtitle="Sales, revenue and conversion by employee and by team." tabs={tabs} />;
}
