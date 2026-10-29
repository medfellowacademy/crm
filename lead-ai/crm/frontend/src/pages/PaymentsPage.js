import React, { useState, useRef, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Table, Card, Row, Col, Input, Select, DatePicker, Spin, Empty, Tag,
  Button, Modal, Upload, Space, Divider, Typography, Tooltip, message,
  Descriptions, Badge, Progress, Tabs, Alert, Result,
} from 'antd';
import {
  DollarSign, Users, TrendingUp, FileText, Upload as UploadIcon,
  Eye, CheckCircle, Clock, AlertCircle, AlertTriangle,
} from 'lucide-react';
import {
  UploadOutlined, FilePdfOutlined, FileImageOutlined,
  EyeOutlined, PlusOutlined, DownloadOutlined, CheckOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { leadsAPI, uploadAPI, paymentsAPI } from '../api/api';
import PayEmiModal from '../components/payments/PayEmiModal';
import CollectionsTab from '../components/payments/CollectionsTab';
import OverdueTab from '../components/payments/OverdueTab';
import EmiMonthTab from '../components/payments/EmiMonthTab';
import DropStudentModal from '../components/payments/DropStudentModal';
import DroppedTab from '../components/payments/DroppedTab';
import { PaymentActivity } from '../components/payments/PaymentComments';
import EnrollmentModal from '../components/leads/EnrollmentModal';
import { useAuth } from '../context/AuthContext';
import { fmt, safeParse, financeFor, instalmentLabel, PAYMENT_STATUS_CONFIG } from '../utils/finance';

const { Text, Title } = Typography;

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
    cancelled: { color: 'default',  label: 'Cancelled (dropped)' },
  }[status] || { color: 'default', label: status || '—' };
  return <Badge status={cfg.color} text={cfg.label} />;
};

// ── Expanded Row ─────────────────────────────────────────────────────────────
const ExpandedRow = ({ lead, onUpload, uploading, onMarkPaid }) => {
  const [showLog, setShowLog] = useState(false);
  const regPayments = safeParse(lead.registration_payments, []);
  const lmsModules  = safeParse(lead.lms_modules, []);
  const { total, reg, emis, emiPaid, collected, balance: remaining, pct, overdueAmount, scheduledPending, unscheduled, overScheduled } = financeFor(lead);
  const today = dayjs().startOf('day');

  return (
    <div style={{ padding: '12px 24px', background: '#f9fafb' }}>
      <Row gutter={24}>

        {/* Payment Summary */}
        <Col xs={24} md={10}>
          <Title level={5} style={{ marginBottom: 12 }}>Payment Summary</Title>
          <Descriptions size="small" column={1} bordered
            labelStyle={{ width: 160, background: '#f3f4f6' }}>
            <Descriptions.Item label="Total Course Fee">{fmt(total)}</Descriptions.Item>
            <Descriptions.Item label="Registration received">
              {fmt(reg)}
              {regPayments.length > 1 && (
                <span style={{ marginLeft: 8, fontSize: 12, color: '#6b7280' }}>
                  ({regPayments.length} payments)
                </span>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="Instalments received">{fmt(emiPaid)}</Descriptions.Item>
            <Descriptions.Item label="Total received">
              <Text strong style={{ color: '#2563eb' }}>{fmt(collected)}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Scheduled to come">{fmt(scheduledPending)}</Descriptions.Item>
            {unscheduled > 0.5 && (
              <Descriptions.Item label="Not scheduled">
                <Text strong style={{ color: '#d97706' }}>{fmt(unscheduled)}</Text>
                <div style={{ fontSize: 11, color: '#6b7280' }}>in no instalment, so no due date — use Edit Payment</div>
              </Descriptions.Item>
            )}
            {overScheduled > 0.5 && (
              <Descriptions.Item label="Over-scheduled">
                <Text strong style={{ color: '#dc2626' }}>{fmt(overScheduled)}</Text>
                <div style={{ fontSize: 11, color: '#6b7280' }}>received + scheduled is more than the fee</div>
              </Descriptions.Item>
            )}
            <Descriptions.Item label="Remaining to collect">
              <Text strong style={{ color: remaining > 0 ? '#dc2626' : '#059669' }}>{fmt(remaining)}</Text>
            </Descriptions.Item>
            {overdueAmount > 0 && (
              <Descriptions.Item label="Overdue">
                <Text strong style={{ color: '#dc2626' }}>
                  {fmt(overdueAmount)} <AlertTriangle size={13} style={{ verticalAlign: -2 }} />
                </Text>
              </Descriptions.Item>
            )}
          </Descriptions>
          <Progress
            percent={pct} strokeColor={pct === 100 ? '#10b981' : '#3b82f6'}
            style={{ marginTop: 12 }}
            format={p => `${p}% collected`}
          />
          {regPayments.length > 1 && (
            <div style={{ marginTop: 12 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>Registration Payments</Text>
              {regPayments.map((p, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between',
                  padding: '4px 0', borderBottom: '1px solid #e5e7eb', fontSize: 13,
                }}>
                  <span>{p.date ? dayjs(p.date).format('DD MMM YYYY') : `Payment ${i + 1}`}</span>
                  <Text strong>{fmt(p.amount)}</Text>
                </div>
              ))}
            </div>
          )}
        </Col>

        {/* EMI Schedule */}
        <Col xs={24} md={8}>
          <Title level={5} style={{ marginBottom: 12 }}>Instalments ({emis.length})</Title>
          {emis.length === 0
            ? <Text type="secondary">No instalments scheduled</Text>
            : emis.map((emi, i) => {
              const isOverdue = emi.status !== 'paid' && emi.status !== 'cancelled' && emi.date && dayjs(emi.date).isBefore(today);
              return (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '6px 8px', borderBottom: '1px solid #e5e7eb',
                  background: isOverdue ? '#fef2f2' : 'transparent',
                  borderRadius: 4,
                }}>
                  <span style={{ fontSize: 13 }}>
                    <b>{instalmentLabel(emis, i)}</b>
                    <div style={{ fontSize: 12, color: '#6b7280' }}>{emi.date ? dayjs(emi.date).format('DD MMM YYYY') : 'No due date'}</div>
                  </span>
                  <Text strong style={{ fontSize: 13 }}>
                    {fmt(emi.status === 'paid' && emi.paid_amount != null ? emi.paid_amount : emi.amount)}
                    {emi.status === 'paid' && emi.paid_amount != null && Number(emi.paid_amount) !== Number(emi.amount) && (
                      <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 400 }}>of {fmt(emi.amount)}</div>
                    )}
                  </Text>
                  {isOverdue
                    ? <Badge status="error" text={<Text type="danger" style={{ fontSize: 12 }}>Overdue</Text>} />
                    : <EmiStatus status={emi.status} />}
                  {emi.status !== 'paid' && emi.status !== 'cancelled' && (
                    <Button size="small" type="link" icon={<CheckOutlined />} style={{ padding: 0 }}
                      onClick={() => onMarkPaid({ leadId: lead.lead_id, index: i, name: lead.full_name, amount: emi.amount, dueDate: emi.date, label: instalmentLabel(emis, i) })}>
                      Mark paid
                    </Button>
                  )}
                  {emi.status === 'paid' && emi.paid_date && (
                    <Text type="secondary" style={{ fontSize: 11 }}>on {dayjs(emi.paid_date).format('DD MMM')}{emi.method ? ` · ${emi.method}` : ''}</Text>
                  )}
                </div>
              );
            })
          }
          <div style={{ marginTop: 12 }}>
            <Button size="small" type="link" style={{ padding: 0 }} onClick={() => setShowLog(v => !v)}>
              {showLog ? 'Hide' : 'Show'} payment comments &amp; log
            </Button>
            {showLog && <div style={{ marginTop: 6 }}><PaymentActivity leadId={lead.lead_id} compact /></div>}
          </div>
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
            <Upload showUploadList={false} multiple
              customRequest={({ file }) => onUpload(lead.lead_id, file, 'document')}>
              <Button size="small" icon={<PlusOutlined />} type="dashed"
                loading={uploading === `${lead.lead_id}-document`}>
                Add Document(s)
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
  const [filterStatus,    setFilterStatus]    = useState(null);
  const [dateRange,       setDateRange]       = useState([null, null]);
  const [uploading,       setUploading]       = useState(null);
  const [editLead,        setEditLead]        = useState(null);
  const [dropLead,        setDropLead]        = useState(null);
  const [payTarget,       setPayTarget]       = useState(null);
  const [tab,             setTab]             = useState('payments');
  const [qualityFilter,   setQualityFilter]   = useState(null); // 'fee' | 'date' | 'unscheduled' | 'over'

  // Server-side overview: enrolled leads (scoped to the caller), summary,
  // collections, aging and due-soon in ONE small request. The date range
  // filters by ENROLLMENT date (not last-edited, which moves on every edit).
  const dateFrom = dateRange?.[0] ? dateRange[0].format('YYYY-MM-DD') : undefined;
  const dateTo   = dateRange?.[1] ? dateRange[1].format('YYYY-MM-DD') : undefined;
  const { data: overview, isLoading, isError, refetch } = useQuery({
    queryKey: ['payments-overview', dateFrom, dateTo],
    queryFn: () => paymentsAPI.overview({ date_from: dateFrom, date_to: dateTo }).then(r => r.data),
  });

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ['payments-overview'] });
    queryClient.invalidateQueries({ queryKey: ['payments-overdue'] });
    queryClient.invalidateQueries({ queryKey: ['payments-emis'] });
    queryClient.invalidateQueries({ queryKey: ['payments-dropped'] });
    queryClient.invalidateQueries({ queryKey: ['payment-history'] });
    queryClient.invalidateQueries({ queryKey: ['enrolled-leads'] });
    queryClient.invalidateQueries({ queryKey: ['leads'] });
  };

  const updateMutation = useMutation({
    mutationFn: ({ leadId, data }) => leadsAPI.update(leadId, data),
    onSuccess: () => {
      refreshAll();
      setEditLead(null);
      message.success('Payment details updated');
    },
    onError: (e) => message.error(e?.response?.data?.detail || 'Could not save — nothing was changed. Please try again.'),
  });

  const leads = useMemo(() => overview?.leads || [], [overview]);

  const filtered = leads.filter(l => {
    const q = searchText.trim().toLowerCase();
    if (q && !l.full_name?.toLowerCase().includes(q) && !l.phone?.includes(searchText.trim()) &&
        !l.email?.toLowerCase().includes(q)) return false;
    if (filterCounselor && l.assigned_to !== filterCounselor) return false;
    if (filterCourse    && l.course_interested !== filterCourse) return false;
    if (filterStatus    && financeFor(l).paymentStatus !== filterStatus) return false;
    if (qualityFilter === 'fee'  && Number(l.actual_revenue) > 0) return false;
    if (qualityFilter === 'date' && (l.enroll_date || l.enrolled_at)) return false;
    if (qualityFilter === 'unscheduled' && financeFor(l).unscheduled <= 0.5) return false;
    if (qualityFilter === 'over' && financeFor(l).overScheduled <= 0.5) return false;
    return true;
  });

  // Summary cards — derived from the same financeFor() the table and the
  // expanded row use, so the top-line numbers always match what you see per lead.
  const finances       = filtered.map(financeFor);
  const totalRevenue   = finances.reduce((s, f) => s + f.total,     0);
  const totalCollected = finances.reduce((s, f) => s + f.collected, 0);
  const totalBalance   = finances.reduce((s, f) => s + f.balance,   0);
  const totalOverdue   = finances.reduce((s, f) => s + f.overdueAmount, 0);
  const totalScheduled   = finances.reduce((s, f) => s + f.scheduledPending, 0);
  const totalUnscheduled = finances.reduce((s, f) => s + f.unscheduled, 0);
  const overdueCount   = finances.filter(f => f.overdueAmount > 0).length;
  const collectionRate = totalRevenue > 0 ? Math.round((totalCollected / totalRevenue) * 1000) / 10 : 0;

  // From the data-quality banner: jump to the table filtered to the affected leads.
  // Leads with no enrollment date are excluded server-side whenever a date range
  // is set, so showing them also clears the range.
  const showIncomplete = (kind) => {
    if (kind === 'date') setDateRange([null, null]);
    setSearchText(''); setFilterCounselor(null); setFilterCourse(null); setFilterStatus(null);
    setQualityFilter(kind);
    setTab('payments');
  };

  const counselors = [...new Set(leads.map(l => l.assigned_to).filter(Boolean))];
  const courses    = [...new Set(leads.map(l => l.course_interested).filter(Boolean))];

  const exportCsv = () => {
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const header = ['Lead ID', 'Name', 'Phone', 'Email', 'Counselor', 'Course', 'Country', 'Enrolled', 'Total fee', 'Collected', 'Balance', 'Overdue', 'Status', 'EMIs paid'];
    const body = filtered.map(l => {
      const f = financeFor(l);
      const emis = safeParse(l.emi_details, []);
      return [l.lead_id, l.full_name, l.phone, l.email, l.assigned_to, l.course_interested, l.country,
        (l.enroll_date || l.enrolled_at) ? dayjs(l.enroll_date || l.enrolled_at).format('YYYY-MM-DD') : '',
        f.total, f.collected, f.balance, f.overdueAmount, PAYMENT_STATUS_CONFIG[f.paymentStatus].label,
        `${emis.filter(e => e.status === 'paid').length}/${emis.length}`].map(esc).join(',');
    });
    const blob = new Blob(['\uFEFF' + [header.map(esc).join(','), ...body].join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `payments-${dayjs().format('YYYY-MM-DD')}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  // Uploads must run one-at-a-time per lead+docType: the backend appends to
  // the `documents` array via read-modify-write (fetch lead -> push -> save
  // whole array), so firing several uploads for the same lead concurrently
  // races and silently drops all but the last one. AntD's Upload calls
  // customRequest once per selected file but does NOT wait for the previous
  // call to finish, so selecting multiple files at once would otherwise
  // trigger exactly that race — this queue chains them per key instead.
  const uploadChainRef = useRef({});
  const uploadCountRef = useRef({});

  const handleUpload = (leadId, file, docType) => {
    const key = `${leadId}-${docType}`;
    uploadCountRef.current[key] = (uploadCountRef.current[key] || 0) + 1;
    setUploading(key);

    const prevChain = uploadChainRef.current[key] || Promise.resolve();
    const thisChain = prevChain
      .catch(() => {}) // a prior failure shouldn't block the rest of the queue
      .then(() => uploadAPI.uploadLeadDocument(leadId, file, docType))
      .then(() => {
        queryClient.invalidateQueries({ queryKey: ['enrolled-leads'] });
      })
      .catch(() => {
        message.error(`Failed to upload ${file.name}`);
      })
      .finally(() => {
        uploadCountRef.current[key] -= 1;
        if (uploadCountRef.current[key] <= 0) {
          setUploading(null);
          message.success(docType === 'receipt' ? 'Receipt uploaded' : 'Document(s) uploaded');
        }
      });

    uploadChainRef.current[key] = thisChain;
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
          {r.email && <div style={{ fontSize: 11, color: '#9ca3af' }}>{r.email}</div>}
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
      render: v => Number(v) ? <Text strong style={{ color: '#059669' }}>{fmt(Number(v))}</Text> : <Tag color="warning">Fee missing</Tag>,
      sorter: (a, b) => (Number(a.actual_revenue) || 0) - (Number(b.actual_revenue) || 0),
      defaultSortOrder: 'descend',
    },
    {
      title: 'Registration',
      dataIndex: 'registration_fees',
      key: 'registration_fees',
      render: v => Number(v) ? <Text style={{ color: '#2563eb' }}>{fmt(Number(v))}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Balance Due',
      key: 'balance',
      render: (_, r) => {
        const { balance, overdueAmount, unscheduled } = financeFor(r);
        if (balance <= 0) return <Tag color="green">Cleared</Tag>;
        return (
          <div>
            <Text strong style={{ color: '#dc2626' }}>{fmt(balance)}</Text>
            {unscheduled > 0.5 && (
              <div style={{ fontSize: 11, color: '#d97706' }}>{fmt(unscheduled)} not scheduled</div>
            )}
            {overdueAmount > 0 && (
              <div style={{ fontSize: 11, color: '#dc2626' }}>
                {fmt(overdueAmount)} overdue
              </div>
            )}
          </div>
        );
      },
      sorter: (a, b) => financeFor(a).balance - financeFor(b).balance,
    },
    {
      title: 'Status',
      key: 'payment_status',
      render: (_, r) => {
        const { label, color } = PAYMENT_STATUS_CONFIG[financeFor(r).paymentStatus];
        return <Badge status={color} text={label} />;
      },
    },
    {
      title: 'EMIs',
      key: 'emis',
      render: (_, r) => {
        const emis = safeParse(r.emi_details, []);
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
        const docCount   = safeParse(r.documents, []).length;
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
      key: 'enrolled_at',
      render: (_, r) => {
        const d = r.enroll_date || r.enrolled_at;
        return d ? dayjs(d).format('DD MMM YYYY') : <Text type="secondary">Date missing</Text>;
      },
      sorter: (a, b) => dayjs(a.enroll_date || a.enrolled_at || 0).unix() - dayjs(b.enroll_date || b.enrolled_at || 0).unix(),
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
        <Space size={0} wrap>
          <Button size="small" type="link" onClick={() => setEditLead(r)}>
            Edit Payment
          </Button>
          <Button size="small" type="link" danger onClick={() => setDropLead(r)}>
            Mark dropped
          </Button>
        </Space>
      ),
    },
  ];

  const cards = [
    { label: 'Total Fees (booked)', value: fmt(totalRevenue),   sub: 'fees of the enrolled students',          bg: 'linear-gradient(135deg,#10b981,#059669)', Icon: DollarSign },
    { label: 'Received',            value: fmt(totalCollected), sub: `${collectionRate}% of fees`,             bg: 'linear-gradient(135deg,#8b5cf6,#7c3aed)', Icon: TrendingUp },
    { label: 'Remaining to collect', value: fmt(totalBalance),
      sub: `${fmt(totalScheduled)} scheduled · ${fmt(totalUnscheduled)} not scheduled`,                         bg: 'linear-gradient(135deg,#f59e0b,#d97706)', Icon: FileText },
    {
      label: 'Overdue', value: fmt(totalOverdue),
      sub: overdueCount > 0 ? `${overdueCount} lead${overdueCount > 1 ? 's' : ''}` : 'all on time',
      bg: totalOverdue > 0 ? 'linear-gradient(135deg,#ef4444,#dc2626)' : 'linear-gradient(135deg,#9ca3af,#6b7280)',
      Icon: AlertTriangle,
    },
    { label: 'Total Enrolled', value: filtered.length, bg: 'linear-gradient(135deg,#3b82f6,#2563eb)', Icon: Users },
  ];
  const dq = overview?.data_quality || {};

  const paymentsTab = (
    <>
      {qualityFilter && (
        <Alert
          type="info" showIcon style={{ marginBottom: 12 }}
          message={{
            fee: `Showing ${filtered.length} enrolled lead(s) with no total fee — click "Edit Payment" to add it.`,
            date: `Showing ${filtered.length} enrolled lead(s) with no enrollment date — click "Edit Payment" to add it.`,
            unscheduled: `Showing ${filtered.length} student(s) whose fee is not fully in instalments — click "Edit Payment" and schedule the rest.`,
            over: `Showing ${filtered.length} student(s) whose payments add up to more than the fee — click "Edit Payment" to correct them.`,
          }[qualityFilter]}
          action={<Button size="small" onClick={() => setQualityFilter(null)}>Show all</Button>}
        />
      )}
      <Card style={{ marginBottom: 20, borderRadius: 12 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 12 }}>
          <Input placeholder="Search name / phone / email…" value={searchText}
            onChange={e => setSearchText(e.target.value)} allowClear />
          {!isCounselor && (
            <Select placeholder="Counselor" value={filterCounselor} onChange={setFilterCounselor}
              allowClear showSearch options={counselors.map(c => ({ label: c, value: c }))} />
          )}
          <Select placeholder="Course" value={filterCourse} onChange={setFilterCourse}
            allowClear showSearch options={courses.map(c => ({ label: c, value: c }))} />
          <Select placeholder="Payment Status" value={filterStatus} onChange={setFilterStatus}
            allowClear options={Object.entries(PAYMENT_STATUS_CONFIG).map(([value, { label }]) => ({ label, value }))} />
          <DatePicker.RangePicker value={dateRange} onChange={v => setDateRange(v || [null, null])}
            placeholder={['Enrolled from', 'Enrolled to']} />
        </div>
      </Card>
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
                scroll={{ x: 1200 }}
                rowClassName={r => financeFor(r).overdueAmount > 0 ? 'payments-row-overdue' : ''}
                expandable={{
                  expandedRowRender: r => (
                    <ExpandedRow lead={r} onUpload={handleUpload} uploading={uploading} onMarkPaid={setPayTarget} />
                  ),
                }}
              />
            )
        }
      </Card>
    </>
  );

  if (isError) {
    return (
      <div style={{ padding: 24 }}>
        <Result status="warning" title="Couldn't load payments"
          subTitle="The server was slow or didn't respond. Your data is fine — try again."
          extra={<Button type="primary" onClick={() => refetch()}>Retry</Button>} />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 600, marginBottom: 4 }}>Enrolled Leads & Payments</h1>
          <p style={{ color: 'var(--text-secondary)', margin: 0 }}>
            {isCounselor
              ? `Your enrolled leads — ${authUser?.full_name}`
              : 'Track fees, EMI schedules, collections and overdue accounts'}
          </p>
        </div>
        <Button icon={<DownloadOutlined />} onClick={exportCsv} disabled={!filtered.length}>Export CSV</Button>
      </div>

      {(dq.missing_fee > 0 || dq.undated_enrollments > 0 || dq.unscheduled_leads > 0 || dq.over_scheduled_leads > 0) && (
        <Alert
          type="warning" showIcon closable style={{ marginBottom: 16 }}
          message="Some enrollments have incomplete data"
          description={(
            <div>
              {dq.missing_fee > 0 && (
                <div>
                  {dq.missing_fee} enrolled lead(s) have no total fee, so their revenue and balance read as zero.{' '}
                  <Button type="link" size="small" style={{ padding: 0 }} onClick={() => showIncomplete('fee')}>
                    Show these {dq.missing_fee}
                  </Button>
                </div>
              )}
              {dq.undated_enrollments > 0 && (
                <div>
                  {dq.undated_enrollments} have no enrollment date and are hidden whenever an enrolled-date range is set.{' '}
                  <Button type="link" size="small" style={{ padding: 0 }} onClick={() => showIncomplete('date')}>
                    Show these {dq.undated_enrollments}
                  </Button>
                </div>
              )}
              {dq.unscheduled_leads > 0 && (
                <div>
                  {dq.unscheduled_leads} student(s) have part of the fee in no instalment ({fmt(totalUnscheduled)} in all), so it has no due date and is never chased.{' '}
                  <Button type="link" size="small" style={{ padding: 0 }} onClick={() => showIncomplete('unscheduled')}>
                    Show these {dq.unscheduled_leads}
                  </Button>
                </div>
              )}
              {dq.over_scheduled_leads > 0 && (
                <div>
                  {dq.over_scheduled_leads} student(s) have more received + scheduled than the fee.{' '}
                  <Button type="link" size="small" style={{ padding: 0 }} onClick={() => showIncomplete('over')}>
                    Show these {dq.over_scheduled_leads}
                  </Button>
                </div>
              )}
              <div style={{ marginTop: 4 }}>Use "Edit Payment" on those rows to fix them.</div>
            </div>
          )}
        />
      )}

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))',
        gap: 16, marginBottom: 24,
      }}>
        {cards.map(({ label, value, sub, bg, Icon }) => (
          <Card key={label} style={{ background: bg, color: 'white', borderRadius: 12, border: 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
              <div>
                <div style={{ fontSize: 12, opacity: 0.9, marginBottom: 8 }}>{label}</div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
                {sub && <div style={{ fontSize: 12, opacity: 0.9, marginTop: 4 }}>{sub}</div>}
              </div>
              <Icon size={32} opacity={0.3} />
            </div>
          </Card>
        ))}
      </div>

      <Tabs
        activeKey={tab}
        onChange={setTab}
        destroyInactiveTabPane
        items={[
          { key: 'payments', label: 'Enrolled & Payments', children: paymentsTab },
          { key: 'emis', label: 'EMIs by month', children: <EmiMonthTab onChanged={refreshAll} /> },
          { key: 'collections', label: 'Collections', children: <CollectionsTab data={overview} /> },
          { key: 'dropped', label: 'Dropped', children: <DroppedTab onChanged={refreshAll} /> },
          { key: 'overdue', label: `Overdue${overview?.summary?.overdue_leads ? ` (${overview.summary.overdue_leads})` : ''}`, children: <OverdueTab onChanged={refreshAll} /> },
        ]}
      />

      <PayEmiModal target={payTarget} onClose={() => setPayTarget(null)} onDone={refreshAll} />
      <DropStudentModal lead={dropLead} onClose={() => setDropLead(null)} onDone={refreshAll} />

      {/* Edit Payment Modal */}
      <EnrollmentModal
        open={!!editLead}
        lead={editLead}
        loading={updateMutation.isPending}
        onCancel={() => setEditLead(null)}
        onSave={data => updateMutation.mutate({ leadId: editLead.lead_id, data })}
      />

      <style>{`.payments-row-overdue { background: #fff1f0 !important; }
        .payments-row-overdue:hover > td { background: #ffe4e2 !important; }`}</style>
    </div>
  );
};

export default PaymentsPage;
