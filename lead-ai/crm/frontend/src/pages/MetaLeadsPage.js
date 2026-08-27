import React, { useState, useEffect, useRef } from 'react';
import {
  Table, Card, Button, Tag, Statistic, Row, Col, Space, Typography,
  Tooltip, Badge, Alert, Spin, Modal, message, Tabs, DatePicker, Select, Switch,
} from 'antd';
import {
  SyncOutlined, CheckCircleOutlined, ClockCircleOutlined,
  ExclamationCircleOutlined, InstagramOutlined, FacebookOutlined,
  BarChartOutlined, TeamOutlined, DollarCircleOutlined,
  MergeCellsOutlined, RetweetOutlined, CalendarOutlined,
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
  Facebook:  <FacebookOutlined  style={{ color: '#1877f2' }} />,
};

const STATUS_COLORS = {
  Fresh: 'blue', New: 'blue', Interested: 'cyan',
  'Follow-up': 'orange', Enrolled: 'green',
  'Not Interested': 'red', Hot: 'red', Warm: 'orange',
  'Will Enroll Later': 'gold', Dropped: 'volcano',
  'TMT No Response': 'gold', 'Re-assigned Lead': 'geekblue', 'Test Lead': 'default',
};

// ── helpers ────────────────────────────────────────────────────────────────────
const fmtDate = (v) => {
  if (!v) return '—';
  const d = dayjs(v);
  const today = dayjs().format('YYYY-MM-DD');
  const yesterday = dayjs().subtract(1, 'day').format('YYYY-MM-DD');
  const dateStr = d.format('YYYY-MM-DD');
  if (dateStr === today)     return 'Today';
  if (dateStr === yesterday) return 'Yesterday';
  return d.format('DD MMM YYYY');
};

// ── Adset leads modal ──────────────────────────────────────────────────────────
const AdSetLeadsModal = ({ adset, open, onClose }) => {
  const { data, isLoading } = useQuery({
    queryKey: ['adset-leads', adset],
    queryFn: () => leadsAPI.getAll({ limit: 1000, adset_name: adset }).then(r => r.data?.leads || []),
    enabled: open && !!adset,
    staleTime: 2 * 60 * 1000,
  });

  const cols = [
    { title: 'Name',   dataIndex: 'full_name',        key: 'name',   width: 160 },
    { title: 'Phone',  dataIndex: 'phone',             key: 'phone',  width: 140 },
    { title: 'Email',  dataIndex: 'email',             key: 'email',  ellipsis: true },
    { title: 'Course', dataIndex: 'course_interested', key: 'course', ellipsis: true, width: 200 },
    { title: 'Status', dataIndex: 'status', key: 'status', width: 110,
      render: s => <Tag color={STATUS_COLORS[s] || 'default'}>{s}</Tag> },
    { title: 'Received', dataIndex: 'created_at', key: 'at', width: 120,
      render: v => v ? dayjs(v).fromNow() : '—' },
  ];

  return (
    <Modal title={<Space><TeamOutlined /><span>Leads — {adset}</span></Space>}
      open={open} onCancel={onClose} footer={null} width={900}>
      {isLoading
        ? <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        : <Table dataSource={data || []} columns={cols} rowKey="lead_id"
            size="small" pagination={{ pageSize: 20 }} scroll={{ x: 800 }} />}
    </Modal>
  );
};

// ── Daily drilldown modal ──────────────────────────────────────────────────────
const DailyLeadsModal = ({ date, adset, open, onClose }) => {
  const { data, isLoading } = useQuery({
    queryKey: ['daily-drilldown', date, adset],
    queryFn: () => leadsAPI.getAll({
      limit: 500,
      adset_name: adset,
      created_from: `${date}T00:00:00+05:30`,
      created_to:   `${date}T23:59:59+05:30`,
    }).then(r => r.data?.leads || []),
    enabled: open && !!date && !!adset,
    staleTime: 2 * 60 * 1000,
  });

  const repeated = (data || []).filter(r => r.is_repeated).length;

  const cols = [
    { title: 'Name',   dataIndex: 'full_name', key: 'name', width: 160,
      render: v => <Text strong>{v}</Text> },
    { title: 'Phone',  dataIndex: 'phone', key: 'phone', width: 140 },
    { title: 'Email',  dataIndex: 'email', key: 'email', ellipsis: true },
    { title: 'Course', dataIndex: 'course_interested', key: 'course', ellipsis: true, width: 180 },
    { title: 'Status', dataIndex: 'status', key: 'status', width: 100,
      render: s => <Tag color={STATUS_COLORS[s] || 'default'}>{s}</Tag> },
    { title: 'Repeated', dataIndex: 'is_repeated', key: 'rep', width: 95,
      render: v => v ? <Tag color="orange" icon={<RetweetOutlined />}>Repeated</Tag> : '—' },
    { title: 'Owner', dataIndex: 'assigned_to', key: 'owner', width: 140,
      render: v => v ? <Tag color="geekblue">{v}</Tag> : <Text type="secondary">—</Text> },
  ];

  return (
    <Modal
      title={
        <Space>
          <CalendarOutlined />
          <span>Leads on {date ? dayjs(date).format('DD MMM YYYY') : ''}</span>
          {adset && <Tag color="purple">{adset}</Tag>}
        </Space>
      }
      open={open} onCancel={onClose} footer={null} width={1050}
    >
      {isLoading
        ? <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        : <>
            <Space style={{ marginBottom: 10 }}>
              <Text type="secondary">{(data || []).length} leads total</Text>
              {repeated > 0 && <Tag color="orange">{repeated} repeated</Tag>}
            </Space>
            <Table
              dataSource={data || []} columns={cols} rowKey="lead_id"
              size="small" pagination={{ pageSize: 25 }} scroll={{ x: 900 }}
              rowClassName={r => r.is_repeated ? 'ant-table-row-warning' : ''}
            />
          </>}
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
        created_to:   dateRange[1].endOf('day').toISOString(),
      } : {}),
    }).then(r => r.data?.leads || []),
    staleTime: 2 * 60 * 1000,
  });

  const cols = [
    { title: 'Name',   dataIndex: 'full_name', key: 'name', width: 160,
      render: v => <Text strong>{v}</Text> },
    { title: 'Phone',  dataIndex: 'phone',  key: 'phone',  width: 145 },
    { title: 'Email',  dataIndex: 'email',  key: 'email',  ellipsis: true },
    { title: 'Course', dataIndex: 'course_interested', key: 'course', ellipsis: true, width: 200 },
    { title: 'Ad Set', dataIndex: 'adset_name', key: 'adset', ellipsis: true, width: 180,
      render: v => v ? <Tag color="purple">{v}</Tag> : '—' },
    { title: 'Source', dataIndex: 'source', key: 'source', width: 100,
      render: v => <Space size={4}>{SOURCE_ICON[v]}<span>{v}</span></Space> },
    { title: 'Status', dataIndex: 'status', key: 'status', width: 100,
      render: s => <Tag color={STATUS_COLORS[s] || 'default'}>{s}</Tag> },
    { title: 'Received', dataIndex: 'created_at', key: 'recv', width: 120,
      render: v => v ? dayjs(v).fromNow() : '—' },
  ];

  return (
    <>
      <div style={{ marginBottom: 12 }}>
        <DatePicker.RangePicker
          value={dateRange}
          onChange={v => setDateRange(v || [null, null])}
          allowClear placeholder={['Received from', 'to']}
        />
      </div>
      <Table
        dataSource={data || []} columns={cols} rowKey="lead_id"
        loading={isLoading} size="small"
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
      title: 'Lead', key: 'lead', width: 200,
      render: (_, r) => (
        <div>
          <Text strong>{r.full_name}</Text>
          <div style={{ fontSize: 12, color: '#6b7280' }}>{r.email || r.phone}</div>
        </div>
      ),
    },
    {
      title: 'Owner', dataIndex: 'assigned_to', key: 'owner', width: 150,
      render: v => v
        ? <Tag color="geekblue" style={{ fontWeight: 600 }}>{v}</Tag>
        : <Text type="secondary">Unassigned</Text>,
    },
    {
      title: 'First Submission', key: 'first', width: 230,
      render: (_, r) => (
        <div>
          <Tag color="purple" style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {r.adset_name || 'Unknown adset'}
          </Tag>
          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>{r.campaign_name || ''}</div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 1 }}>
            {r.created_at ? dayjs(r.created_at).format('DD MMM YYYY') : '—'}
          </div>
        </div>
      ),
    },
    {
      title: 'Latest Re-submission', key: 'latest', width: 250,
      render: (_, r) => r.last_submission_adset ? (
        <div>
          <Tag color="volcano" style={{ maxWidth: 215, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {r.last_submission_adset}
          </Tag>
          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>{r.last_submission_campaign || ''}</div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 1 }}>
            {r.last_submission_tab ? `Tab: ${r.last_submission_tab}` : ''}
            {r.last_submission_date ? ` · ${dayjs(r.last_submission_date).format('DD MMM YYYY')}` : ''}
          </div>
        </div>
      ) : <Text type="secondary">—</Text>,
    },
    {
      title: 'Submissions', dataIndex: 'submission_count', key: 'count', width: 105,
      sorter: (a, b) => (a.submission_count || 1) - (b.submission_count || 1),
      defaultSortOrder: 'descend',
      render: v => (
        <Badge count={v || 1} overflowCount={99}
          style={{ backgroundColor: (v || 1) >= 3 ? '#ef4444' : '#f59e0b', fontWeight: 700 }} />
      ),
    },
    {
      title: 'Status', dataIndex: 'status', key: 'status', width: 100,
      render: s => <Tag color={STATUS_COLORS[s] || 'default'}>{s}</Tag>,
    },
    { title: 'Course', dataIndex: 'course_interested', key: 'course', ellipsis: true, width: 180 },
    {
      title: '', key: 'action', width: 75,
      render: (_, r) => (
        <Button size="small" href={`/leads/${r.lead_id}`} target="_blank" rel="noopener noreferrer">
          View
        </Button>
      ),
    },
  ];

  return (
    <>
      {leads.length > 0 && (
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message={
            <>
              <Text strong>{leads.length} leads</Text> submitted via Meta ads more than once.
              Original owner and first ad set are preserved. Latest re-submission shown on the right.
            </>
          }
        />
      )}
      <Table
        dataSource={leads} columns={cols} rowKey="lead_id"
        loading={isLoading} size="small"
        pagination={{ pageSize: 25, showSizeChanger: true }}
        scroll={{ x: 1250 }}
        locale={{ emptyText: 'No repeated leads yet. Leads who submit via multiple Meta ads will appear here.' }}
      />
    </>
  );
};

// ── Daily Breakdown tab ────────────────────────────────────────────────────────
const DailyBreakdownTab = ({ adsets }) => {
  const [dateRange, setDateRange] = useState([dayjs().subtract(29, 'day'), dayjs()]);
  const [selectedAdset, setSelectedAdset]       = useState(null);
  const [selectedPlatform, setSelectedPlatform] = useState(null);
  const [showRepeatedOnly, setShowRepeatedOnly] = useState(false);
  const [drilldown, setDrilldown]               = useState(null); // {date, adset}

  const params = {
    date_from: dateRange[0]?.format('YYYY-MM-DD'),
    date_to:   dateRange[1]?.format('YYYY-MM-DD'),
    ...(selectedAdset    ? { adset_name: selectedAdset }    : {}),
    ...(selectedPlatform ? { platform: selectedPlatform }   : {}),
  };

  const { data, isLoading } = useQuery({
    queryKey: ['daily-stats', params],
    queryFn: () => sheetsAPI.dailyStats(params).then(r => r.data),
    staleTime: 2 * 60 * 1000,
    enabled: !!(dateRange[0] && dateRange[1]),
  });

  const rows = (data?.rows || []).filter(r => !showRepeatedOnly || r.repeated > 0);
  const summary = data?.summary || {};

  const adsetOptions = adsets.map(a => ({ label: a.adset_name, value: a.adset_name }));

  const cols = [
    {
      title: 'Date', dataIndex: 'date', key: 'date', width: 130,
      sorter: (a, b) => a.date.localeCompare(b.date),
      defaultSortOrder: 'descend',
      render: v => (
        <div>
          <Text strong>{fmtDate(v)}</Text>
          <div style={{ fontSize: 11, color: '#9ca3af' }}>{dayjs(v).format('ddd, DD MMM')}</div>
        </div>
      ),
    },
    {
      title: 'Ad Set', dataIndex: 'adset_name', key: 'adset',
      render: v => (
        <Tag color="purple" style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {v}
        </Tag>
      ),
    },
    {
      title: 'Campaign', dataIndex: 'campaign_name', key: 'campaign', ellipsis: true,
      render: v => v ? <Text type="secondary">{v}</Text> : '—',
    },
    {
      title: 'Platform', dataIndex: 'source', key: 'source', width: 120,
      render: v => <Space size={4}>{SOURCE_ICON[v]}<span>{v || 'Meta'}</span></Space>,
    },
    {
      title: 'New Leads', dataIndex: 'new_leads', key: 'new', width: 100,
      sorter: (a, b) => a.new_leads - b.new_leads,
      render: v => v > 0
        ? <Badge count={v} color="#1677ff" overflowCount={999} />
        : <Text type="secondary">0</Text>,
    },
    {
      title: 'Repeated', dataIndex: 'repeated', key: 'rep', width: 95,
      sorter: (a, b) => a.repeated - b.repeated,
      render: v => v > 0
        ? <Badge count={v} color="#f97316" overflowCount={999} />
        : <Text type="secondary">0</Text>,
    },
    {
      title: 'Total', dataIndex: 'total', key: 'total', width: 80,
      sorter: (a, b) => a.total - b.total,
      render: v => <Tag color="blue" style={{ fontWeight: 700 }}>{v}</Tag>,
    },
    {
      title: '', key: 'view', width: 75,
      render: (_, r) => (
        <Button size="small" onClick={() => setDrilldown({ date: r.date, adset: r.adset_name })}>
          Leads
        </Button>
      ),
    },
  ];

  return (
    <>
      {/* Summary cards */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        {[
          { label: 'Today',       key: 'today'        },
          { label: 'Last 7 Days', key: 'last_7_days'  },
          { label: 'Last 30 Days',key: 'last_30_days' },
        ].map(({ label, key }) => {
          const d = summary[key] || {};
          return (
            <Col span={8} key={label}>
              <Card size="small" style={{ background: '#fafafa', borderRadius: 8 }}>
                <Text strong style={{ display: 'block', marginBottom: 6, fontSize: 13 }}>{label}</Text>
                <Space wrap>
                  <Tag color="blue"   style={{ fontWeight: 600 }}>{d.new      || 0} New</Tag>
                  <Tag color="orange" style={{ fontWeight: 600 }}>{d.repeated || 0} Repeated</Tag>
                  <Tag style={{ fontWeight: 700, background: '#f0f4ff', color: '#1677ff', border: 'none' }}>
                    {d.total || 0} Total
                  </Tag>
                </Space>
              </Card>
            </Col>
          );
        })}
      </Row>

      {/* Filters */}
      <Space wrap style={{ marginBottom: 14 }}>
        <DatePicker.RangePicker
          value={dateRange}
          onChange={v => setDateRange(v || [dayjs().subtract(29, 'day'), dayjs()])}
          allowClear={false}
          presets={[
            { label: 'Today',       value: [dayjs(),                    dayjs()] },
            { label: 'Last 7 days', value: [dayjs().subtract(6,  'day'), dayjs()] },
            { label: 'Last 30 days',value: [dayjs().subtract(29, 'day'), dayjs()] },
            { label: 'Last 90 days',value: [dayjs().subtract(89, 'day'), dayjs()] },
          ]}
        />
        <Select
          placeholder="All Ad Sets"
          allowClear showSearch
          style={{ minWidth: 230 }}
          onChange={setSelectedAdset}
          value={selectedAdset}
          options={adsetOptions}
          filterOption={(input, opt) =>
            (opt?.label || '').toLowerCase().includes(input.toLowerCase())
          }
        />
        <Select
          placeholder="All Platforms"
          allowClear
          style={{ width: 150 }}
          onChange={setSelectedPlatform}
          value={selectedPlatform}
          options={[
            { label: 'Facebook',  value: 'Facebook'  },
            { label: 'Instagram', value: 'Instagram' },
          ]}
        />
        <Space size={6}>
          <Switch
            checked={showRepeatedOnly}
            onChange={setShowRepeatedOnly}
            size="small"
          />
          <Text style={{ fontSize: 13 }}>Repeated only</Text>
        </Space>
      </Space>

      {/* Table */}
      <Table
        dataSource={rows}
        columns={cols}
        rowKey={r => `${r.date}-${r.adset_name}`}
        loading={isLoading}
        size="small"
        pagination={{ pageSize: 30, showSizeChanger: true, showTotal: (t) => `${t} rows` }}
        scroll={{ x: 950 }}
        summary={pageData => {
          const totalNew = pageData.reduce((s, r) => s + (r.new_leads || 0), 0);
          const totalRep = pageData.reduce((s, r) => s + (r.repeated  || 0), 0);
          const totalAll = pageData.reduce((s, r) => s + (r.total     || 0), 0);
          return (
            <Table.Summary.Row style={{ background: '#fafafa', fontWeight: 600 }}>
              <Table.Summary.Cell colSpan={4}>
                <Text strong>Page Total</Text>
              </Table.Summary.Cell>
              <Table.Summary.Cell>
                <Text strong style={{ color: '#1677ff' }}>{totalNew}</Text>
              </Table.Summary.Cell>
              <Table.Summary.Cell>
                <Text strong style={{ color: '#f97316' }}>{totalRep}</Text>
              </Table.Summary.Cell>
              <Table.Summary.Cell>
                <Text strong>{totalAll}</Text>
              </Table.Summary.Cell>
              <Table.Summary.Cell />
            </Table.Summary.Row>
          );
        }}
        locale={{ emptyText: 'No leads found for the selected filters.' }}
      />

      <DailyLeadsModal
        date={drilldown?.date}
        adset={drilldown?.adset}
        open={!!drilldown}
        onClose={() => setDrilldown(null)}
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
      queryClient.invalidateQueries({ queryKey: ['daily-stats'] });
    } else if (prev === 'running' && curr === 'error') {
      message.error(`Sync failed: ${status.last_sync_error || 'Unknown error'}`);
    }
    prevSyncStatus.current = curr;
  }, [status, queryClient]);

  const cleanupMutation = useMutation({
    mutationFn: () => duplicatesAPI.cleanup(),
    onSuccess: (res) => {
      const d = res.data;
      if (d.error) { message.error(`Cleanup failed: ${d.error}`); return; }
      message.success(
        `Cleanup complete — ${d.deleted_leads} duplicate leads removed, ` +
        `${d.merged_groups} groups merged` +
        (d.still_repeated > 0 ? `, ${d.still_repeated} still flagged` : '')
      );
      queryClient.invalidateQueries({ queryKey: ['sheets-adsets'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['all-meta-leads'] });
      queryClient.invalidateQueries({ queryKey: ['repeated-leads'] });
      queryClient.invalidateQueries({ queryKey: ['daily-stats'] });
    },
    onError: (e) => message.error(`Cleanup failed: ${e?.response?.data?.detail || e.message}`),
  });

  const total      = adsets.reduce((s, a) => s + a.total,        0);
  const freshLeads = adsets.reduce((s, a) => s + (a.fresh || 0), 0);
  const enrolled   = adsets.reduce((s, a) => s + a.enrolled,     0);
  const adSetCount = adsets.length;

  const adsetColumns = [
    {
      title: 'Ad Set Name', dataIndex: 'adset_name', key: 'adset_name',
      render: v => <Text strong>{v || 'Unknown'}</Text>,
      sorter: (a, b) => (a.adset_name || '').localeCompare(b.adset_name || ''),
    },
    {
      title: 'Campaign', dataIndex: 'campaign_name', key: 'campaign', ellipsis: true,
      render: v => v ? <Text type="secondary">{v}</Text> : '—',
    },
    {
      title: 'Ad Name', dataIndex: 'ad_name', key: 'ad_name', ellipsis: true,
      render: v => v ? <Text style={{ fontSize: 12, color: '#6366f1' }}>{v}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Platform', dataIndex: 'source', key: 'source', width: 110,
      render: v => <Space size={4}>{SOURCE_ICON[v] || null}<span>{v || 'Meta'}</span></Space>,
    },
    {
      title: 'Total', dataIndex: 'total', key: 'total', width: 80,
      sorter: (a, b) => a.total - b.total, defaultSortOrder: 'descend',
      render: v => <Tag color="blue" style={{ fontWeight: 700 }}>{v}</Tag>,
    },
    { title: 'Fresh',      dataIndex: 'fresh',         key: 'fresh',    width: 70,
      render: v => (v || 0) > 0 ? <Badge count={v} color="#1677ff" /> : <Text type="secondary">0</Text> },
    { title: 'Follow Up',  dataIndex: 'follow_up',     key: 'follow_up',width: 90,
      render: v => (v || 0) > 0 ? <Badge count={v} color="#f59e0b" /> : <Text type="secondary">0</Text> },
    { title: 'Interested', dataIndex: 'interested',    key: 'interested',width: 90,
      render: v => (v || 0) > 0 ? <Badge count={v} color="#06b6d4" /> : <Text type="secondary">0</Text> },
    { title: 'Enrolled',   dataIndex: 'enrolled',      key: 'enrolled', width: 80,
      render: v => (v || 0) > 0 ? <Badge count={v} color="#10b981" /> : <Text type="secondary">0</Text> },
    { title: 'Not Int.',   dataIndex: 'not_interested',key: 'not_int',  width: 80,
      render: v => (v || 0) > 0 ? <Badge count={v} color="#ef4444" /> : <Text type="secondary">0</Text> },
    { title: 'Repeated',   dataIndex: 'repeated',      key: 'repeated', width: 90,
      render: v => (v || 0) > 0
        ? <Badge count={v} color="#f97316" style={{ fontWeight: 600 }} />
        : <Text type="secondary">0</Text> },
    {
      title: 'Latest Lead', dataIndex: 'latest', key: 'latest', width: 130,
      render: v => v ? (
        <Tooltip title={dayjs(v).format('DD MMM YYYY HH:mm')}>
          <Text type="secondary">{dayjs(v).fromNow()}</Text>
        </Tooltip>
      ) : '—',
    },
    {
      title: '', key: 'action', width: 75,
      render: (_, row) => (
        <Button size="small" onClick={() => setSelectedAdset(row.adset_name)}>View</Button>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>Meta Leads — Google Sheet Sync</Title>
          <Text type="secondary">Auto-imports leads from your connected Meta Lead Ads sheet into the CRM</Text>
        </div>
        <Space>
          {isAdmin && (
            <Button icon={<MergeCellsOutlined />} loading={cleanupMutation.isPending}
              onClick={() => cleanupMutation.mutate()}>
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
                    {status?.sync_status === 'running' ? 'Sync in progress…'
                      : status?.enabled ? 'Sync active' : 'Not yet synced'}
                  </Text>
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>Sheet ID: {status?.sheet_id || '—'}</Text>
                {status?.sync_status === 'completed' && status?.last_sync_stats && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Last result: {status.last_sync_stats.new_leads || 0} new,{' '}
                    {status.last_sync_stats.updated_leads || 0} updated,{' '}
                    {status.last_sync_stats.skipped || 0} skipped
                    {status.last_sync_stats.errors > 0 ? `, ${status.last_sync_stats.errors} errors` : ''}
                  </Text>
                )}
                {status?.sync_status === 'error' && status?.last_sync_error && (
                  <Text type="danger" style={{ fontSize: 12 }}>Last sync failed: {status.last_sync_error}</Text>
                )}
              </Space>
            </Col>
            <Col>
              <Space size={4}>
                <ClockCircleOutlined style={{ color: '#6b7280' }} />
                <Text type="secondary">
                  Last synced: {status?.last_synced_at ? dayjs(status.last_synced_at).fromNow() : 'Never'}
                </Text>
              </Space>
            </Col>
            {status?.api_key_configured === false && (
              <Col span={24} style={{ marginTop: 8 }}>
                <Alert type="warning" showIcon
                  message={<>Set <code>GOOGLE_SHEETS_API_KEY</code> in your backend .env to enable multi-tab sync.</>}
                />
              </Col>
            )}
          </Row>
        )}
      </Card>

      {/* Summary stats */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        {[
          { title: 'Total Meta Leads',   value: total,        icon: <TeamOutlined />,        color: '#1877f2' },
          { title: 'Ad Sets',            value: adSetCount,   icon: <BarChartOutlined />,    color: '#8b5cf6' },
          { title: 'Fresh / Uncontacted',value: freshLeads,   icon: <ClockCircleOutlined />, color: '#f59e0b' },
          { title: 'Enrolled',           value: enrolled,     icon: <DollarCircleOutlined />,color: '#10b981' },
          { title: 'Repeated Leads',     value: repeatedCount,icon: <RetweetOutlined />,     color: '#f97316' },
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

      {/* Tabs */}
      <Card>
        <Tabs
          defaultActiveKey="adsets"
          items={[
            {
              key: 'adsets',
              label: `Ad Sets (${adSetCount})`,
              children: (
                <Table
                  dataSource={adsets} columns={adsetColumns} rowKey="adset_name"
                  loading={adsetsLoading} size="middle"
                  pagination={{ pageSize: 20, showSizeChanger: true }}
                  scroll={{ x: 1250 }}
                  locale={{ emptyText: 'No Meta leads synced yet. Click "Sync Now" to import.' }}
                />
              ),
            },
            {
              key: 'daily',
              label: <Space size={4}><CalendarOutlined /><span>Daily Breakdown</span></Space>,
              children: <DailyBreakdownTab adsets={adsets} />,
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
                  {repeatedCount > 0 && <Badge count={repeatedCount} color="#f97316" overflowCount={999} />}
                </Space>
              ),
              children: <RepeatedLeadsTable />,
            },
          ]}
        />
      </Card>

      <AdSetLeadsModal
        adset={selectedAdset}
        open={!!selectedAdset}
        onClose={() => setSelectedAdset(null)}
      />
    </div>
  );
};

export default MetaLeadsPage;
