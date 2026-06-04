import React, { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Table, Card, Row, Col, Input, Select, DatePicker, Spin, Empty, Tag,
  Button, Modal, Upload, Space, Divider, Typography, Tooltip, message,
  Descriptions, Badge, Progress,
} from 'antd';
import {
  DollarSign, Users, TrendingUp, FileText, Upload as UploadIcon,
  Eye, CheckCircle, Clock, AlertCircle,
} from 'lucide-react';
import {
  UploadOutlined, FilePdfOutlined, FileImageOutlined,
  EyeOutlined, PlusOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import isBetween from 'dayjs/plugin/isBetween';
import { leadsAPI, uploadAPI } from '../api/api';
import EnrollmentModal from '../components/leads/EnrollmentModal';
import { useAuth } from '../context/AuthContext';

dayjs.extend(isBetween);

const { Text, Title } = Typography;
const fmt = v => `₹${Number(v || 0).toLocaleString('en-IN')}`;

// Safe JSON parse — emi_details / lms_modules may arrive as string from Supabase JSONB
const safeParse = (val, fallback = []) => {
  if (!val) return fallback;
  if (Array.isArray(val)) return val;
  try { return JSON.parse(val); } catch { return fallback; }
};

const LMS_STATUS_COLOR = {
  'Not Started': 'default',
  'Active':      'processing',
  'On Hold':     'warning',
  'Completed':   'success',
};

// ── EMI Status Badge ─────────────────────────────────────────────────────────
const EmiStatus = ({ status }) => {
  const cfg = {
    paid:    { color: 'success',    label: 'Paid'    },
    pending: { color: 'processing', label: 'Pending' },
    overdue: { color: 'error',      label: 'Overdue' },
  }[status] || { color: 'default', label: status || '—' };
  return <Badge status={cfg.color} text={cfg.label} />;
};

// ── Expanded Row ─────────────────────────────────────────────────────────────
const ExpandedRow = ({ lead, onUpload, uploading }) => {
  const emis       = safeParse(lead.emi_details, []);
  const lmsModules = safeParse(lead.lms_modules, []);
  const total      = lead.actual_revenue    || 0;
  const reg        = lead.registration_fees || 0;
  const emiPaid    = emis.filter(e => e.status === 'paid').reduce((s, e) => s + (Number(e.amount) || 0), 0);
  const collected  = reg + emiPaid;
  const remaining  = Math.max(0, total - collected);
  const pct = total > 0 ? Math.round((collected / total) * 100) : 0;

  return (
    <div style={{ padding: '12px 24px', background: '#f9fafb' }}>
      <Row gutter={24}>

        {/* Payment Summary */}
        <Col xs={24} md={10}>
          <Title level={5} style={{ marginBottom: 12 }}>Payment Summary</Title>
          <Descriptions size="small" column={1} bordered
            labelStyle={{ width: 160, background: '#f3f4f6' }}>
            <Descriptions.Item label="Total Course Fee">{fmt(total)}</Descriptions.Item>
            <Descriptions.Item label="Registration / Advance">{fmt(reg)}</Descriptions.Item>
            <Descriptions.Item label="EMI Collected">{fmt(emiPaid)}</Descriptions.Item>
            <Descriptions.Item label="Total Collected">
              <Text strong style={{ color: '#2563eb' }}>{fmt(collected)}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Balance Due">
              <Text strong style={{ color: remaining > 0 ? '#dc2626' : '#059669' }}>{fmt(remaining)}</Text>
            </Descriptions.Item>
          </Descriptions>
          <Progress
            percent={pct} strokeColor={pct === 100 ? '#10b981' : '#3b82f6'}
            style={{ marginTop: 12 }}
            format={p => `${p}% collected`}
          />
        </Col>

        {/* EMI Schedule */}
        <Col xs={24} md={8}>
          <Title level={5} style={{ marginBottom: 12 }}>EMI Schedule ({emis.length})</Title>
          {emis.length === 0
            ? <Text type="secondary">No EMIs — full payment</Text>
            : emis.map((emi, i) => (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '6px 0', borderBottom: '1px solid #e5e7eb',
              }}>
                <span style={{ fontSize: 13 }}>
                  {emi.date ? dayjs(emi.date).format('DD MMM YYYY') : `EMI ${i + 1}`}
                </span>
                <Text strong style={{ fontSize: 13 }}>{fmt(emi.amount)}</Text>
                <EmiStatus status={emi.status} />
              </div>
            ))
          }
        </Col>

        {/* Documents */}
        <Col xs={24} md={6}>
          <Title level={5} style={{ marginBottom: 12 }}>Documents</Title>

          {/* Payment Receipt */}
          <div style={{ marginBottom: 12 }}>
            <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
              Payment Receipt
            </Text>
            {lead.payment_receipt_url
              ? <Space>
                  <Button size="small" icon={<EyeOutlined />} type="link"
                    href={lead.payment_receipt_url} target="_blank">View</Button>
                  <Upload showUploadList={false}
                    customRequest={({ file }) => onUpload(lead.lead_id, file, 'receipt')}>
                    <Button size="small" icon={<UploadOutlined />}
                      loading={uploading === `${lead.lead_id}-receipt`}>Replace</Button>
                  </Upload>
                </Space>
              : <Upload showUploadList={false}
                  customRequest={({ file }) => onUpload(lead.lead_id, file, 'receipt')}>
                  <Button size="small" icon={<UploadOutlined />} type="dashed"
                    loading={uploading === `${lead.lead_id}-receipt`}>
                    Upload Receipt
                  </Button>
                </Upload>
            }
          </div>

          {/* Doctor Documents */}
          <div>
            <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
              Doctor Documents
            </Text>
            {safeParse(lead.documents, []).map((doc, i) => (
              <div key={i} style={{ marginBottom: 4 }}>
                <Button size="small" icon={<EyeOutlined />} type="link"
                  href={doc.url} target="_blank">
                  {doc.name || `Document ${i + 1}`}
                </Button>
              </div>
            ))}
            <Upload showUploadList={false}
              customRequest={({ file }) => onUpload(lead.lead_id, file, 'document')}>
              <Button size="small" icon={<PlusOutlined />} type="dashed"
                loading={uploading === `${lead.lead_id}-document`}>
                Add Document
              </Button>
            </Upload>
          </div>
        </Col>

        {/* LMS Status & Modules */}
        <Col xs={24} style={{ marginTop: 16 }}>
          <Title level={5} style={{ marginBottom: 10 }}>LMS Access</Title>
          <Space size={16} wrap>
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>LMS Status </Text>
              <Badge
                status={LMS_STATUS_COLOR[lead.lms_status] || 'default'}
                text={lead.lms_status || 'Not Set'}
              />
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>Modules Unlocked </Text>
              {lmsModules.length === 0
                ? <Text type="secondary">None</Text>
                : lmsModules.map(m => (
                    <Tag key={m} color="blue" style={{ marginBottom: 2 }}>{m}</Tag>
                  ))
              }
            </div>
          </Space>
        </Col>

      </Row>
    </div>
  );
};

// ── Main Page ────────────────────────────────────────────────────────────────
const PaymentsPage = () => {
  const queryClient = useQueryClient();
  const { user: authUser } = useAuth();
  const isCounselor = authUser?.role === 'Counselor';

  const [searchText,      setSearchText]      = useState('');
  const [filterCounselor, setFilterCounselor] = useState(null);
  const [filterCourse,    setFilterCourse]    = useState(null);
  const [dateRange,       setDateRange]       = useState([null, null]);
  const [uploading,       setUploading]       = useState(null);
  const [editLead,        setEditLead]        = useState(null);

  // Counselors only see their own enrolled leads
  const queryParams = {
    status: 'Enrolled',
    limit: 10000,
    ...(isCounselor && authUser?.full_name
      ? { assigned_to: authUser.full_name }
      : {}),
  };

  const { data: leadsResponse, isLoading } = useQuery({
    queryKey: ['enrolled-leads', isCounselor ? authUser?.full_name : 'all'],
    queryFn: () => leadsAPI.getAll(queryParams).then(r => r.data),
  });

  const updateMutation = useMutation({
    mutationFn: ({ leadId, data }) => leadsAPI.update(leadId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['enrolled-leads'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      setEditLead(null);
      message.success('Payment details updated');
    },
  });

  const leads = leadsResponse?.leads || (Array.isArray(leadsResponse) ? leadsResponse : []);

  const filtered = leads.filter(l => {
    if (searchText && !l.full_name?.toLowerCase().includes(searchText.toLowerCase()) &&
        !l.phone?.includes(searchText)) return false;
    if (filterCounselor && l.assigned_to !== filterCounselor) return false;
    if (filterCourse    && l.course_interested !== filterCourse) return false;
    if (dateRange[0] && dateRange[1]) {
      const d = dayjs(l.updated_at || l.created_at);
      if (!d.isBetween(dateRange[0], dateRange[1], 'day', '[]')) return false;
    }
    return true;
  });

  // Summary stats
  const totalRevenue  = filtered.reduce((s, l) => s + (l.actual_revenue || 0), 0);
  const totalRegFees  = filtered.reduce((s, l) => s + (l.registration_fees || 0), 0);
  const totalBalance  = filtered.reduce((s, l) => {
    const emPaid = (Array.isArray(l.emi_details) ? l.emi_details : [])
      .filter(e => e.status === 'paid').reduce((a, e) => a + (Number(e.amount) || 0), 0);
    return s + Math.max(0, (l.actual_revenue || 0) - ((l.registration_fees || 0) + emPaid));
  }, 0);

  const counselors = [...new Set(leads.map(l => l.assigned_to).filter(Boolean))];
  const courses    = [...new Set(leads.map(l => l.course_interested).filter(Boolean))];

  const handleUpload = async (leadId, file, docType) => {
    const key = `${leadId}-${docType}`;
    setUploading(key);
    try {
      await uploadAPI.uploadLeadDocument(leadId, file, docType);
      queryClient.invalidateQueries({ queryKey: ['enrolled-leads'] });
      message.success(`${docType === 'receipt' ? 'Receipt' : 'Document'} uploaded`);
    } catch {
      message.error('Upload failed');
    } finally {
      setUploading(null);
    }
  };

  const columns = [
    {
      title: 'Name',
      dataIndex: 'full_name',
      key: 'full_name',
      render: (t, r) => (
        <div>
          <div style={{ fontWeight: 600 }}>{t}</div>
          <div style={{ fontSize: 12, color: '#6b7280' }}>{r.phone}</div>
        </div>
      ),
    },
    {
      title: 'Course',
      dataIndex: 'course_interested',
      key: 'course_interested',
      render: t => <Tag color="blue" style={{ whiteSpace: 'normal', maxWidth: 180 }}>{t || '—'}</Tag>,
    },
    {
      title: 'Country',
      dataIndex: 'country',
      key: 'country',
      render: t => t || '—',
    },
    {
      title: 'Total Fee',
      dataIndex: 'actual_revenue',
      key: 'actual_revenue',
      render: v => v ? <Text strong style={{ color: '#059669' }}>{fmt(v)}</Text> : <Text type="secondary">—</Text>,
      sorter: (a, b) => (a.actual_revenue || 0) - (b.actual_revenue || 0),
      defaultSortOrder: 'descend',
    },
    {
      title: 'Registration',
      dataIndex: 'registration_fees',
      key: 'registration_fees',
      render: v => v ? <Text style={{ color: '#2563eb' }}>{fmt(v)}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Balance Due',
      key: 'balance',
      render: (_, r) => {
        const emiPaid = (Array.isArray(r.emi_details) ? r.emi_details : [])
          .filter(e => e.status === 'paid').reduce((s, e) => s + (Number(e.amount) || 0), 0);
        const bal = Math.max(0, (r.actual_revenue || 0) - ((r.registration_fees || 0) + emiPaid));
        return bal > 0
          ? <Text strong style={{ color: '#dc2626' }}>{fmt(bal)}</Text>
          : <Tag color="green">Cleared</Tag>;
      },
    },
    {
      title: 'EMIs',
      key: 'emis',
      render: (_, r) => {
        const emis = Array.isArray(r.emi_details) ? r.emi_details : [];
        if (!emis.length) return <Text type="secondary">—</Text>;
        const paid = emis.filter(e => e.status === 'paid').length;
        return <Text>{paid}/{emis.length} paid</Text>;
      },
    },
    {
      title: 'Docs',
      key: 'docs',
      render: (_, r) => {
        const hasReceipt = !!r.payment_receipt_url;
        const docCount   = (Array.isArray(r.documents) ? r.documents : []).length;
        return (
          <Space size={4}>
            <Tooltip title={hasReceipt ? 'Receipt uploaded' : 'No receipt'}>
              <FilePdfOutlined style={{ color: hasReceipt ? '#10b981' : '#d1d5db', fontSize: 16 }} />
            </Tooltip>
            {docCount > 0 && <Tag>{docCount} doc{docCount > 1 ? 's' : ''}</Tag>}
          </Space>
        );
      },
    },
    {
      title: 'Enrolled',
      dataIndex: 'updated_at',
      key: 'enrolled_at',
      render: d => d ? dayjs(d).format('DD MMM YYYY') : '—',
      sorter: (a, b) => dayjs(a.updated_at).unix() - dayjs(b.updated_at).unix(),
    },
    ...(!isCounselor ? [{
      title: 'Counselor',
      dataIndex: 'assigned_to',
      key: 'counselor',
      render: t => t || <Text type="secondary">Unassigned</Text>,
    }] : []),
    {
      title: 'LMS Status',
      dataIndex: 'lms_status',
      key: 'lms_status',
      render: v => v
        ? <Badge status={LMS_STATUS_COLOR[v] || 'default'} text={v} />
        : <Text type="secondary">—</Text>,
    },
    {
      title: 'Modules',
      dataIndex: 'lms_modules',
      key: 'lms_modules',
      render: v => {
        const mods = safeParse(v, []);
        if (!mods.length) return <Text type="secondary">—</Text>;
        return (
          <Space size={2} wrap>
            {mods.map(m => <Tag key={m} color="blue" style={{ marginBottom: 0 }}>{m}</Tag>)}
          </Space>
        );
      },
    },
    {
      title: '',
      key: 'actions',
      render: (_, r) => (
        <Button size="small" type="link" onClick={() => setEditLead(r)}>
          Edit Payment
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, marginBottom: 4 }}>Enrolled Leads & Payments</h1>
        <p style={{ color: 'var(--text-secondary)' }}>
          {isCounselor
            ? `Your enrolled leads — ${authUser?.full_name}`
            : 'Track fees, EMI schedules and documents for all enrolled leads'}
        </p>
      </div>

      {/* Summary Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {[
          { label: 'Total Revenue',     value: `₹${(totalRevenue/100000).toFixed(1)}L`,   bg: 'linear-gradient(135deg,#10b981,#059669)', Icon: DollarSign },
          { label: 'Total Enrolled',    value: filtered.length,                           bg: 'linear-gradient(135deg,#3b82f6,#2563eb)', Icon: Users },
          { label: 'Collected',         value: `₹${((totalRevenue-totalBalance)/100000).toFixed(1)}L`, bg: 'linear-gradient(135deg,#8b5cf6,#7c3aed)', Icon: TrendingUp },
          { label: 'Balance Pending',   value: `₹${(totalBalance/100000).toFixed(1)}L`,  bg: 'linear-gradient(135deg,#f59e0b,#d97706)', Icon: FileText },
        ].map(({ label, value, bg, Icon }) => (
          <Col xs={24} sm={12} lg={6} key={label}>
            <Card style={{ background: bg, color: 'white', borderRadius: 12, border: 'none' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                <div>
                  <div style={{ fontSize: 12, opacity: 0.9, marginBottom: 8 }}>{label}</div>
                  <div style={{ fontSize: 26, fontWeight: 700 }}>{value}</div>
                </div>
                <Icon size={32} opacity={0.3} />
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* Filters */}
      <Card style={{ marginBottom: 20, borderRadius: 12 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 12 }}>
          <Input placeholder="Search name / phone…" value={searchText}
            onChange={e => setSearchText(e.target.value)} />
          {!isCounselor && (
            <Select placeholder="Counselor" value={filterCounselor} onChange={setFilterCounselor}
              allowClear options={counselors.map(c => ({ label: c, value: c }))} />
          )}
          <Select placeholder="Course" value={filterCourse} onChange={setFilterCourse}
            allowClear showSearch options={courses.map(c => ({ label: c, value: c }))} />
          <DatePicker.RangePicker value={dateRange} onChange={setDateRange} />
        </div>
      </Card>

      {/* Table */}
      <Card style={{ borderRadius: 12 }}>
        {isLoading
          ? <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>
          : filtered.length === 0
            ? <Empty description="No enrolled leads found" />
            : (
              <Table
                columns={columns}
                dataSource={filtered.map(l => ({ ...l, key: l.lead_id || l.id }))}
                pagination={{ pageSize: 15, showSizeChanger: true }}
                scroll={{ x: 1100 }}
                expandable={{
                  expandedRowRender: r => (
                    <ExpandedRow lead={r} onUpload={handleUpload} uploading={uploading} />
                  ),
                }}
              />
            )
        }
      </Card>

      {/* Edit Payment Modal */}
      <EnrollmentModal
        open={!!editLead}
        lead={editLead}
        loading={updateMutation.isPending}
        onCancel={() => setEditLead(null)}
        onSave={data => updateMutation.mutate({ leadId: editLead.lead_id, data })}
      />
    </div>
  );
};

export default PaymentsPage;
