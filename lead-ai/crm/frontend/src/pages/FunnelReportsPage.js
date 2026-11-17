import React, { lazy } from 'react';
import ReportHub from './ReportHub';

const tabs = [
  { key: 'leads', label: 'Lead analysis', Component: lazy(() => import('./LeadAnalysisPage')) },
  { key: 'speed', label: 'Time to convert', Component: lazy(() => import('./ConversionTimePage')) },
  { key: 'cohorts', label: 'Cohorts', Component: lazy(() => import('./CohortAnalysisPage')) },
];

export default function FunnelReportsPage() {
  return <ReportHub title="Funnel reports" subtitle="Where leads come in, how fast they convert, and where they drop." tabs={tabs} />;
}
