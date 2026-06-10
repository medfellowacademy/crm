import React, { useState } from 'react';
import {
  Table, Card, Button, Tag, Statistic, Row, Col, Space, Typography,
  Tooltip, Badge, Alert, Spin, Modal, message, Divider,
} from 'antd';
import {
  SyncOutlined, CheckCircleOutlined, ClockCircleOutlined,
  ExclamationCircleOutlined, InstagramOutlined, FacebookOutlined,
  BarChartOutlined, TeamOutlined, DollarCircleOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { sheetsAPI, leadsAPI } from '../api/api';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
dayjs.extend(relativeTime);

const { Title, Text } = Typography;

const SOURCE_ICON = {
  Instagram: <InstagramOutlined style={{ color: '#e1306c' }} />,
  Facebook: <FacebookOutlined style={{ color: '#1877f2' }} />,
};

const STATUS_COLORS = {
  New: 'blue',
  Interested: 'cyan',
  'Follow-up': 'orange',
  Enrolled: 'green',
  'Not Interested': 'red',
};

// ── Lead list modal ────────────────────────────────────────────────────────────
const AdSetLeadsModal = ({ adset, open, onClose }) => {
  const { data, isLoading } = useQuery({
    queryKey: ['adset-leads', adset],
    queryFn: () =>
      leadsAPI.getAll({ limit: 500, utm_medium: adset }).then(r => r.data?.leads || []),
    enabled: open && !!adset,
    staleTime: 2 * 60 * 1000,
  });

  const cols = [
    { title: 'Name', dataIndex: 'full_name', key: 'name', width: 160 },
    { title: 'Phone', dataIndex: 'phone', key: 'phone', width: 140 },
    { title: 'Email', dataIndex: 'email', key: 'email', ellipsis: true },
    {
      title: 'Course', dataIndex: 'course_interested', key: 'course',
      ellipsis: true, width: 200,
    },
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

// ── Main page ──────────────────────────────────────────────────────────────────
const MetaLeadsPage = () => {
  const queryClient = useQueryClient();
  const [selectedAdset, setSelectedAdset] = useState(null);

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['sheets-status'],
    queryFn: () => sheetsAPI.status().then(r => r.data),
    staleTime: 30 * 1000,
  });

  const { data: adsets = [], isLoading: adsetsLoading } = useQuery({
    queryKey: ['sheets-adsets'],
    queryFn: () => sheetsAPI.adsets().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  });

  const syncMutation = useMutation({
    mutationFn: () => sheetsAPI.sync(),
    onSuccess: (res) => {
      const d = res.data;
      message.success(
        `Sync complete — ${d.new_leads} new leads added, ${d.skipped} already existed.`
      );
      queryClient.invalidateQueries({ queryKey: ['sheets-status'] });
      queryClient.invalidateQueries({ queryKey: ['sheets-adsets'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (e) => message.error(`Sync failed: ${e?.response?.data?.detail || e.message}`),
  });

  // Totals
  const total      = adsets.reduce((s, a) => s + a.total,       0);
  const newLeads   = adsets.reduce((s, a) => s + a.new,         0);
  const enrolled   = adsets.reduce((s, a) => s + a.enrolled,    0);
  const adSetCount = adsets.length;

  const columns = [
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
      title: 'Total Leads',
      dataIndex: 'total',
      key: 'total',
      width: 100,
      sorter: (a, b) => a.total - b.total,
      defaultSortOrder: 'descend',
      render: v => <Tag color="blue" style={{ fontWeight: 700 }}>{v}</Tag>,
    },
    {
      title: 'New',
      dataIndex: 'new',
      key: 'new',
      width: 70,
      render: v => v > 0 ? <Badge count={v} color="#1677ff" /> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Interested',
      dataIndex: 'interested',
      key: 'interested',
      width: 90,
      render: v => v > 0 ? <Badge count={v} color="#06b6d4" /> : <Text type="secondary">0</Text>,
    },
    {
      title: 'Enrolled',
      dataIndex: 'enrolled',
      key: 'enrolled',
      width: 90,
      render: v => v > 0 ? <Badge count={v} color="#10b981" /> : <Text type="secondary">0</Text>,
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
          <Button
            type="primary"
            icon={<SyncOutlined spin={syncMutation.isPending} />}
            loading={syncMutation.isPending}
            onClick={() => syncMutation.mutate()}
            style={{ background: '#1877f2', borderColor: '#1877f2' }}
          >
            Sync Now
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
                  {status?.enabled
                    ? <CheckCircleOutlined style={{ color: '#10b981' }} />
                    : <ExclamationCircleOutlined style={{ color: '#f59e0b' }} />}
                  <Text strong>
                    {status?.enabled ? 'Sync active' : 'Not yet synced'}
                  </Text>
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Sheet ID: {status?.sheet_id || '—'}
                </Text>
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
          { title: 'Total Meta Leads', value: total, icon: <TeamOutlined />, color: '#1877f2' },
          { title: 'Ad Sets', value: adSetCount, icon: <BarChartOutlined />, color: '#8b5cf6' },
          { title: 'New / Uncontacted', value: newLeads, icon: <ClockCircleOutlined />, color: '#f59e0b' },
          { title: 'Enrolled', value: enrolled, icon: <DollarCircleOutlined />, color: '#10b981' },
        ].map(({ title, value, icon, color }) => (
          <Col xs={12} sm={6} key={title}>
            <Card>
              <Statistic
                title={<Space size={4}>{icon}<span>{title}</span></Space>}
                value={value}
                valueStyle={{ color, fontWeight: 700 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Divider orientation="left" style={{ marginBottom: 16 }}>
        Ad Sets ({adSetCount})
      </Divider>

      {/* Ad sets table */}
      <Card>
        <Table
          dataSource={adsets}
          columns={columns}
          rowKey="adset_name"
          loading={adsetsLoading}
          size="middle"
          pagination={{ pageSize: 20, showSizeChanger: true }}
          scroll={{ x: 900 }}
          locale={{ emptyText: 'No Meta leads synced yet. Click "Sync Now" to import.' }}
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
