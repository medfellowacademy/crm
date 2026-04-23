import React, { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Table, Button, Tag, Progress, Space, Input, Select, DatePicker,
  Drawer, Form, message, Row, Col, Card, Statistic, Avatar, Tooltip,
  Dropdown, Segmented, Empty, Typography, Divider, Checkbox,
  Radio, InputNumber, Alert, Modal, Upload, Steps, Badge,
} from 'antd';
import {
  PlusOutlined, SearchOutlined, FilterOutlined, WhatsAppOutlined,
  MailOutlined, EyeOutlined, DeleteOutlined, ReloadOutlined,
  DownloadOutlined, UserOutlined, PhoneOutlined, GlobalOutlined,
  BookOutlined, CalendarOutlined, EditOutlined, MoreOutlined,
  StarOutlined, FireOutlined, ThunderboltOutlined, TeamOutlined,
  ClockCircleOutlined, SyncOutlined, ExportOutlined, ImportOutlined,
  CheckCircleOutlined, CloseCircleOutlined, UploadOutlined,
  WarningOutlined, FunnelPlotOutlined, MessageOutlined,
} from '@ant-design/icons';
import ChatDrawer from '../components/ChatDrawer';
import { leadsAPI, coursesAPI, counselorsAPI, usersAPI } from '../api/api';
import { useAuth } from '../context/AuthContext';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import isBetween from 'dayjs/plugin/isBetween';
import * as XLSX from 'xlsx';

dayjs.extend(relativeTime);
dayjs.extend(isBetween);

const { RangePicker } = DatePicker;
const { Option } = Select;
const { Text, Title } = Typography;
const { Dragger } = Upload;

// ── Date filter helper ──────────────────────────────────────────────────────
const makeDateFilter = (fieldKey) => ({
  filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }) => {
    const [mode, setMode] = useState(selectedKeys[0]?.mode || 'all');
    const [date, setDate] = useState(selectedKeys[0]?.date ? dayjs(selectedKeys[0].date) : null);
    const [range, setRange] = useState(
      selectedKeys[0]?.range ? [dayjs(selectedKeys[0].range[0]), dayjs(selectedKeys[0].range[1])] : null
    );

    const apply = (m, d, r) => {
      setSelectedKeys([{ mode: m, date: d?.format?.('YYYY-MM-DD'), range: r?.map(x => x.format('YYYY-MM-DD')) }]);
      confirm();
    };

    return (
      <div style={{ padding: 16, width: 280 }}>
        <Text strong style={{ display: 'block', marginBottom: 8 }}>Filter by date</Text>
        <Radio.Group
          value={mode}
          onChange={e => { setMode(e.target.value); }}
          style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}
        >
          <Radio value="all">All time</Radio>
          <Radio value="today">Today</Radio>
          <Radio value="week">This week</Radio>
          <Radio value="month">This month</Radio>
          <Radio value="on">On exact date</Radio>
          <Radio value="before">Before date</Radio>
          <Radio value="after">After date</Radio>
          <Radio value="between">Between dates</Radio>
        </Radio.Group>

        {['on', 'before', 'after'].includes(mode) && (
          <DatePicker
            style={{ width: '100%', marginBottom: 8 }}
            value={date}
            onChange={d => setDate(d)}
          />
        )}
        {mode === 'between' && (
          <RangePicker
            style={{ width: '100%', marginBottom: 8 }}
            value={range}
            onChange={r => setRange(r)}
          />
        )}

        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Button size="small" onClick={() => { clearFilters(); setMode('all'); setDate(null); setRange(null); }}>
            Reset
          </Button>
          <Button type="primary" size="small" onClick={() => apply(mode, date, range)}>
            Apply
          </Button>
        </Space>
      </div>
    );
  },
  onFilter: (value, record) => {
    if (!value || value.mode === 'all') return true;
    const val = record[fieldKey];
    if (!val) return false;
    const d = dayjs(val);
    const now = dayjs();
    const { mode, date, range } = value;
    if (mode === 'today') return d.isSame(now, 'day');
    if (mode === 'week') return d.isAfter(now.subtract(7, 'day'));
    if (mode === 'month') return d.isAfter(now.subtract(1, 'month'));
    if (mode === 'on' && date) return d.isSame(dayjs(date), 'day');
    if (mode === 'before' && date) return d.isBefore(dayjs(date), 'day');
    if (mode === 'after' && date) return d.isAfter(dayjs(date), 'day');
    if (mode === 'between' && range?.length === 2) {
      return d.isBetween(dayjs(range[0]).startOf('day'), dayjs(range[1]).endOf('day'), null, '[]');
    }
    return true;
  },
  filterIcon: filtered => <CalendarOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
});

// ── File parser (CSV, Excel, ODS) ──────────────────────────────────────────
const parseSpreadsheet = (data, isBinary) => {
  const workbook = XLSX.read(data, { type: isBinary ? 'binary' : 'string' });
  const sheet = workbook.Sheets[workbook.SheetNames[0]];
  const rows = XLSX.utils.sheet_to_json(sheet, { defval: '' });
  // Normalize header keys: lowercase + spaces → underscores
  return rows.map(row => {
    const normalized = {};
    Object.keys(row).forEach(k => {
      normalized[k.trim().toLowerCase().replace(/\s+/g, '_')] = String(row[k] ?? '');
    });
    return normalized;
  }).filter(r => r.full_name || r.name);
};

const REQUIRED_COLS = ['full_name', 'phone'];
const STATUS_OPTIONS = ['Fresh', 'Follow Up', 'Warm', 'Hot', 'Not Interested', 'Not Answering', 'Enrolled', 'Junk'];

// ════════════════════════════════════════════════════════════════════════════
const LeadsPageEnhanced = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user: authUser } = useAuth();
  const isCounselor = authUser?.role === 'Counselor';

  const [chatLead, setChatLead] = useState(null);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [bulkDrawerVisible, setBulkDrawerVisible] = useState(false);
  const [filterDrawerVisible, setFilterDrawerVisible] = useState(false);
  const [importVisible, setImportVisible] = useState(false);
  const [importStep, setImportStep] = useState(0);
  const [importData, setImportData] = useState([]);
  const [importErrors, setImportErrors] = useState([]);
  const [importProgress, setImportProgress] = useState(0);
  const [filters, setFilters] = useState({});
  const [searchText, setSearchText] = useState('');
  const [selectedRows, setSelectedRows] = useState([]);
  const [quickFilter, setQuickFilter] = useState('all');
  const [advFilters, setAdvFilters] = useState({});
  const [form] = Form.useForm();
  const [bulkForm] = Form.useForm();
  const fileInputRef = useRef(null);

  // ── Queries ────────────────────────────────────────────────────────────────
  const { data: leads = [], isLoading, refetch } = useQuery({
    queryKey: ['leads', filters, searchText, quickFilter],
    queryFn: async () => {
      let params = { ...filters };
      if (quickFilter === 'hot') params.ai_segment = 'Hot';
      if (quickFilter === 'warm') params.ai_segment = 'Warm';
      if (quickFilter === 'today') params.created_today = true;
      if (quickFilter === 'overdue') params.overdue = true;
      if (searchText) params.search = searchText;
      try { return (await leadsAPI.getAll(params)).data?.leads || []; } catch { return []; }
    },
    refetchInterval: 30000,
    retry: 1,
  });

  const { data: courses = [] } = useQuery({
    queryKey: ['courses'],
    queryFn: async () => { try { return (await coursesAPI.getAll()).data || []; } catch { return []; } },
  });

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: async () => { try { return (await usersAPI.getAll()).data?.users || []; } catch { return []; } },
  });

  // ── Computed filter options ────────────────────────────────────────────────
  const uniqueStatuses   = [...new Set(leads.map(l => l.status))].filter(Boolean).sort();
  const uniqueCountries  = [...new Set(leads.map(l => l.country))].filter(Boolean).sort();
  const uniqueCourses    = [...new Set([
    ...courses.map(c => c.course_name),
    ...leads.map(l => l.course_interested),
  ])].filter(Boolean).sort();
  const uniqueAssigned   = isCounselor
    ? (authUser?.full_name ? [authUser.full_name] : [])
    : [...new Set(leads.map(l => l.assigned_to))].filter(Boolean).sort();
  const uniqueSources    = [...new Set(leads.map(l => l.source))].filter(Boolean).sort();
  const uniqueSegments   = ['Hot', 'Warm', 'Cold', 'Junk'];

  // ── Client-side advanced filter ────────────────────────────────────────────
  const filteredLeads = leads.filter(l => {
    if (advFilters.status?.length && !advFilters.status.includes(l.status)) return false;
    if (advFilters.segment?.length && !advFilters.segment.includes(l.ai_segment)) return false;
    if (advFilters.country?.length && !advFilters.country.includes(l.country)) return false;
    if (advFilters.course?.length && !advFilters.course.includes(l.course_interested)) return false;
    if (advFilters.source?.length && !advFilters.source.includes(l.source)) return false;
    if (advFilters.assigned?.length && !advFilters.assigned.includes(l.assigned_to)) return false;
    if (advFilters.minScore != null && (l.ai_score || 0) < advFilters.minScore) return false;
    if (advFilters.maxScore != null && (l.ai_score || 0) > advFilters.maxScore) return false;
    // Follow-up date filters
    if (advFilters.followUp) {
      const { mode, date, range } = advFilters.followUp;
      const d = l.follow_up_date ? dayjs(l.follow_up_date) : null;
      if (mode === 'today' && (!d || !d.isSame(dayjs(), 'day'))) return false;
      if (mode === 'overdue' && (!d || !d.isBefore(dayjs(), 'day'))) return false;
      if (mode === 'on' && date && (!d || !d.isSame(dayjs(date), 'day'))) return false;
      if (mode === 'before' && date && (!d || !d.isBefore(dayjs(date), 'day'))) return false;
      if (mode === 'after' && date && (!d || !d.isAfter(dayjs(date), 'day'))) return false;
      if (mode === 'between' && range?.length === 2 && (!d || !d.isBetween(dayjs(range[0]).startOf('day'), dayjs(range[1]).endOf('day'), null, '[]'))) return false;
    }
    return true;
  });

  // ── Stats ──────────────────────────────────────────────────────────────────
  const stats = {
    total: leads.length,
    hot: leads.filter(l => l.ai_segment === 'Hot').length,
    warm: leads.filter(l => l.ai_segment === 'Warm').length,
    enrolled: leads.filter(l => l.status === 'Enrolled').length,
    followUpToday: leads.filter(l => l.follow_up_date && dayjs(l.follow_up_date).isSame(dayjs(), 'day')).length,
    overdue: leads.filter(l => l.follow_up_date && dayjs(l.follow_up_date).isBefore(dayjs(), 'day')).length,
    avgScore: leads.length ? (leads.reduce((s, l) => s + (l.ai_score || 0), 0) / leads.length).toFixed(1) : 0,
    revenue: leads.filter(l => l.status === 'Enrolled').reduce((s, l) => s + (l.actual_revenue || 0), 0),
  };

  // ── Mutations ──────────────────────────────────────────────────────────────
  const createMutation = useMutation({
    mutationFn: (d) => leadsAPI.create(d),
    onSuccess: () => { message.success('Lead created!'); setDrawerVisible(false); form.resetFields(); queryClient.invalidateQueries(['leads']); },
    onError: (e) => message.error(`Failed: ${e.message}`),
  });

  const updateMutation = useMutation({
    mutationFn: ({ leadId, data }) => leadsAPI.update(leadId, data),
    onSuccess: () => { message.success('Lead updated!'); queryClient.invalidateQueries(['leads']); },
    onError: (e) => message.error(`Failed: ${e.message}`),
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => leadsAPI.delete(id),
    onSuccess: () => { message.success('Lead deleted!'); queryClient.invalidateQueries(['leads']); },
  });

  const bulkMutation = useMutation({
    mutationFn: ({ leadIds, updates }) => leadsAPI.bulkUpdate(leadIds, updates),
    onSuccess: () => { message.success(`${selectedRows.length} leads updated!`); setSelectedRows([]); setBulkDrawerVisible(false); bulkForm.resetFields(); queryClient.invalidateQueries(['leads']); },
  });

  // ── Import handlers ────────────────────────────────────────────────────────
  const processImportRows = (rows) => {
    const errors = [];
    const valid = [];
    rows.forEach((row, i) => {
      // Normalise: trim all string values
      const r = {};
      Object.keys(row).forEach(k => { r[k.trim().toLowerCase().replace(/\s+/g, '_')] = String(row[k] ?? '').trim(); });

      const name = r.full_name || r.name || '';
      const phone = r.phone || r.mobile || r.phone_number || '';

      if (!name || !phone) {
        errors.push({ row: i + 2, msg: `Missing: ${!name ? 'full_name ' : ''}${!phone ? 'phone' : ''}`.trim() });
        return;
      }

      // Only send fields that LeadCreate accepts; strip unknown keys
      const lead = {
        full_name: name,
        phone,
        email: r.email || undefined,
        whatsapp: r.whatsapp || phone,
        country: r.country || 'India',
        source: r.source || 'Import',
        course_interested: r.course_interested || r.course || r.fellowship || 'Not Specified',
        assigned_to: isCounselor
          ? (authUser?.full_name || undefined)
          : (r.assigned_to || r.counselor || undefined),
      };
      // Remove undefined keys so FastAPI validation doesn't choke
      Object.keys(lead).forEach(k => { if (lead[k] === undefined || lead[k] === '') delete lead[k]; });
      valid.push(lead);
    });
    setImportData(valid);
    setImportErrors(errors);
    setImportStep(1);
  };

  const handleFileRead = (file) => {
    const ext = file.name.split('.').pop().toLowerCase();
    const isCsv = ext === 'csv';
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const rows = parseSpreadsheet(e.target.result, !isCsv);
        processImportRows(rows);
      } catch {
        message.error('Could not parse file. Please check the format and try again.');
      }
    };
    if (isCsv) {
      reader.readAsText(file);
    } else {
      reader.readAsBinaryString(file);
    }
    return false;
  };

  const handleImportSubmit = async () => {
    if (!importData.length) return;
    setImportStep(2);
    let done = 0;
    for (const lead of importData) {
      try { await leadsAPI.create(lead); } catch { /* skip errors */ }
      done++;
      setImportProgress(Math.round((done / importData.length) * 100));
    }
    setImportStep(3);
    queryClient.invalidateQueries(['leads']);
    message.success(`${done} leads imported successfully!`);
  };

  const resetImport = () => { setImportStep(0); setImportData([]); setImportErrors([]); setImportProgress(0); };

  // ── Export ─────────────────────────────────────────────────────────────────
  const handleExport = () => {
    const exportData = filteredLeads.map(l => ({
      'Lead ID': l.lead_id, Name: l.full_name, Email: l.email, Phone: l.phone,
      Country: l.country, Course: l.course_interested, Status: l.status,
      Segment: l.ai_segment, Score: l.ai_score, Source: l.source,
      'Assigned To': l.assigned_to, 'Follow Up': l.follow_up_date,
      Revenue: l.status === 'Enrolled' ? l.actual_revenue : l.expected_revenue,
      Created: l.created_at,
    }));
    const csv = [Object.keys(exportData[0]).join(','), ...exportData.map(r => Object.values(r).map(v => `"${v ?? ''}"`).join(','))].join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = `leads_${dayjs().format('YYYY-MM-DD')}.csv`;
    a.click();
    message.success('Exported!');
  };

  // ── Download template ──────────────────────────────────────────────────────
  const downloadTemplate = () => {
    const csv = 'full_name,email,phone,whatsapp,country,source,course_interested,status,assigned_to,expected_revenue\nJohn Doe,john@email.com,+919876543210,+919876543210,India,Website,MBBS MD,Fresh,,150000';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = 'leads_import_template.csv';
    a.click();
  };

  // ── Action menu ────────────────────────────────────────────────────────────
  const getActionMenu = (record) => ({
    items: [
      { key: 'view', icon: <EyeOutlined />, label: 'View Details', onClick: () => navigate(`/leads/${record.lead_id}`) },
      { key: 'edit', icon: <EditOutlined />, label: 'Edit', onClick: () => { form.setFieldsValue({ ...record, follow_up_date: record.follow_up_date ? dayjs(record.follow_up_date) : null }); setDrawerVisible(true); } },
      { key: 'whatsapp', icon: <WhatsAppOutlined />, label: 'WhatsApp', onClick: () => window.open(`https://wa.me/${record.phone?.replace(/[^0-9]/g, '')}`) },
      { key: 'email', icon: <MailOutlined />, label: 'Email', onClick: () => { window.location.href = `mailto:${record.email}`; } },
      { type: 'divider' },
      { key: 'delete', icon: <DeleteOutlined />, label: 'Delete', danger: true, onClick: () => deleteMutation.mutate(record.lead_id) },
    ],
  });

  // ── Table columns ──────────────────────────────────────────────────────────
  const columns = [
    {
      title: 'Lead',
      key: 'lead_info',
      fixed: 'left',
      width: 240,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }) => (
        <div style={{ padding: 8 }}>
          <Input placeholder="Search name / phone" value={selectedKeys[0]} onChange={e => setSelectedKeys([e.target.value])}
            onPressEnter={() => confirm()} style={{ marginBottom: 8, display: 'block' }} />
          <Space>
            <Button type="primary" size="small" onClick={() => confirm()}>Search</Button>
            <Button size="small" onClick={() => clearFilters()}>Reset</Button>
          </Space>
        </div>
      ),
      onFilter: (v, r) => (r.full_name + ' ' + r.phone).toLowerCase().includes(v.toLowerCase()),
      filterIcon: f => <SearchOutlined style={{ color: f ? '#1890ff' : undefined }} />,
      render: (_, r) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Avatar size={42} style={{ backgroundColor: r.ai_segment === 'Hot' ? '#ff4d4f' : r.ai_segment === 'Warm' ? '#faad14' : '#52c41a', flexShrink: 0 }}>
            {r.full_name?.charAt(0)?.toUpperCase()}
          </Avatar>
          <div style={{ minWidth: 0 }}>
            <a onClick={() => navigate(`/leads/${r.lead_id}`)} style={{ fontWeight: 600, fontSize: 13 }}>{r.full_name}</a>
            <Tag style={{ marginLeft: 4 }} color={r.ai_segment === 'Hot' ? 'red' : r.ai_segment === 'Warm' ? 'orange' : 'green'}>
              {r.ai_segment === 'Hot' ? '🔥' : r.ai_segment === 'Warm' ? '⚡' : '❄️'} {r.ai_segment}
            </Tag>
            <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}><PhoneOutlined /> {r.phone}</div>
          </div>
        </div>
      ),
    },
    {
      title: 'Country',
      dataIndex: 'country',
      key: 'country',
      width: 130,
      filters: uniqueCountries.map(c => ({ text: c, value: c })),
      onFilter: (v, r) => r.country === v,
      render: c => c ? <><GlobalOutlined /> {c}</> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Course',
      dataIndex: 'course_interested',
      key: 'course',
      width: 180,
      filters: uniqueCourses.map(c => ({ text: c, value: c })),
      onFilter: (v, r) => r.course_interested === v,
      ellipsis: true,
      render: c => c ? <><BookOutlined style={{ color: '#1890ff', marginRight: 4 }} />{c}</> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Source',
      dataIndex: 'source',
      key: 'source',
      width: 120,
      filters: uniqueSources.map(s => ({ text: s, value: s })),
      onFilter: (v, r) => r.source === v,
      render: s => s ? <Tag>{s}</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 140,
      filters: uniqueStatuses.map(s => ({ text: s, value: s })),
      onFilter: (v, r) => r.status === v,
      render: (s) => {
        const colorMap = { Enrolled: 'green', Hot: 'red', Warm: 'orange', Fresh: 'blue', 'Follow Up': 'purple', 'Not Interested': 'default', 'Not Answering': 'gray', Junk: 'volcano' };
        return <Tag color={colorMap[s] || 'default'}>{s}</Tag>;
      },
    },
    {
      title: 'AI Score',
      dataIndex: 'ai_score',
      key: 'ai_score',
      width: 130,
      sorter: (a, b) => (a.ai_score || 0) - (b.ai_score || 0),
      render: (score) => (
        <div>
          <Progress percent={score || 0} size="small"
            strokeColor={{ '0%': '#108ee9', '50%': '#87d068', '100%': '#ff4d4f' }}
            format={p => `${p?.toFixed(0)}`} />
        </div>
      ),
    },
    {
      title: 'Assigned To',
      dataIndex: 'assigned_to',
      key: 'assigned_to',
      width: 160,
      filters: [{ text: 'Unassigned', value: '__none__' }, ...uniqueAssigned.map(u => ({ text: u, value: u }))],
      onFilter: (v, r) => v === '__none__' ? !r.assigned_to : r.assigned_to === v,
      render: (val, r) => (
        <Select value={val || undefined} placeholder="Assign..." size="small" style={{ width: '100%' }} allowClear
          disabled={isCounselor}
          onChange={v => updateMutation.mutate({ leadId: r.lead_id, data: { assigned_to: v || null } })}
          options={isCounselor
            ? (authUser?.full_name ? [{ label: authUser.full_name, value: authUser.full_name }] : [])
            : users.map(u => ({ label: u.full_name, value: u.full_name }))} />
      ),
    },
    {
      title: 'Revenue',
      key: 'revenue',
      width: 120,
      sorter: (a, b) => {
        const aR = a.status === 'Enrolled' ? a.actual_revenue : a.expected_revenue;
        const bR = b.status === 'Enrolled' ? b.actual_revenue : b.expected_revenue;
        return (aR || 0) - (bR || 0);
      },
      render: (_, r) => {
        const rev = r.status === 'Enrolled' ? r.actual_revenue : r.expected_revenue;
        const actual = r.status === 'Enrolled';
        return (
          <div>
            <div style={{ fontWeight: 600, color: actual ? '#52c41a' : '#faad14' }}>
              ₹{((rev || 0) / 1000).toFixed(0)}K
            </div>
            <Text type="secondary" style={{ fontSize: 11 }}>{actual ? 'Actual' : 'Expected'}</Text>
          </div>
        );
      },
    },
    {
      title: 'Follow Up',
      dataIndex: 'follow_up_date',
      key: 'follow_up_date',
      width: 140,
      sorter: (a, b) => new Date(a.follow_up_date || 0) - new Date(b.follow_up_date || 0),
      ...makeDateFilter('follow_up_date'),
      render: (date) => {
        if (!date) return <Text type="secondary">—</Text>;
        const d = dayjs(date);
        const overdue = d.isBefore(dayjs(), 'day');
        const today = d.isSame(dayjs(), 'day');
        return (
          <Tooltip title={d.format('YYYY-MM-DD')}>
            <div style={{ color: overdue ? '#ff4d4f' : today ? '#faad14' : undefined }}>
              <CalendarOutlined /> {d.format('MMM DD')}
              {overdue && <Tag color="red" style={{ marginLeft: 4, fontSize: 10 }}>Overdue</Tag>}
              {today && <Tag color="orange" style={{ marginLeft: 4, fontSize: 10 }}>Today</Tag>}
            </div>
            <Text type="secondary" style={{ fontSize: 11 }}>{d.fromNow()}</Text>
          </Tooltip>
        );
      },
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 140,
      sorter: (a, b) => new Date(a.created_at) - new Date(b.created_at),
      ...makeDateFilter('created_at'),
      render: (d) => (
        <Tooltip title={dayjs(d).format('YYYY-MM-DD HH:mm')}>
          <Text type="secondary">{dayjs(d).fromNow()}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Last Updated',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 140,
      sorter: (a, b) => new Date(a.updated_at || a.created_at) - new Date(b.updated_at || b.created_at),
      ...makeDateFilter('updated_at'),
      render: (d, r) => {
        const date = d || r.created_at;
        return (
          <Tooltip title={dayjs(date).format('YYYY-MM-DD HH:mm')}>
            <Text type="secondary">{dayjs(date).fromNow()}</Text>
          </Tooltip>
        );
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      fixed: 'right',
      width: 120,
      render: (_, r) => (
        <Space>
          <Button type="primary" size="small" icon={<EyeOutlined />} onClick={() => navigate(`/leads/${r.lead_id}`)} />
          <Tooltip title="WhatsApp Chat">
            <Button
              size="small"
              icon={<MessageOutlined />}
              style={{ background: '#25d366', borderColor: '#25d366', color: '#fff' }}
              onClick={() => setChatLead(r)}
            />
          </Tooltip>
          <Dropdown menu={getActionMenu(r)} trigger={['click']}>
            <Button size="small" icon={<MoreOutlined />} />
          </Dropdown>
        </Space>
      ),
    },
  ];

  const activeAdvFilters = Object.values(advFilters).filter(v => v && (Array.isArray(v) ? v.length > 0 : true)).length;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ padding: 24, background: '#f0f2f5', minHeight: '100vh' }}>

      {/* ── Stats Row ── */}
      <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
        {[
          { label: 'Total Leads', value: stats.total, icon: <TeamOutlined />, color: '#1890ff' },
          { label: 'Hot 🔥', value: stats.hot, icon: <FireOutlined />, color: '#ff4d4f' },
          { label: 'Warm ⚡', value: stats.warm, icon: <ThunderboltOutlined />, color: '#faad14' },
          { label: 'Enrolled ✅', value: stats.enrolled, icon: <StarOutlined />, color: '#52c41a' },
          { label: 'Follow-up Today', value: stats.followUpToday, icon: <CalendarOutlined />, color: '#722ed1' },
          { label: 'Overdue ⚠️', value: stats.overdue, icon: <ClockCircleOutlined />, color: stats.overdue > 0 ? '#ff4d4f' : '#8c8c8c' },
          { label: 'Avg Score', value: `${stats.avgScore}`, icon: null, color: '#13c2c2' },
          { label: 'Revenue', value: `₹${(stats.revenue / 1000).toFixed(0)}K`, icon: null, color: '#52c41a' },
        ].map(({ label, value, icon, color }) => (
          <Col xs={12} sm={8} md={6} lg={3} key={label}>
            <Card size="small" hoverable style={{ textAlign: 'center', cursor: 'pointer' }}>
              <Statistic title={<span style={{ fontSize: 11 }}>{label}</span>} value={value}
                prefix={icon} valueStyle={{ color, fontSize: 20 }} />
            </Card>
          </Col>
        ))}
      </Row>

      {/* ── Main Card ── */}
      <Card
        title={
          <Space>
            <Title level={4} style={{ margin: 0 }}>Lead Management</Title>
            <Badge count={filteredLeads.length} style={{ backgroundColor: '#1890ff' }} />
          </Space>
        }
        extra={
          <Space wrap>
            <Segmented value={quickFilter} onChange={setQuickFilter}
              options={[
                { label: 'All', value: 'all' },
                { label: '🔥 Hot', value: 'hot' },
                { label: '⚡ Warm', value: 'warm' },
                { label: '📅 Today', value: 'today' },
                { label: '⚠️ Overdue', value: 'overdue' },
              ]} />
            <Input.Search placeholder="Search name / email / phone..." allowClear style={{ width: 240 }}
              onChange={e => setSearchText(e.target.value)} prefix={<SearchOutlined />} />
            <Tooltip title={activeAdvFilters ? `${activeAdvFilters} filters active` : 'Advanced Filters'}>
              <Badge count={activeAdvFilters} size="small">
                <Button icon={<FunnelPlotOutlined />} type={activeAdvFilters ? 'primary' : 'default'}
                  onClick={() => setFilterDrawerVisible(true)}>Filters</Button>
              </Badge>
            </Tooltip>
            <Button icon={<SyncOutlined />} onClick={() => { setAdvFilters({}); setFilters({}); setSearchText(''); setQuickFilter('all'); message.success('Filters cleared'); }}>Clear</Button>
            <Button icon={<DownloadOutlined />} onClick={downloadTemplate}>Template</Button>
            <Button icon={<ImportOutlined />} onClick={() => { resetImport(); setImportVisible(true); }}>Import</Button>
            <Button icon={<ExportOutlined />} onClick={handleExport}>Export</Button>
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setDrawerVisible(true); }}>Add Lead</Button>
          </Space>
        }
      >
        {/* Bulk bar */}
        {selectedRows.length > 0 && (
          <Alert style={{ marginBottom: 12 }}
            message={
              <Space>
                <Text strong>{selectedRows.length} selected</Text>
                <Button size="small" onClick={() => setSelectedRows(filteredLeads.map(l => l.lead_id))}>Select All {filteredLeads.length}</Button>
                <Button size="small" onClick={() => setSelectedRows([])}>Clear</Button>
                <Button size="small" type="primary" onClick={() => setBulkDrawerVisible(true)}>Bulk Update</Button>
                <Button size="small" danger onClick={() => {
                  Modal.confirm({
                    title: `Delete ${selectedRows.length} leads?`,
                    content: 'This cannot be undone.',
                    onOk: async () => { for (const id of selectedRows) { await leadsAPI.delete(id).catch(() => {}); } setSelectedRows([]); queryClient.invalidateQueries(['leads']); message.success('Deleted!'); },
                  });
                }}>Bulk Delete</Button>
              </Space>
            } type="info" showIcon />
        )}

        <Table
          columns={columns}
          dataSource={filteredLeads}
          loading={isLoading}
          rowKey="lead_id"
          scroll={{ x: 1800 }}
          size="middle"
          rowSelection={{
            selectedRowKeys: selectedRows,
            onChange: (keys) => setSelectedRows(keys),
            preserveSelectedRowKeys: true,
          }}
          pagination={{ total: filteredLeads.length, pageSize: 25, showSizeChanger: true, pageSizeOptions: ['10','25','50','100'], showTotal: t => `${t} leads`, position: ['bottomCenter'] }}
          locale={{ emptyText: <Empty description="No leads found"><Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawerVisible(true)}>Add First Lead</Button></Empty> }}
          rowClassName={r => r.follow_up_date && dayjs(r.follow_up_date).isBefore(dayjs(), 'day') ? 'overdue-row' : ''}
        />
        />
      </Card>

      {/* ══════════════════════════════════════════════════════════════════════
          IMPORT MODAL
      ══════════════════════════════════════════════════════════════════════ */}
      <Modal
        title={<Space><ImportOutlined /> Bulk Import Leads</Space>}
        open={importVisible}
        onCancel={() => { setImportVisible(false); resetImport(); }}
        footer={null}
        width={700}
      >
        <Steps current={importStep} style={{ marginBottom: 24 }}
          items={[{ title: 'Upload' }, { title: 'Preview' }, { title: 'Importing' }, { title: 'Done' }]} />

        {/* Step 0: Upload */}
        {importStep === 0 && (
          <div>
            <Alert type="info" showIcon style={{ marginBottom: 16 }}
              message="Supported Formats: CSV, Excel (.xlsx, .xls), ODS"
              description={
                <div>
                  Required columns: <Text code>full_name</Text>, <Text code>phone</Text><br />
                  Optional: email, country, source, course_interested, status, assigned_to, expected_revenue, whatsapp<br />
                  <Button size="small" type="link" icon={<DownloadOutlined />} onClick={downloadTemplate} style={{ padding: 0, marginTop: 4 }}>
                    Download template CSV
                  </Button>
                </div>
              }
            />
            <Dragger beforeUpload={handleFileRead} accept=".csv,.xlsx,.xls,.ods" showUploadList={false}>
              <p className="ant-upload-drag-icon"><UploadOutlined style={{ fontSize: 48, color: '#1890ff' }} /></p>
              <p className="ant-upload-text">Click or drag file here to upload</p>
              <p className="ant-upload-hint">Supports CSV, Excel (.xlsx, .xls), and ODS. Max 5,000 rows.</p>
            </Dragger>
          </div>
        )}

        {/* Step 1: Preview */}
        {importStep === 1 && (
          <div>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={8}>
                <Card size="small" style={{ textAlign: 'center', background: '#f6ffed', border: '1px solid #b7eb8f' }}>
                  <Statistic title="Valid Rows" value={importData.length} prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />} valueStyle={{ color: '#52c41a' }} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" style={{ textAlign: 'center', background: '#fff2f0', border: '1px solid #ffccc7' }}>
                  <Statistic title="Errors" value={importErrors.length} prefix={<CloseCircleOutlined style={{ color: '#ff4d4f' }} />} valueStyle={{ color: '#ff4d4f' }} />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <Statistic title="Total Rows" value={importData.length + importErrors.length} />
                </Card>
              </Col>
            </Row>

            {importErrors.length > 0 && (
              <Alert type="warning" showIcon style={{ marginBottom: 12 }}
                message={`${importErrors.length} rows skipped`}
                description={<ul style={{ marginBottom: 0 }}>{importErrors.slice(0, 5).map((e, i) => <li key={i}>Row {e.row}: {e.msg}</li>)}{importErrors.length > 5 && <li>...and {importErrors.length - 5} more</li>}</ul>}
              />
            )}

            <Table
              size="small"
              scroll={{ x: 600, y: 300 }}
              dataSource={importData.slice(0, 10)}
              rowKey={(_, i) => i}
              pagination={false}
              columns={[
                { title: 'Name', dataIndex: 'full_name', width: 150 },
                { title: 'Phone', dataIndex: 'phone', width: 130 },
                { title: 'Email', dataIndex: 'email', width: 160, ellipsis: true },
                { title: 'Country', dataIndex: 'country', width: 100 },
                { title: 'Course', dataIndex: 'course_interested', width: 150, ellipsis: true },
                { title: 'Status', dataIndex: 'status', width: 100, render: s => <Tag>{s}</Tag> },
              ]}
            />
            {importData.length > 10 && <Text type="secondary" style={{ fontSize: 12 }}>Showing first 10 of {importData.length} rows</Text>}

            <Divider />
            <Space>
              <Button onClick={() => setImportStep(0)}>Back</Button>
              <Button type="primary" onClick={handleImportSubmit} disabled={!importData.length}
                icon={<UploadOutlined />}>
                Import {importData.length} Leads
              </Button>
            </Space>
          </div>
        )}

        {/* Step 2: Importing */}
        {importStep === 2 && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Progress type="circle" percent={importProgress} />
            <p style={{ marginTop: 16 }}>Importing {importData.length} leads...</p>
          </div>
        )}

        {/* Step 3: Done */}
        {importStep === 3 && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <CheckCircleOutlined style={{ fontSize: 64, color: '#52c41a' }} />
            <Title level={3} style={{ marginTop: 16 }}>Import Complete!</Title>
            <p>{importData.length} leads imported successfully.</p>
            <Space>
              <Button onClick={() => { setImportVisible(false); resetImport(); }}>Close</Button>
              <Button type="primary" onClick={() => { setImportVisible(false); resetImport(); refetch(); }}>View Leads</Button>
            </Space>
          </div>
        )}
      </Modal>

      {/* ══════════════════════════════════════════════════════════════════════
          ADD / EDIT LEAD DRAWER
      ══════════════════════════════════════════════════════════════════════ */}
      <Drawer
        title={form.getFieldValue('lead_id') ? 'Edit Lead' : '➕ Add New Lead'}
        width={620}
        open={drawerVisible}
        onClose={() => { setDrawerVisible(false); form.resetFields(); }}
        extra={
          <Space>
            <Button onClick={() => { setDrawerVisible(false); form.resetFields(); }}>Cancel</Button>
            <Button type="primary" onClick={() => form.submit()} loading={createMutation.isPending}>Save</Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical"
          onFinish={v => createMutation.mutate({ ...v, follow_up_date: v.follow_up_date?.format('YYYY-MM-DD') || null })}>
          <Form.Item name="full_name" label="Full Name" rules={[{ required: true }]}>
            <Input prefix={<UserOutlined />} placeholder="John Doe" size="large" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="email" label="Email">
                <Input prefix={<MailOutlined />} placeholder="john@email.com" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="phone" label="Phone" rules={[{ required: true }]}>
                <Input prefix={<PhoneOutlined />} placeholder="+91 9876543210" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="country" label="Country" rules={[{ required: true }]}>
                <Select placeholder="Select country" showSearch>
                  {['India','USA','UK','Canada','Australia','UAE','Singapore','Germany','Nepal','Sri Lanka'].map(c => <Option key={c} value={c}>{c}</Option>)}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="source" label="Source">
                <Select placeholder="Lead source">
                  {['Website','Facebook','Google Ads','Instagram','WhatsApp','Referral','Direct','LinkedIn','YouTube'].map(s => <Option key={s} value={s}>{s}</Option>)}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="course_interested" label="Course Interested" rules={[{ required: true }]}>
            <Select placeholder="Select course" showSearch
              onChange={name => { const c = courses.find(c => c.course_name === name); if (c) { form.setFieldValue('expected_revenue', c.price); message.info(`Price ₹${(c.price/1000).toFixed(0)}K auto-filled`); } }}
              filterOption={(i, o) => o.children.toLowerCase().includes(i.toLowerCase())}>
              {courses.map(c => <Option key={c.id} value={c.course_name}>{c.course_name} — ₹{(c.price/1000).toFixed(0)}K</Option>)}
            </Select>
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="status" label="Status" initialValue="Fresh">
                <Select>{STATUS_OPTIONS.map(s => <Option key={s} value={s}>{s}</Option>)}</Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="follow_up_date" label="Follow-up Date">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="expected_revenue" label="Expected Revenue (₹)">
                <InputNumber style={{ width: '100%' }} min={0} formatter={v => `₹ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} parser={v => v.replace(/₹\s?|(,*)/g, '')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="actual_revenue" label="Actual Revenue (₹)">
                <InputNumber style={{ width: '100%' }} min={0} formatter={v => `₹ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} parser={v => v.replace(/₹\s?|(,*)/g, '')} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="assigned_to" label="Assign To">
            <Select placeholder="Select counselor" allowClear showSearch
              disabled={isCounselor}
              filterOption={(i, o) => o.label.toLowerCase().includes(i.toLowerCase())}
              options={isCounselor
                ? (authUser?.full_name ? [{ label: `${authUser.full_name} (Counselor)`, value: authUser.full_name }] : [])
                : users.map(u => ({ label: `${u.full_name} (${u.role})`, value: u.full_name }))} />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={3} placeholder="Initial notes..." showCount maxLength={500} />
          </Form.Item>
        </Form>
      </Drawer>

      {/* ══════════════════════════════════════════════════════════════════════
          BULK UPDATE DRAWER
      ══════════════════════════════════════════════════════════════════════ */}
      <Drawer
        title={`✏️ Bulk Update — ${selectedRows.length} leads`}
        width={440}
        open={bulkDrawerVisible}
        onClose={() => setBulkDrawerVisible(false)}
        extra={
          <Space>
            <Button onClick={() => setBulkDrawerVisible(false)}>Cancel</Button>
            <Button type="primary" onClick={() => bulkForm.submit()}>Apply to All</Button>
          </Space>
        }
      >
        <Alert message="Only filled fields will be updated. Blank fields stay unchanged." type="warning" showIcon style={{ marginBottom: 16 }} />
        <Form form={bulkForm} layout="vertical"
          onFinish={v => {
            const updates = {};
            if (v.status) updates.status = v.status;
            if (v.assigned_to) updates.assigned_to = v.assigned_to;
            if (v.follow_up_date) updates.follow_up_date = v.follow_up_date.format('YYYY-MM-DD');
            if (v.source) updates.source = v.source;
            bulkMutation.mutate({ leadIds: selectedRows, updates });
          }}>
          <Form.Item name="status" label="Status"><Select placeholder="Keep unchanged" allowClear>{STATUS_OPTIONS.map(s => <Option key={s} value={s}>{s}</Option>)}</Select></Form.Item>
          <Form.Item name="assigned_to" label="Assign To">
            <Select placeholder="Keep unchanged" allowClear showSearch
              options={users.map(u => ({ label: `${u.full_name} (${u.role})`, value: u.full_name }))} />
          </Form.Item>
          <Form.Item name="follow_up_date" label="Follow-up Date"><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="source" label="Source"><Select placeholder="Keep unchanged" allowClear>{['Website','Facebook','Google Ads','Instagram','Referral','Direct','LinkedIn','YouTube'].map(s => <Option key={s} value={s}>{s}</Option>)}</Select></Form.Item>
        </Form>
      </Drawer>

      {/* ══════════════════════════════════════════════════════════════════════
          ADVANCED FILTER DRAWER
      ══════════════════════════════════════════════════════════════════════ */}
      <Drawer
        title={<Space><FunnelPlotOutlined /> Advanced Filters</Space>}
        width={400}
        open={filterDrawerVisible}
        onClose={() => setFilterDrawerVisible(false)}
        extra={
          <Button onClick={() => { setAdvFilters({}); setFilterDrawerVisible(false); message.success('Filters cleared'); }}>
            Clear All
          </Button>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size={16}>

          <div>
            <Text strong>Status</Text>
            <Select mode="multiple" style={{ width: '100%', marginTop: 6 }} placeholder="Any status"
              value={advFilters.status || []} onChange={v => setAdvFilters(f => ({ ...f, status: v }))}>
              {STATUS_OPTIONS.map(s => <Option key={s} value={s}>{s}</Option>)}
            </Select>
          </div>

          <div>
            <Text strong>Segment</Text>
            <Select mode="multiple" style={{ width: '100%', marginTop: 6 }} placeholder="Any segment"
              value={advFilters.segment || []} onChange={v => setAdvFilters(f => ({ ...f, segment: v }))}>
              {uniqueSegments.map(s => <Option key={s} value={s}>{s}</Option>)}
            </Select>
          </div>

          <div>
            <Text strong>Country</Text>
            <Select mode="multiple" style={{ width: '100%', marginTop: 6 }} placeholder="Any country" showSearch
              value={advFilters.country || []} onChange={v => setAdvFilters(f => ({ ...f, country: v }))}>
              {uniqueCountries.map(c => <Option key={c} value={c}>{c}</Option>)}
            </Select>
          </div>

          <div>
            <Text strong>Course</Text>
            <Select mode="multiple" style={{ width: '100%', marginTop: 6 }} placeholder="Any course" showSearch
              value={advFilters.course || []} onChange={v => setAdvFilters(f => ({ ...f, course: v }))}>
              {uniqueCourses.map(c => <Option key={c} value={c}>{c}</Option>)}
            </Select>
          </div>

          <div>
            <Text strong>Source</Text>
            <Select mode="multiple" style={{ width: '100%', marginTop: 6 }} placeholder="Any source"
              value={advFilters.source || []} onChange={v => setAdvFilters(f => ({ ...f, source: v }))}>
              {uniqueSources.map(s => <Option key={s} value={s}>{s}</Option>)}
            </Select>
          </div>

          <div>
            <Text strong>Assigned To</Text>
            <Select mode="multiple" style={{ width: '100%', marginTop: 6 }} placeholder="Any counselor" showSearch
              disabled={isCounselor}
              value={advFilters.assigned || []} onChange={v => setAdvFilters(f => ({ ...f, assigned: v }))}>
              {uniqueAssigned.map(u => <Option key={u} value={u}>{u}</Option>)}
            </Select>
          </div>

          <div>
            <Text strong>AI Score Range</Text>
            <Row gutter={8} style={{ marginTop: 6 }}>
              <Col span={12}><InputNumber placeholder="Min (0)" min={0} max={100} style={{ width: '100%' }} value={advFilters.minScore} onChange={v => setAdvFilters(f => ({ ...f, minScore: v }))} /></Col>
              <Col span={12}><InputNumber placeholder="Max (100)" min={0} max={100} style={{ width: '100%' }} value={advFilters.maxScore} onChange={v => setAdvFilters(f => ({ ...f, maxScore: v }))} /></Col>
            </Row>
          </div>

          <div>
            <Text strong>Follow-up Date</Text>
            <Select style={{ width: '100%', marginTop: 6 }} placeholder="Any time" allowClear
              value={advFilters.followUp?.mode}
              onChange={v => setAdvFilters(f => ({ ...f, followUp: v ? { mode: v } : null }))}>
              <Option value="today">Today</Option>
              <Option value="overdue">Overdue</Option>
              <Option value="on">On exact date</Option>
              <Option value="before">Before date</Option>
              <Option value="after">After date</Option>
              <Option value="between">Between dates</Option>
            </Select>
            {advFilters.followUp?.mode === 'between' && (
              <RangePicker style={{ width: '100%', marginTop: 6 }}
                onChange={r => setAdvFilters(f => ({ ...f, followUp: { ...f.followUp, range: r?.map(d => d.format('YYYY-MM-DD')) } }))} />
            )}
            {['on','before','after'].includes(advFilters.followUp?.mode) && (
              <DatePicker style={{ width: '100%', marginTop: 6 }}
                onChange={d => setAdvFilters(f => ({ ...f, followUp: { ...f.followUp, date: d?.format('YYYY-MM-DD') } }))} />
            )}
          </div>

          <Button type="primary" block onClick={() => setFilterDrawerVisible(false)}>
            Apply Filters ({activeAdvFilters} active)
          </Button>
        </Space>
      </Drawer>

      <style>{`.overdue-row { background: #fff2f0 !important; }`}</style>

      {/* WhatsApp Chat Drawer */}
      <ChatDrawer lead={chatLead} onClose={() => setChatLead(null)} />
    </div>
  );
};

export default LeadsPageEnhanced;
