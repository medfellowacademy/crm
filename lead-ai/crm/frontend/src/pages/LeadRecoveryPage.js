import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Row, Col, Card, Statistic, Table, Tag, Select, Button, Space, Typography,
  Alert, Popconfirm, message, Empty, Tooltip,
} from 'antd';
import {
  ReloadOutlined, BellOutlined, RiseOutlined, FireOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { reengagementAPI } from '../api/api';
import { useAuth } from '../context/AuthContext';

dayjs.extend(relativeTime);

const { Text, Paragraph } = Typography;
const { Option } = Select;

const STATUS_META = {
  active:    { color: 'blue',    label: 'Active' },
  responded: { color: 'cyan',    label: 'Responded' },
  converted: { color: 'green',   label: 'Converted' },
  exhausted: { color: 'default', label: 'Exhausted' },
  stopped:   { color: 'orange',  label: 'Stopped' },
};

const LeadRecoveryPage = () => {
  const { user } = useAuth();
  const canRun = ['Super Admin', 'Manager', 'Team Leader'].includes(user?.role);
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState(undefined);

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['reengagement-stats'],
    queryFn: () => reengagementAPI.getStats().then((r) => r.data),
    refetchInterval: 60 * 1000,
  });
  const maxSteps = stats?.max_steps || 3;

  const { data: rows, isLoading: rowsLoading } = useQuery({
    queryKey: ['reengagement-list', statusFilter],
    queryFn: () => reengagementAPI.getAll(statusFilter).then((r) => r.data),
  });

  const runMutation = useMutation({
    mutationFn: () => reengagementAPI.runNow(),
    onSuccess: (res) => {
      const d = res.data || {};
      message.success(
        `Run complete — ${d.newly_started || 0} new reminder${d.newly_started === 1 ? '' : 's'}, `
        + `${d.advanced?.reminded || 0} re-surfaced, ${d.advanced?.converted || 0} converted, `
        + `${d.advanced?.checked || 0} checked`
      );
      queryClient.invalidateQueries({ queryKey: ['reengagement-stats'] });
      queryClient.invalidateQueries({ queryKey: ['reengagement-list'] });
    },
    onError: (e) => message.error(e?.response?.data?.detail || 'Recovery run failed'),
  });

  const columns = [
    {
      title: 'Lead',
      key: 'lead',
      render: (_, row) => (
        <div>
          <div style={{ fontWeight: 600 }}>{row.lead?.full_name || row.lead_id}</div>
          <Text type="secondary" style={{ fontSize: 12 }}>{row.lead?.phone}</Text>
        </div>
      ),
    },
    { title: 'Course', key: 'course', render: (_, row) => row.lead?.course_interested || '—' },
    { title: 'Owner', key: 'owner', render: (_, row) => row.lead?.assigned_to || '—' },
    {
      title: 'Recovery status',
      dataIndex: 'status',
      render: (s) => {
        const meta = STATUS_META[s] || { color: 'default', label: s };
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: 'Reminder #',
      dataIndex: 'step',
      align: 'center',
      render: (step) => `${step || 0} of ${maxSteps}`,
    },
    { title: 'Cold for (at entry)', dataIndex: 'cold_days_at_entry', align: 'center', render: (d) => (d != null ? `${d}d` : '—') },
    {
      title: 'Started',
      dataIndex: 'started_at',
      render: (v) => (v ? <Tooltip title={dayjs(v).format('DD MMM YYYY, HH:mm')}>{dayjs(v).fromNow()}</Tooltip> : '—'),
    },
    {
      title: 'Last reminded',
      dataIndex: 'last_sent_at',
      render: (v) => (v ? dayjs(v).fromNow() : '—'),
    },
    {
      title: 'Revenue recovered',
      dataIndex: 'revenue_at_conversion',
      align: 'right',
      render: (v) => (v ? `₹${Number(v).toLocaleString('en-IN')}` : '—'),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0 }}>
          <BellOutlined /> Lead Recovery
        </h1>
        {canRun && (
          <Popconfirm
            title="Recompute reminders now?"
            description="Scans for newly-cold leads and raises/escalates in-CRM reminders. Nothing is sent externally. Normally runs automatically on a schedule."
            okText="Run now"
            onConfirm={() => runMutation.mutate()}
          >
            <Button type="primary" icon={<ReloadOutlined />} loading={runMutation.isPending}>
              Run Now
            </Button>
          </Popconfirm>
        )}
      </div>

      <Paragraph type="secondary" style={{ maxWidth: 760, marginBottom: 20 }}>
        Leads with no logged contact for a few days automatically get a reminder — here and in
        the notification bell — so nobody has to remember to check. This page tracks how many of
        those "would've been zero anyway" leads convert because someone acted on the reminder —
        pure found money.
      </Paragraph>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={12} sm={8} lg={4}>
          <Card><Statistic title="Entered recovery" loading={statsLoading} value={stats?.total_entered ?? 0} /></Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card><Statistic title="Active now" loading={statsLoading} value={stats?.active_now ?? 0}
            valueStyle={{ color: '#1677ff' }} prefix={<FireOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card><Statistic title="Converted" loading={statsLoading} value={stats?.converted ?? 0}
            valueStyle={{ color: '#389e0d' }} prefix={<RiseOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <Card><Statistic title="Conversion rate" loading={statsLoading} value={stats?.conversion_rate ?? 0} suffix="%" /></Card>
        </Col>
        <Col xs={24} sm={16} lg={8}>
          <Card>
            <Statistic
              title="Revenue recovered"
              loading={statsLoading}
              value={stats?.revenue_recovered ?? 0}
              precision={0}
              prefix="₹"
              valueStyle={{ color: '#389e0d', fontWeight: 700 }}
            />
          </Card>
        </Col>
      </Row>

      {!statsLoading && stats && !stats.total_entered && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="No cold leads have entered recovery yet"
          description={`A lead qualifies once it's gone ${stats?.cold_days || 3}+ days with no logged contact — it'll show up here and in the notification bell automatically.`}
        />
      )}

      <Card
        title="Recovery sequences"
        extra={
          <Select allowClear placeholder="All statuses" style={{ width: 180 }}
            value={statusFilter} onChange={setStatusFilter}>
            {Object.entries(STATUS_META).map(([k, m]) => <Option key={k} value={k}>{m.label}</Option>)}
          </Select>
        }
      >
        <Table
          rowKey="id"
          loading={rowsLoading}
          dataSource={rows || []}
          columns={columns}
          pagination={{ pageSize: 20 }}
          locale={{ emptyText: <Empty description="Nothing here yet" /> }}
        />
      </Card>
    </div>
  );
};

export default LeadRecoveryPage;
