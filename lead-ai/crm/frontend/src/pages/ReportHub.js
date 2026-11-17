import React, { Suspense } from 'react';
import { Tabs, Spin } from 'antd';
import { useSearchParams } from 'react-router-dom';

/**
 * One menu entry, several related reports as tabs. Each tab is the existing page, loaded only when
 * opened. The chosen tab lives in the URL (?tab=...), so a link or refresh lands on the same report.
 */
export default function ReportHub({ title, subtitle, tabs }) {
  const [params, setParams] = useSearchParams();
  const active = tabs.some((t) => t.key === params.get('tab')) ? params.get('tab') : tabs[0].key;
  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>{title}</h2>
        {subtitle && <div style={{ color: 'var(--text-secondary, #6b7280)', fontSize: 13 }}>{subtitle}</div>}
      </div>
      <Tabs
        activeKey={active} destroyInactiveTabPane
        onChange={(k) => setParams({ tab: k }, { replace: true })}
        items={tabs.map(({ key, label, Component }) => ({
          key, label,
          children: (
            <Suspense fallback={<div style={{ textAlign: 'center', padding: 80 }}><Spin /></div>}>
              <Component />
            </Suspense>
          ),
        }))}
      />
    </div>
  );
}
