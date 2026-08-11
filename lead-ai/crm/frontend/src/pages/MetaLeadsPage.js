import React, { useState, useEffect, useRef } from 'react';
import {
  Table, Card, Button, Tag, Statistic, Row, Col, Space, Typography,
  Tooltip, Badge, Alert, Spin, Modal, message, Tabs, DatePicker,
} from 'antd';
import {
  SyncOutlined, CheckCircleOutlined, ClockCircleOutlined,
  ExclamationCircleOutlined, InstagramOutlined, FacebookOutlined,
  BarChartOutlined, TeamOutlined, DollarCircleOutlined,
  MergeCellsOutlined, RetweetOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { sheetsAPI, leadsAPI, duplicatesAPI } from '../api/api';
import { useAuth } from '../context/AuthContext';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
dayjs.extend(relativeTime);

const { Title, Text } = Typography;

const SOURCE_ICON = {
  Instagram: <InstagramOutlined style={{ color: '#e1306c' }} />,
  Facebook: <FacebookOutlined style={{ color: '#1877f2' }} />,
};

const STATUS_COLORS = {
  Fresh: 'blue',
  New: 'blue',
  Interested: 'cyan',
  'Follow-up': 'orange',
  Enrolled: 'green',
  'Not Interested': 'red',
  Hot: 'red',
  Warm: 'orange',
};

// ── Lead list modal ────────────────────────────────────────────────────────────
const AdSetLeadsModal = ({ adset, open, onClose }) => {
  const { data, isLoading } = useQuery({
    queryKey: ['adset-leads', adset],
    queryFn: () =>
      leadsAPI.getAll({ limit: 1000, adset_name: adset }).then(r => r.data?.leads || []),
    enabled: open && !!adset,
    staleTime: 2 * 60 * 1000,
  });

  const cols = [
    { title: 'Name', dataIndex: 'full_name', key: 'name', width: 160 },
    { title: 'Phone', dataIndex: 'phone', key: 'phone', width: 140 },
    { title: 'Email', dataIndex: 'email', key: 'email', ellipsis: true },
    { title: 'Course', dataIndex: 'course_interested', key: 'course', ellipsis: true, width: 200 },
    {
      title: 'Status', dataIndex: 'status', key: 'status', width: 110,
      render: s => <Tag color={STATUS_COLORS[s] || 'default'}>{s}</Tag>,
    },
    {
      title: 'Received', dataIndex: 'created_at', key: 'created_at', width: 120,
      render: v => v ? dayjs(v).fromNow() : '—',
    },
  ];

  return (
    <Modal
      title={<Space><TeamOutlined /><span>Leads — {adset}</span></Space>}
      open={open}
      onCancel={onClose}
      footer={null}
      width={900}
    >
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : (
        <Table
          dataSource={data || []}
          columns={cols}
          rowKey="lead_id"
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 800 }}
        />
      )}
    </Modal>
  );
};

// ── All Meta Leads table ───────────────────────────────────────────────────────
const AllMetaLeadsTable = () => {
  const [dateRange, setDateRange] = useState([null, null]);

  const { data, isLoading } = useQuery({
    queryKey: ['all-meta-leads', dateRange[0]?.toISOString(), dateRange[1]?.toISOString()],
    queryFn: () => leadsAPI.getAll({
      limit: 2000, meta_only: true,
      ...(dateRange[0] && dateRange[1] ? {
        created_from: dateRange[0].startOf('day').toISOString(),
        created_to: dateRange[1].endOf('day').toISOString(),
      } : {}),
    }).then(r => r.data?.leads || []),
    staleTime: 2 * 60 * 1000,
  });

  const cols = [
    {
      title: 'Name', dataIndex: 'full_name', key: 'name', width: 160,
      render: v => <Text strong>{v}</Text>,
    },
    { title: 'Phone', dataIndex: 'phone', key: 'phone', width: 145 },
    { title: 'Email', dataIndex: 'email', key: 'email', ellipsis: true },
    { title: 'Course', dataIndex: 'course_interested', key: 'course', ellipsis: true, width: 200 },
    { title: 'Ad Set', dataIndex: 'adset_name', key: 'adset', ellipsis: true, width: 180,
      render: v => v ? <Tag color="purple">{v}</Tag> : '—' },
    { title: 'Source', dataIndex: 'source', key: 'source', width: 100,
      render: v => <Space size={4}>{SOURCE_ICON[v]}<span>{v}</span></Space> },
    { title: 'Status', dataIndex: 'status', key: 'status', width: 100,
      render: s => <Tag color={STATUS_COLORS[s] || 'default'}>{s}</Tag> },
    { title: 'Received', dataIndex: 'created_at', key: 'received', width: 120,
      render: v => v ? dayjs(v).fromNow() : '—' },
  ];

  return (
    <>
      <div style={{ marginBottom: 12 }}>
        <DatePicker.RangePicker
          value={dateRange}
          onChange={v => setDateRange(v || [null, null])}
          allowClear
          placeholder={['Received from', 'to']}
        />
      </div>
      <Table
        dataSource={data || []}
        columns={cols}
        rowKey="lead_id"
        loading={isLoading}
        size="small"
        pagination={{ pageSize: 50, showSizeChanger: true }}
        scroll={{ x: 1100 }}
        locale={{ emptyText: 'No Meta leads synced yet. Click "Sync Now" to import.' }}
      />
    </>
  );
};

// ── Repeated Leads table ───────────────────────────────────────────────────────
const RepeatedLeadsTable = () => {
  const { data: result, isLoading } = useQuery({
    queryKey: ['repeated-leads'],
    queryFn: () => duplicatesAPI.repeated().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  });

  const leads = result?.repeated || [];

  const cols = [
    {
      title: 'Lead',
      key: 'lead',
      width: 200,
      render: (_, r) => (
        <div>
          <Text strong>{r.full_name}</Text>
          <div style={{ fontSize: 12, color: '#6b7280' }}>{r.email || r.phone}</div>
        </div>
      ),
    },
    {
      title: 'Owner (Counselor)',
      dataIndex: 'assigned_to',
      key: 'owner',
      width: 150,
      render: v => v
        ? <Tag color="geekblue" style={{ fontWeight: 600 }}>{v}</Tag>
        : <Text type="secondary">Unassigned</Text>,
    },
    {
      title: 'First Submission',
      key: 'first',
      width: 220,
      render: (_, r) => (
        <div>
          <div>
            <Tag color="purple" style={{ maxWidth: 190, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {r.adset_name || 'Unknown adset'}
            </Tag>
          </div>
          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
            {r.campaign_name || ''}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 1 }}>
            {r.created_at ? dayjs(r.created_at).format('DD MMM YYYY') : '—'}
          </div>
        </div>
      ),
    },
    {
      title: 'Latest Re-submission',
      key: 'latest',
      width: 240,
      render: (_, r) => r.last_submission_adset ? (
        <div>
          <div>
            <Tag color="volcano" style={{ maxWidth: 210, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {r.last_submission_adset}
            </Tag>
          </div>
          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
            {r.last_submission_campaign || ''}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 1 }}>
            {r.last_submission_tab ? `Tab: ${r.last_submission_tab}` : ''}
            {r.last_submission_date
              ? ` · ${dayjs(r.last_submission_date).format('DD MMM YYYY')}`
              : ''}
          </div>
        </div>
      ) : <Text type="secondary">—</Text>,
    },
    {
      title: 'Submissions',
      dataIndex: 'submission_count',
      key: 'count',
      width: 100,
      sorter: (a, b) => (a.submission_count || 1) - (b.submission_count || 1),
      defaultSortOrder: 'descend',
      render: v => (
        <Badge
          count={v || 1}
          style={{ backgroundColor: (v || 1) >= 3 ? '#ef4444' : '#f59e0b', fontWeight: 700 }}
          overflowCount={99}
        />
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: s => <Tag color={STATUS_COLORS[s] || 'default'}>{s}</Tag>,
    },
    {
      title: 'Course',
      dataIndex: 'course_interested',
      key: 'course',
      ellipsis: true,
      width: 180,
    },
    {
      title: 'Action',
      key: 'action',
      width: 80,
      render: (_, r) => (
        <Button
          size="small"
          href={`/leads/${r.lead_id}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          View
        </Button>
      ),
    },
  ];

  return (
    <>
      {leads.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={
            <>
              <Text strong>{leads.length} leads</Text> submitted via Meta ads multiple times.
              Each row shows the original owner and ad set, plus where the lead re-submitted from.
              The counselor's assignment is preserved — only the latest ad set changes.
            </>
          }
        />
      )}
      <Table
        dataSource={leads}
        columns={cols}
        rowKey="lead_id"
        loading={isLoading}
        size="small"
        pagination={{ pageSize: 25, showSizeChanger: true }}
        scroll={{ x: 1200 }}
        locale={{ emptyText: 'No repeated leads found. Leads who submit via multiple Meta ads will appear here.' }}
        rowClassName={r => (r.submission_count || 1) >= 3 ? 'repeated-lead-high' : ''}
      />
    </>
  );
};

// ── Main page ──────────────────────────────────────────────────────────────────
const MetaLeadsPage = () => {
  const queryClient = useQueryClient();
  const { user: authUser } = useAuth();
  const isAdmin = ['admin', 'super admin', 'manager'].includes(
    (authUser?.role || '').toLowerCase()
  );
  const [selectedAdset, setSelectedAdset] = useState(null);

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['sheets-status'],
    queryFn: () => sheetsAPI.status().then(r => r.data),
    staleTime: 30 * 1000,
    refetchInterval: (query) => query.state.data?.sync_status === 'running' ? 4000 : false,
  });

  const { data: adsets = [], isLoading: adsetsLoading } = useQuery({
    queryKey: ['sheets-adsets'],
    queryFn: () => sheetsAPI.adsets().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  });

  const { data: repeatedResult } = useQuery({
    queryKey: ['repeated-leads'],
    queryFn: () => duplicatesAPI.repeated().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  });
  const repeatedCount = repeatedResult?.total || 0;

  const syncMutation = useMutation({
    mutationFn: () => sheetsAPI.sync(),
    onSuccess: () => {
      message.info('Sync started in the background — this can take a few minutes for a large sheet.');
      queryClient.invalidateQueries({ queryKey: ['sheets-status'] });
    },
    onError: (e) => {
      if (e?.response?.status === 409) {
        message.warning('A sync is already in progress. Please wait for it to finish.');
      } else {
        message.error(`Sync failed to start: ${e?.response?.data?.detail || e.message}`);
      }
    },
  });

  const prevSyncStatus = useRef(status?.sync_status);
  useEffect(() => {
    const prev = prevSyncStatus.current;
    const curr = status?.sync_status;
    if (prev === 'running' && curr === 'completed') {
      const d = status.last_sync_stats || {};
      const parts = [];
      if (d.new_leads > 0)     parts.push(`${d.new_leads} new leads created`);
      if (d.updated_leads > 0) parts.push(`${d.updated_leads} existing leads updated`);
      if (parts.length === 0)  parts.push('no new leads');
      message.success(`Sync complete — ${parts.join(', ')} (${d.skipped || 0} skipped)`);
      queryClient.invalidateQueries({ queryKey: ['sheets-adsets'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['all-meta-leads'] });
      queryClient.invalidateQueries({ queryKey: ['repeated-leads'] });
    } else if (prev === 'running' && curr === 'error') {
      message.error(`Sync failed: ${status.last_sync_error || 'Unknown error'}`);
    }
    prevSyncStatus.current = curr;
  }, [status, queryClient]);

  const cleanupMutation = useMutation({
    mutationFn: () => duplicatesAPI.cleanup(),
    onSuccess: (res) => {
      const d = res.data;
      if (d.error) {
        message.error(`Cleanup failed: ${d.error}`);
        return;
      }
      message.success(
        `Cleanup complete — ${d.deleted_leads} duplicate leads removed, ` +
        `${d.merged_groups} groups merged` +
        (d.still_repeated > 0 ? `, ${d.still_repeated} still flagged (manual review needed)` : '')
      );
      queryClient.invalidateQueries({ queryKey: ['sheets-adsets'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['all-meta-leads'] });
      queryClient.invalidateQueries({ queryKey: ['repeated-leads'] });
    },
    onError: (e) => message.error(`Cleanup failed: ${e?.response?.data?.detail || e.message}`),
  });

  const total      = adsets.reduce((s, a) => s + a.total,        0);
  const freshLeads = adsets.reduce((s, a) => s + (a.fresh || 0), 0);
  const enrolled   = adsets.reduce((s, a) => s + a.enrolled,     0);
  const adSetCount = adsets.length;

  const adsetColumns = [
    {
      title: 'Ad Set Name',
      dataIndex: 'adset_name',
      key: 'adset_name',
      render: (v) => <Text strong>{v || 'Unknown'}</Text>,
      sorter: (a, b) => (a.adset_name || '').localeCompare(b.adset_name || ''),
    },
    {
      title: 'Campaign',
      dataIndex: 'campaign_name',
      key: 'campaign',
      ellipsis: true,
      render: v => v ? <Text type="secondary">{v}</Text> : '—',
    },
    {
      title: 'Platform',
      dataIndex: 'source',
      key: 'source',
      width: 110,
      render: v => (
        <Space size={4}>
          {SOURCE_ICON[v] || null}
          <span>{v || 'Meta'}</span>
        </Space>
      ),
    },
    {
      title: 'Total',
      dataIndex: 'total',
      key: 'total',
      width: 80,
      sorter: (a, b) => a.total - b.total,
      defaultSortOrder: 'descend',
      render: v => <Tag color="blue" style={{ fontWeight: 700 }}>{v}</Tag>,
    },
    {
      title: 'Fresh',
      dataIndex: 'fresh',
      key: 'fresh',
      width: 70,
      render: v => (v || 0) > 0 ? <Badge count={v} color="#1677ff" /> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Follow Up',
      dataIndex: 'follow_up',
      key: 'follow_up',
      width: 90,
      render: v => (v || 0) > 0 ? <Badge count={v} color="#f59e0b" /> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Interested',
      dataIndex: 'interested',
      key: 'interested',
      width: 90,
      render: v => (v || 0) > 0 ? <Badge count={v} color="#06b6d4" /> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Enrolled',
      dataIndex: 'enrolled',
      key: 'enrolled',
      width: 80,
      render: v => (v || 0) > 0 ? <Badge count={v} color="#10b981" /> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Not Int.',
      dataIndex: 'not_interested',
      key: 'not_interested',
      width: 80,
      render: v => (v || 0) > 0 ? <Badge count={v} color="#ef4444" /> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Repeated',
      dataIndex: 'repeated',
      key: 'repeated',
      width: 90,
      render: v => (v || 0) > 0
        ? <Badge count={v} color="#f97316" style={{ fontWeight: 600 }} />
        : <Text type="secondary">0</Text>,
    },
    {
      title: 'Latest Lead',
      dataIndex: 'latest',
      key: 'latest',
      width: 130,
      render: v => v ? (
        <Tooltip title={dayjs(v).format('DD MMM YYYY HH:mm')}>
          <Text type="secondary">{dayjs(v).fromNow()}</Text>
        </Tooltip>
      ) : '—',
    },
    {
      title: '',
      key: 'action',
      width: 80,
      render: (_, row) => (
        <Button size="small" onClick={() => setSelectedAdset(row.adset_name)}>
          View
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>Meta Leads — Google Sheet Sync</Title>
          <Text type="secondary">
            Auto-imports leads from your connected Meta Lead Ads sheet into the CRM
          </Text>
        </div>
        <Space>
          {isAdmin && (
            <Button
              icon={<MergeCellsOutlined />}
              loading={cleanupMutation.isPending}
              onClick={() => cleanupMutation.mutate()}
              title="Merge duplicate leads that share phone or email"
            >
              Clean Up Duplicates
            </Button>
          )}
          <Button
            type="primary"
            icon={<SyncOutlined spin={syncMutation.isPending || status?.sync_status === 'running'} />}
            loading={syncMutation.isPending}
            disabled={status?.sync_status === 'running'}
            onClick={() => syncMutation.mutate()}
            style={{ background: '#1877f2', borderColor: '#1877f2' }}
          >
            {status?.sync_status === 'running' ? 'Syncing…' : 'Sync Now'}
          </Button>
        </Space>
      </div>

      {/* Status card */}
      <Card style={{ marginBottom: 20, background: '#f8faff', border: '1px solid #d0e4ff' }}>
        {statusLoading ? <Spin /> : (
          <Row gutter={24} align="middle">
            <Col flex="auto">
              <Space direction="vertical" size={2}>
                <Space>
                  {status?.sync_status === 'running'
                    ? <SyncOutlined spin style={{ color: '#1877f2' }} />
                    : status?.enabled
                      ? <CheckCircleOutlined style={{ color: '#10b981' }} />
                      : <ExclamationCircleOutlined style={{ color: '#f59e0b' }} />}
                  <Text strong>
                    {status?.sync_status === 'running'
                      ? 'Sync in progress…'
                      : status?.enabled ? 'Sync active' : 'Not yet synced'}
                  </Text>
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Sheet ID: {status?.sheet_id || '—'}
                </Text>
                {status?.sync_status === 'completed' && status?.last_sync_stats && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Last result: {status.last_sync_stats.new_leads || 0} new,{' '}
                    {status.last_sync_stats.updated_leads || 0} updated,{' '}
                    {status.last_sync_stats.skipped || 0} skipped
                    {status.last_sync_stats.errors > 0 ? `, ${status.last_sync_stats.errors} errors` : ''}
                  </Text>
                )}
                {status?.sync_status === 'error' && status?.last_sync_error && (
                  <Text type="danger" style={{ fontSize: 12 }}>
                    Last sync failed: {status.last_sync_error}
                  </Text>
                )}
              </Space>
            </Col>
            <Col>
              <Space size={4}>
                <ClockCircleOutlined style={{ color: '#6b7280' }} />
                <Text type="secondary">
                  Last synced:{' '}
                  {status?.last_synced_at
                    ? dayjs(status.last_synced_at).fromNow()
                    : 'Never'}
                </Text>
              </Space>
            </Col>
            {status?.api_key_configured === false && (
              <Col span={24} style={{ marginTop: 8 }}>
                <Alert
                  type="warning"
                  showIcon
                  message={
                    <>
                      Set <code>GOOGLE_SHEETS_API_KEY</code> in your backend .env to enable
                      multi-tab sync. Without it, only the first sheet tab (gid=0) is synced.
                    </>
                  }
                />
              </Col>
            )}
          </Row>
        )}
      </Card>

      {/* Summary stats */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        {[
          { title: 'Total Meta Leads', value: total,        icon: <TeamOutlined />,        color: '#1877f2' },
          { title: 'Ad Sets',          value: adSetCount,   icon: <BarChartOutlined />,    color: '#8b5cf6' },
          { title: 'Fresh / Uncontacted', value: freshLeads, icon: <ClockCircleOutlined />, color: '#f59e0b' },
          { title: 'Enrolled',         value: enrolled,     icon: <DollarCircleOutlined />, color: '#10b981' },
          { title: 'Repeated Leads',   value: repeatedCount, icon: <RetweetOutlined />,     color: '#f97316' },
        ].map(({ title, value, icon, color }) => (
          <Col xs={12} sm={8} md={5} key={title}>
            <Card size="small">
              <Statistic
                title={<Space size={4}>{icon}<span>{title}</span></Space>}
                value={value}
                valueStyle={{ color, fontWeight: 700 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* Tabs: Ad Sets + All Leads + Repeated */}
      <Card>
        <Tabs
          defaultActiveKey="adsets"
          items={[
            {
              key: 'adsets',
              label: `Ad Sets (${adSetCount})`,
              children: (
                <Table
                  dataSource={adsets}
                  columns={adsetColumns}
                  rowKey="adset_name"
                  loading={adsetsLoading}
                  size="middle"
                  pagination={{ pageSize: 20, showSizeChanger: true }}
                  scroll={{ x: 1000 }}
                  locale={{ emptyText: 'No Meta leads synced yet. Click "Sync Now" to import.' }}
                />
              ),
            },
            {
              key: 'all',
              label: `All Meta Leads (${total})`,
              children: <AllMetaLeadsTable />,
            },
            {
              key: 'repeated',
              label: (
                <Space size={6}>
                  <RetweetOutlined />
                  <span>Repeated Leads</span>
                  {repeatedCount > 0 && (
                    <Badge count={repeatedCount} color="#f97316" overflowCount={999} />
                  )}
                </Space>
              ),
              children: <RepeatedLeadsTable />,
            },
          ]}
        />
      </Card>

      {/* Leads modal */}
      <AdSetLeadsModal
        adset={selectedAdset}
        open={!!selectedAdset}
        onClose={() => setSelectedAdset(null)}
      />
    </div>
  );
};

export default MetaLeadsPage;
