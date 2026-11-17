import React, { lazy } from 'react';
import ReportHub from './ReportHub';

const tabs = [
  { key: 'users', label: 'User activity', Component: lazy(() => import('./UserActivityPage')) },
  { key: 'updates', label: 'Lead updates', Component: lazy(() => import('./LeadUpdateActivityPage')) },
];

export default function ActivityReportsPage() {
  return <ReportHub title="Activity" subtitle="Who worked which leads, and what changed." tabs={tabs} />;
}
