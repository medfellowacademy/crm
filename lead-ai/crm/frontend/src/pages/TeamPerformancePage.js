import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, Table, Tag, Avatar, Space, Typography, Alert, Tooltip, Spin, DatePicker } from 'antd';
import {
  TrophyOutlined, ClockCircleOutlined, CalendarOutlined,
  WarningOutlined, InfoCircleOutlined,
} from '@ant-design/icons';
import { counselorsAPI } from '../api/api';

const { Title, Text } = Typography;
const medalColor = ['#ffd700', '#c0c0c0', '#cd7f32'];

// Green if better than team average, red if worse. `lowerIsBetter` flips the
// comparison for metrics like response time where a smaller number wins.
function DeltaCell({ value, teamAvg, suffix = '', lowerIsBetter = false }) {
  if (value == null) return <Text type="secondary">—</Text>;
  if (teamAvg == null) return <Text>{value}{suffix}</Text>;
  const diff = value - teamAvg;
  const isBetter = lowerIsBetter ? diff < 0 : diff > 0;
  const isWorse = lowerIsBetter ? diff > 0 : diff < 0;
  const color = isBetter ? '#52c41a' : isWorse ? '#f5222d' : '#8c8c8c';
  return (
    <div>
      <Text strong style={{ fontSize: 13 }}>{value}{suffix}</Text>
      <div style={{ fontSize: 11, color }}>
        {diff === 0 ? 'at team avg' : `${diff > 0 ? '+' : ''}${diff.toFixed(1)}${suffix} vs avg`}
      </div>
    </div>
  );
}

const CURRENT_USER = JSON.parse(localStorage.getItem('user') || '{}');
const IS_TEAM_SCOPED = ['Manager', 'Team Leader'].includes(CURRENT_USER.role);

export default function TeamPerformancePage() {
  const [dateRange, setDateRange] = React.useState([null, null]);
  const dateParams = dateRange[0] && dateRange[1] ? {
    created_from: dateRange[0].startOf('day').toISOString(),
    created_to: dateRange[1].endOf('day').toISOString(),
  } : {};

  const { data, isLoading } = useQuery({
    queryKey: ['counselor-performance-comparison', dateParams.created_from, dateParams.created_to],
    queryFn: () => counselorsAPI.getPerformanceComparison(dateParams).then(r => r.data),
    staleTime: 60000,
  });

  const counselors = data?.counselors || [];
  const teamAvg = data?.team_average || {};

  const columns = [
    {
      title: 'Rank',
      key: 'rank',
      width: 56,
      render: (_, __, idx) => (
        idx < 3
          ? <div style={{
              width: 26, height: 26, borderRadius: '50%', background: medalColor[idx],
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 13, fontWeight: 800, color: idx === 0 ? '#7d5a00' : idx === 1 ? '#555' : '#6b3a1f',
            }}>
              {idx + 1}
            </div>
          : <Text type="secondary" style={{ paddingLeft: 8 }}>{idx + 1}</Text>
      ),
    },
    {
      title: 'Counselor',
      dataIndex: 'name',
      key: 'name',
      render: (name, r) => (
        <Space>
          <Avatar size={30} style={{ background: '#1890ff', fontSize: 12, flexShrink: 0 }}>
            {name?.charAt(0)?.toUpperCase()}
          </Avatar>
          <div>
            <div style={{ fontWeight: 600, fontSize: 13 }}>{name}</div>
            <div style={{ fontSize: 11, color: '#999' }}>{r.total_leads} leads</div>
          </div>
        </Space>
      ),
    },
    {
      title: 'Conversion',
      key: 'conversion',
      width: 130,
      render: (_, r) => (
        <Space size={4}>
          <DeltaCell value={r.conversion_rate} teamAvg={teamAvg.conversion_rate} suffix="%" />
          {r.sample_size_warning && (
            <Tooltip title={`Only ${r.enrolled} conversion(s) — treat this rate as a rough signal, not a stable statistic.`}>
              <InfoCircleOutlined style={{ color: '#faad14' }} />
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: (
        <span>
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          Response Time
        </span>
      ),
      key: 'response',
      width: 140,
      render: (_, r) => (
        <DeltaCell value={r.avg_response_hours} teamAvg={teamAvg.avg_response_hours} suffix="h" lowerIsBetter />
      ),
    },
    {
      title: (
        <span>
          <CalendarOutlined style={{ marginRight: 4 }} />
          Follow-up Cadence
        </span>
      ),
      key: 'cadence',
      width: 150,
      render: (_, r) => (
        <DeltaCell value={r.avg_days_between_notes} teamAvg={teamAvg.avg_days_between_notes} suffix="d" lowerIsBetter />
      ),
    },
    {
      title: 'Top Objection',
      dataIndex: 'top_objection',
      key: 'top_objection',
      render: (v) => v ? <Tag color="volcano">{v}</Tag> : <Text type="secondary">—</Text>,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>
            <TrophyOutlined style={{ color: '#ffd700', marginRight: 8 }} />
            Team Performance Comparison
          </Title>
          <Text type="secondary">
            Response time and follow-up cadence, benchmarked against the team average.
          </Text>
        </div>
        <Space direction="vertical" size={2}>
          <Text type="secondary" style={{ fontSize: 12 }}>Filter by lead creation date</Text>
          <DatePicker.RangePicker
            value={dateRange}
            onChange={v => setDateRange(v || [null, null])}
            allowClear
          />
        </Space>
      </div>

      {IS_TEAM_SCOPED && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="Showing your team only — people in your reporting line."
        />
      )}

      <Alert
        type="info"
        showIcon
        icon={<WarningOutlined />}
        style={{ marginBottom: 16 }}
        message="Read conversion rate with caution"
        description={
          dateRange[0] && dateRange[1]
            ? "A date filter is active — with fewer leads in this window, per-counselor conversion rate and cadence are even smaller-sample statistics than usual. Widen the range for more stable comparisons."
            : "With very few total conversions company-wide, a single counselor's conversion rate is a small-sample statistic that can swing a lot from one enrollment. Response time and follow-up cadence are computed from thousands of notes/activities and are the more statistically stable signals here."
        }
      />

      <Card bodyStyle={{ padding: 0 }}>
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" />
          </div>
        ) : (
          <Table
            dataSource={counselors}
            columns={columns}
            rowKey="name"
            pagination={false}
            size="small"
          />
        )}
      </Card>
    </div>
  );
}
