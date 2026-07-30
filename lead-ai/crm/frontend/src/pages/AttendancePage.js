import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card, Button, Tag, Table, Typography, Space, Alert, Spin, Tabs, DatePicker,
  Empty, Select, InputNumber, Row, Col, Statistic, Divider, Tooltip, message, Input,
} from 'antd';
import {
  LoginOutlined, LogoutOutlined, EnvironmentOutlined, ClockCircleOutlined,
  CheckCircleOutlined, WarningOutlined, DownloadOutlined, FileTextOutlined,
  DollarOutlined, TeamOutlined, CalendarOutlined, SaveOutlined, FilePdfOutlined, PlusOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { attendanceAPI, usersAPI } from '../api/api';

const { Title, Text } = Typography;
const { Option } = Select;
const { TextArea } = Input;

const STATUS_TAG = {
  present:             { color: 'green',   label: 'Present' },
  late:                { color: 'orange',  label: 'Late' },
  left_early:          { color: 'gold',    label: 'Left Early' },
  late_and_left_early: { color: 'red',     label: 'Late & Left Early' },
  absent:              { color: 'default', label: 'Absent' },
  week_off:            { color: 'purple',  label: 'Week Off' },
};

const fmtTime = (iso) => iso ? dayjs(iso).format('hh:mm A') : '—';
const fmtINR  = (n)   => `₹${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function hoursWorked(checkIn, checkOut) {
  if (!checkIn || !checkOut) return '—';
  const diff = dayjs(checkOut).diff(dayjs(checkIn), 'minute');
  if (diff <= 0) return '—';
  return `${Math.floor(diff / 60)}h ${diff % 60}m`;
}

function getCurrentLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Your browser does not support location services.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      (err) => reject(new Error(
        err.code === err.PERMISSION_DENIED
          ? 'Location permission denied. Please allow location access to check in/out.'
          : 'Could not determine your location. Please try again.'
      )),
      { enableHighAccuracy: true, timeout: 15000 }
    );
  });
}

function generateSlipHTML(slip) {
  const monthLabel = dayjs((slip.month || '2025-01') + '-01').format('MMMM YYYY');
  const perDay     = slip.working_days > 0 ? slip.gross_salary / slip.working_days : 0;
  const logoUrl    = window.location.origin + '/medfellow-logo.png';
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Salary Slip - ${slip.user_name} - ${monthLabel}</title>
<style>
  body{font-family:Arial,sans-serif;max-width:750px;margin:40px auto;padding:20px;color:#333}
  .header{display:flex;align-items:center;justify-content:space-between;border-bottom:3px solid #1890ff;padding-bottom:16px;margin-bottom:24px}
  .header-logo img{height:64px;width:auto;display:block}
  .header-right{text-align:right}
  .slip-title{font-size:18px;font-weight:700;color:#1890ff}
  .slip-sub{font-size:13px;color:#666;margin-top:4px}
  .info-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:24px;background:#f8faff;padding:16px;border-radius:8px}
  .info-item label{font-size:11px;color:#888;display:block;margin-bottom:2px}
  .info-item span{font-weight:600;font-size:14px}
  table{width:100%;border-collapse:collapse;margin-bottom:24px}
  th{background:#1890ff;color:white;padding:9px 12px;text-align:left;font-size:13px}
  td{padding:8px 12px;border-bottom:1px solid #f0f0f0;font-size:13px}
  tr:nth-child(even) td{background:#fafafa}
  .net-row td{background:#f6ffed !important;font-weight:700;font-size:15px;color:#389e0d;border-top:2px solid #b7eb8f}
  .deduction-row td{color:#cf1322}
  .notes-box{background:#fffbe6;border:1px solid #ffe58f;padding:12px 16px;border-radius:6px;font-size:13px;margin-bottom:20px}
  .footer{text-align:center;font-size:11px;color:#999;margin-top:32px;border-top:1px solid #f0f0f0;padding-top:12px}
  @media print{body{margin:0}}
</style></head><body>
<div class="header">
  <div class="header-logo"><img src="${logoUrl}" alt="MedFellow Academy" /></div>
  <div class="header-right">
    <div class="slip-title">Salary Slip</div>
    <div class="slip-sub">${monthLabel}</div>
  </div>
</div>
<div class="info-grid">
  <div class="info-item"><label>Employee Name</label><span>${slip.user_name}</span></div>
  <div class="info-item"><label>Employee Email</label><span>${slip.user_email}</span></div>
  <div class="info-item"><label>Month</label><span>${monthLabel}</span></div>
  <div class="info-item"><label>Generated On</label><span>${dayjs().format('DD MMM YYYY')}</span></div>
</div>
<table>
  <thead><tr><th colspan="2">Attendance Summary</th></tr></thead>
  <tbody>
    <tr><td>Total Working Days</td><td>${slip.working_days}</td></tr>
    <tr><td>Present (on time)</td><td>${slip.days_present}</td></tr>
    <tr><td>Late Arrivals</td><td>${slip.days_late}</td></tr>
    <tr><td>Left Early</td><td>${slip.days_left_early}</td></tr>
    <tr><td>Absent</td><td>${slip.days_absent}</td></tr>
    <tr><td>Paid Leaves Allowed</td><td>${slip.paid_leaves_allowed}</td></tr>
    <tr><td>Effective Absent (after paid leave)</td><td>${slip.effective_absent}</td></tr>
  </tbody>
</table>
<table>
  <thead><tr><th>Earnings / Deductions</th><th>Amount</th></tr></thead>
  <tbody>
    <tr><td>Gross Monthly Salary</td><td>${fmtINR(slip.gross_salary)}</td></tr>
    <tr><td>Per Day Rate</td><td>${fmtINR(perDay)}</td></tr>
    ${slip.effective_absent > 0 ? `<tr class="deduction-row"><td>Absent Deduction (${slip.effective_absent} days &times; ${fmtINR(perDay)})</td><td>&minus; ${fmtINR(slip.absent_deduction)}</td></tr>` : ''}
    ${slip.late_deduction_total > 0 ? `<tr class="deduction-row"><td>Late Arrival Deduction (${slip.days_late} days &times; ${fmtINR(slip.late_deduction_per_day)})</td><td>&minus; ${fmtINR(slip.late_deduction_total)}</td></tr>` : ''}
    ${(slip.advance_deduction || 0) > 0 ? `<tr class="deduction-row"><td>Advance Deduction</td><td>&minus; ${fmtINR(slip.advance_deduction)}</td></tr>` : ''}
    ${(slip.leave_payout_amt || 0) > 0 ? `<tr style="color:#389e0d"><td>Leave Encashment (${slip.leave_payout_days} day(s) &times; ${fmtINR(perDay)})</td><td>+ ${fmtINR(slip.leave_payout_amt)}</td></tr>` : ''}
    <tr class="net-row"><td>Net Salary Payable</td><td>${fmtINR(slip.net_salary)}</td></tr>
  </tbody>
</table>
${slip.notes ? `<div class="notes-box"><b>Notes:</b> ${slip.notes}</div>` : ''}
<div class="footer">Generated by MedFellow CRM &bull; ${dayjs().format('DD MMM YYYY HH:mm')} &bull; For official use only</div>
</body></html>`;
}

// ── Self Attendance ─────────────────────────────────────────────────────────
function SelfAttendance() {
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['attendance-today'],
    queryFn: () => attendanceAPI.today().then(res => res.data),
  });

  const { data: history = [] } = useQuery({
    queryKey: ['attendance-history'],
    queryFn: () => attendanceAPI.history(30).then(res => res.data),
  });

  const checkInMutation = useMutation({
    mutationFn: async () => {
      const { lat, lng } = await getCurrentLocation();
      return attendanceAPI.checkIn(lat, lng);
    },
    onSuccess: () => {
      setActionError('');
      queryClient.invalidateQueries({ queryKey: ['attendance-today'] });
      queryClient.invalidateQueries({ queryKey: ['attendance-history'] });
    },
    onError: (err) => setActionError(err.response?.data?.detail || err.message || 'Check-in failed'),
  });

  const checkOutMutation = useMutation({
    mutationFn: async () => {
      const { lat, lng } = await getCurrentLocation();
      return attendanceAPI.checkOut(lat, lng);
    },
    onSuccess: () => {
      setActionError('');
      queryClient.invalidateQueries({ queryKey: ['attendance-today'] });
      queryClient.invalidateQueries({ queryKey: ['attendance-history'] });
    },
    onError: (err) => setActionError(err.response?.data?.detail || err.message || 'Check-out failed'),
  });

  const record        = data?.record;
  const hasCheckedIn  = !!record?.check_in_at;
  const hasCheckedOut = !!record?.check_out_at;

  const historyColumns = [
    { title: 'Date',      dataIndex: 'date',         key: 'date',         render: (d) => dayjs(d).format('DD MMM YYYY') },
    { title: 'Check In',  dataIndex: 'check_in_at',  key: 'check_in_at',  render: fmtTime },
    { title: 'Check Out', dataIndex: 'check_out_at', key: 'check_out_at', render: fmtTime },
    { title: 'Hours',     key: 'hours',              render: (_, r) => hoursWorked(r.check_in_at, r.check_out_at) },
    {
      title: 'Status', dataIndex: 'status', key: 'status',
      render: (s) => <Tag color={STATUS_TAG[s]?.color || 'default'}>{STATUS_TAG[s]?.label || s}</Tag>,
    },
  ];

  return (
    <div>
      <Card style={{ marginBottom: 24 }}>
        {isLoading ? <Spin /> : (
          <>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  <ClockCircleOutlined /> Office hours: {data?.office_hours}
                </Text>
                <div style={{ fontSize: 12, color: '#8c8c8c' }}>
                  <EnvironmentOutlined /> You must be within {data?.office_radius_m}m of the office to check in/out
                </div>
              </div>
              {record?.status && (
                <Tag color={STATUS_TAG[record.status]?.color} style={{ fontSize: 13, padding: '4px 12px' }}>
                  {STATUS_TAG[record.status]?.label}
                </Tag>
              )}
            </div>

            <Space size={32} style={{ marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: 12, color: '#8c8c8c' }}>Check In</div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>{fmtTime(record?.check_in_at)}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: '#8c8c8c' }}>Check Out</div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>{fmtTime(record?.check_out_at)}</div>
              </div>
            </Space>

            {actionError && (
              <Alert type="error" showIcon message={actionError} style={{ marginBottom: 16 }} closable onClose={() => setActionError('')} />
            )}

            <Space>
              <Button type="primary" size="large" icon={<LoginOutlined />}
                loading={checkInMutation.isPending} disabled={hasCheckedIn}
                onClick={() => checkInMutation.mutate()}>
                {hasCheckedIn ? 'Checked In' : 'Check In'}
              </Button>
              <Button size="large" icon={<LogoutOutlined />}
                loading={checkOutMutation.isPending} disabled={!hasCheckedIn || hasCheckedOut}
                onClick={() => checkOutMutation.mutate()}>
                {hasCheckedOut ? 'Checked Out' : 'Check Out'}
              </Button>
            </Space>
          </>
        )}
      </Card>

      <Card title="Attendance History (Last 30 Days)">
        {history.length === 0
          ? <Empty description="No attendance records yet" />
          : <Table columns={historyColumns} dataSource={history} rowKey="id" pagination={{ pageSize: 10 }} size="small" />
        }
      </Card>
    </div>
  );
}

const STATUSES = [
  { value: 'present',             label: 'Present' },
  { value: 'late',                label: 'Late' },
  { value: 'left_early',          label: 'Left Early' },
  { value: 'late_and_left_early', label: 'Late & Left Early' },
  { value: 'absent',              label: 'Absent' },
];

// ── Team Attendance ─────────────────────────────────────────────────────────
function TeamAttendance() {
  const queryClient  = useQueryClient();
  const [date, setDate] = useState(dayjs());
  const [saving, setSaving] = useState(null); // user_email currently being saved

  const { data, isLoading } = useQuery({
    queryKey: ['attendance-team', date.format('YYYY-MM-DD')],
    queryFn: () => attendanceAPI.team(date.format('YYYY-MM-DD')).then(res => res.data),
  });

  const markMutation = useMutation({
    mutationFn: (payload) => attendanceAPI.adminMark(payload),
    onSuccess: (_, vars) => {
      message.success(`${vars.user_name} marked as ${STATUS_TAG[vars.status]?.label || vars.status}.`);
      setSaving(null);
      queryClient.invalidateQueries({ queryKey: ['attendance-team'] });
    },
    onError: (e) => { setSaving(null); message.error('Failed: ' + (e?.response?.data?.detail || e.message)); },
  });

  const handleMark = (row, status) => {
    setSaving(row.user_email);
    markMutation.mutate({
      user_email: row.user_email,
      user_name:  row.user_name,
      date:       date.format('YYYY-MM-DD'),
      status,
      check_in_at:  null,
      check_out_at: null,
    });
  };

  const columns = [
    { title: 'Name',      dataIndex: 'user_name', key: 'user_name', width: 160 },
    { title: 'Role',      dataIndex: 'role',      key: 'role',      width: 120 },
    { title: 'Check In',  dataIndex: 'check_in_at',  key: 'check_in_at',  width: 100, render: fmtTime },
    { title: 'Check Out', dataIndex: 'check_out_at', key: 'check_out_at', width: 100, render: fmtTime },
    { title: 'Hours',     key: 'hours', width: 90, render: (_, r) => hoursWorked(r.check_in_at, r.check_out_at) },
    {
      title: 'Mark Attendance', key: 'mark', width: 320,
      render: (_, row) => (
        <Space size={4} wrap>
          {STATUSES.map(s => (
            <Button
              key={s.value}
              size="small"
              type={row.status === s.value ? 'primary' : 'default'}
              danger={s.value === 'absent'}
              loading={saving === row.user_email}
              onClick={() => handleMark(row, s.value)}
              style={row.status === s.value ? {} : { opacity: 0.7 }}
            >
              {s.label}
            </Button>
          ))}
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="Team Attendance"
      extra={
        <DatePicker
          value={date}
          onChange={(d) => d && setDate(d)}
        />
      }
    >
      {isLoading
        ? <Spin />
        : <Table columns={columns} dataSource={data?.rows || []} rowKey="user_email" pagination={false} size="small" scroll={{ x: 900 }} />
      }
    </Card>
  );
}

function bulkSlipHTML(selectedSlips) {
  const bodies = selectedSlips.map((slip, i) => {
    const inner = generateSlipHTML(slip)
      .replace(/<!DOCTYPE html>[\s\S]*?<body[^>]*>/i, '')
      .replace(/<\/body>[\s\S]*$/i, '');
    return `<div class="slip-page">${inner}</div>`;
  });
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Salary Slips — Bulk Download</title>
<style>
  body{font-family:Arial,sans-serif;margin:0;padding:0;color:#333}
  .slip-page{max-width:750px;margin:40px auto;padding:20px;page-break-after:always}
  .slip-page:last-child{page-break-after:auto}
  .header{display:flex;align-items:center;justify-content:space-between;border-bottom:3px solid #1890ff;padding-bottom:16px;margin-bottom:24px}
  .header-logo img{height:64px;width:auto;display:block}
  .header-right{text-align:right}
  .slip-title{font-size:18px;font-weight:700;color:#1890ff}
  .slip-sub{font-size:13px;color:#666;margin-top:4px}
  .info-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:24px;background:#f8faff;padding:16px;border-radius:8px}
  .info-item label{font-size:11px;color:#888;display:block;margin-bottom:2px}
  .info-item span{font-weight:600;font-size:14px}
  table{width:100%;border-collapse:collapse;margin-bottom:24px}
  th{background:#1890ff;color:white;padding:9px 12px;text-align:left;font-size:13px}
  td{padding:8px 12px;border-bottom:1px solid #f0f0f0;font-size:13px}
  tr:nth-child(even) td{background:#fafafa}
  .net-row td{background:#f6ffed !important;font-weight:700;font-size:15px;color:#389e0d;border-top:2px solid #b7eb8f}
  .deduction-row td{color:#cf1322}
  .notes-box{background:#fffbe6;border:1px solid #ffe58f;padding:12px 16px;border-radius:6px;font-size:13px;margin-bottom:20px}
  .footer{text-align:center;font-size:11px;color:#999;margin-top:32px;border-top:1px solid #f0f0f0;padding-top:12px}
  @media print{.slip-page{margin:0;padding:16px}}
</style></head><body>${bodies.join('\n')}</body></html>`;
}

// ── Salary Slips List ────────────────────────────────────────────────────────
function SalarySlips() {
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const isAdmin = ['Super Admin', 'Manager', 'Team Leader'].includes(currentUser.role);
  const [filterMonth,   setFilterMonth]   = useState(null);
  const [filterUser,    setFilterUser]    = useState(isAdmin ? null : currentUser.email);
  const [selectedKeys,  setSelectedKeys]  = useState([]);

  const { data: usersData } = useQuery({
    queryKey: ['users-all'],
    queryFn: () => usersAPI.getAll().then(r => r.data?.users || r.data || []),
    enabled: isAdmin,
  });

  const { data: slips = [], isLoading } = useQuery({
    queryKey: ['salary-slips', filterMonth, filterUser],
    queryFn: () => attendanceAPI.listSlips(filterMonth || undefined, filterUser || undefined).then(r => r.data),
    onSuccess: () => setSelectedKeys([]),
  });

  const handleBulkPDF = () => {
    const selected = slips.filter(s => selectedKeys.includes(s.id));
    if (!selected.length) return;
    const w = window.open('', '_blank');
    w.document.write(bulkSlipHTML(selected));
    w.document.close();
    setTimeout(() => w.print(), 600);
  };

  const columns = [
    {
      title: 'Month', dataIndex: 'month', key: 'month', width: 130,
      render: m => dayjs((m || '2025-01') + '-01').format('MMMM YYYY'),
    },
    { title: 'Employee',     dataIndex: 'user_name',      key: 'user_name',      width: 150 },
    { title: 'Working Days', dataIndex: 'working_days',   key: 'working_days',   width: 100 },
    {
      title: 'Present', dataIndex: 'days_present', key: 'days_present', width: 80,
      render: v => <Tag color="green">{v}</Tag>,
    },
    {
      title: 'Late', dataIndex: 'days_late', key: 'days_late', width: 70,
      render: v => <Tag color={v > 0 ? 'orange' : 'default'}>{v}</Tag>,
    },
    {
      title: 'Absent', dataIndex: 'days_absent', key: 'days_absent', width: 80,
      render: v => <Tag color={v > 0 ? 'red' : 'default'}>{v}</Tag>,
    },
    {
      title: 'Gross', dataIndex: 'gross_salary', key: 'gross_salary', width: 120,
      render: v => fmtINR(v),
    },
    {
      title: 'Deduction', dataIndex: 'total_deduction', key: 'total_deduction', width: 115,
      render: v => <span style={{ color: '#cf1322' }}>− {fmtINR(v)}</span>,
    },
    {
      title: 'Net Salary', dataIndex: 'net_salary', key: 'net_salary', width: 130,
      render: v => <span style={{ color: '#389e0d', fontWeight: 700 }}>{fmtINR(v)}</span>,
    },
    {
      title: 'Generated By', dataIndex: 'generated_by', key: 'generated_by', width: 120,
      render: v => v ? v.split('@')[0] : '—',
    },
    {
      title: '', key: 'actions', width: 90, fixed: 'right',
      render: (_, slip) => (
        <Button size="small" icon={<FilePdfOutlined />} onClick={() => {
          const w = window.open('', '_blank');
          w.document.write(generateSlipHTML(slip));
          w.document.close();
          setTimeout(() => w.print(), 500);
        }}>
          PDF
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <div>
            <div style={{ fontSize: 11, color: '#8c8c8c', marginBottom: 4 }}>Month</div>
            <DatePicker
              picker="month"
              value={filterMonth ? dayjs(filterMonth + '-01') : null}
              onChange={d => { setFilterMonth(d ? d.format('YYYY-MM') : null); setSelectedKeys([]); }}
              allowClear
              placeholder="All months"
            />
          </div>
          {isAdmin && (
            <div>
              <div style={{ fontSize: 11, color: '#8c8c8c', marginBottom: 4 }}>Employee</div>
              <Select
                style={{ width: 220 }} placeholder="All employees" allowClear
                value={filterUser} onChange={v => { setFilterUser(v); setSelectedKeys([]); }}
                showSearch optionFilterProp="label"
              >
                {(usersData || []).map(u => (
                  <Option key={u.email} value={u.email} label={u.full_name}>{u.full_name}</Option>
                ))}
              </Select>
            </div>
          )}
          {selectedKeys.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <Button
                type="primary" icon={<FilePdfOutlined />}
                onClick={handleBulkPDF}
              >
                Download {selectedKeys.length} Slip{selectedKeys.length > 1 ? 's' : ''} as PDF
              </Button>
            </div>
          )}
        </Space>
      </Card>

      <Card
        title={
          <Space>
            <DollarOutlined />Salary Slips
            {selectedKeys.length > 0 && (
              <Tag color="blue">{selectedKeys.length} selected</Tag>
            )}
          </Space>
        }
        extra={
          slips.length > 0 && (
            <Space size={8}>
              <Button size="small" onClick={() => setSelectedKeys(slips.map(s => s.id))}>
                Select All
              </Button>
              {selectedKeys.length > 0 && (
                <Button size="small" onClick={() => setSelectedKeys([])}>Clear</Button>
              )}
            </Space>
          )
        }
      >
        {isLoading ? <Spin /> : slips.length === 0
          ? <Empty description="No salary slips saved yet. Generate one from the Reports tab." />
          : (
            <Table
              columns={columns}
              dataSource={slips}
              rowKey="id"
              size="small"
              pagination={{ pageSize: 20 }}
              scroll={{ x: 1200 }}
              rowSelection={{
                selectedRowKeys: selectedKeys,
                onChange: setSelectedKeys,
                preserveSelectedRowKeys: false,
              }}
            />
          )
        }
      </Card>
    </div>
  );
}

// ── Reports + Salary Calculator ─────────────────────────────────────────────
function AttendanceReport() {
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const isAdmin     = ['Super Admin', 'Manager', 'Team Leader'].includes(currentUser.role);

  const [dateRange,           setDateRange]           = useState([dayjs().startOf('month'), dayjs()]);
  const [selectedUser,        setSelectedUser]        = useState(isAdmin ? null : currentUser.email);
  const [monthlySalary,       setMonthlySalary]       = useState('');
  const [lateDeductionPerDay, setLateDeductionPerDay] = useState(0);
  const [slipNotes,           setSlipNotes]           = useState('');
  const [leavesUsed,          setLeavesUsed]          = useState(0);
  const [advanceDeduction,    setAdvanceDeduction]    = useState(0);
  const [selectedAdvanceId,   setSelectedAdvanceId]   = useState(null);

  const { data: usersData } = useQuery({
    queryKey: ['users-all'],
    queryFn:  () => usersAPI.getAll().then(r => r.data?.users || r.data || []),
    enabled:  isAdmin,
  });

  const dateFrom = dateRange[0]?.format('YYYY-MM-DD');
  const dateTo   = dateRange[1]?.format('YYYY-MM-DD');

  const { data: reportData, isLoading } = useQuery({
    queryKey: ['attendance-report', dateFrom, dateTo, selectedUser],
    queryFn:  () => attendanceAPI.report(dateFrom, dateTo, selectedUser || undefined).then(r => r.data),
    enabled:  !!(dateFrom && dateTo),
  });

  const slipMonth = dateRange[0]?.format('YYYY-MM');
  const leaveEmployee = selectedUser || (isAdmin ? null : currentUser.email);

  const { data: leaveBalance } = useQuery({
    queryKey: ['leave-balance', leaveEmployee, slipMonth],
    queryFn:  () => attendanceAPI.getLeaveBalance(leaveEmployee, slipMonth).then(r => r.data),
    enabled:  !!(leaveEmployee && slipMonth),
  });

  const { data: pendingAdvances = [] } = useQuery({
    queryKey: ['advances-pending', leaveEmployee],
    queryFn:  () => attendanceAPI.listAdvances(leaveEmployee, 'pending').then(r => r.data),
    enabled:  !!leaveEmployee,
  });

  const saveMutation = useMutation({
    mutationFn: (payload) => attendanceAPI.saveSlip(payload),
    onSuccess: () => message.success('Salary slip saved. View it in the Salary Slips tab.'),
    onError:   (e) => message.error('Failed to save: ' + (e?.response?.data?.detail || e.message)),
  });

  const dailyList = useMemo(() => {
    if (!dateRange[0] || !dateRange[1]) return [];
    const records = reportData?.records || [];
    const today   = dayjs();
    const byDate  = {};
    records.forEach(r => { byDate[r.date] = r; });
    const rows = [];
    let cur = dateRange[0].startOf('day');
    const end = dateRange[1].startOf('day');
    while (!cur.isAfter(end)) {
      const dateStr  = cur.format('YYYY-MM-DD');
      const isSun    = cur.day() === 0;
      const isFuture = cur.isAfter(today, 'day');
      const rec      = byDate[dateStr];
      rows.push({
        key: dateStr, date: dateStr, dayName: cur.format('ddd'),
        isSunday: isSun, isFuture,
        status:       isSun ? 'week_off' : isFuture ? null : (rec?.status || 'absent'),
        check_in_at:  rec?.check_in_at  || null,
        check_out_at: rec?.check_out_at || null,
      });
      cur = cur.add(1, 'day');
    }
    return rows;
  }, [reportData, dateRange]);

  const summary = useMemo(() => {
    const working       = dailyList.filter(r => !r.isFuture).length;  // ALL days incl. Sundays
    const weekOffs      = dailyList.filter(r => r.isSunday && !r.isFuture).length;
    const present       = dailyList.filter(r => r.status === 'present').length;
    const late          = dailyList.filter(r => r.status === 'late').length;
    const leftEarly     = dailyList.filter(r => r.status === 'left_early').length;
    const lateLeftEarly = dailyList.filter(r => r.status === 'late_and_left_early').length;
    const absent        = dailyList.filter(r => r.status === 'absent').length;
    const attended      = present + late + leftEarly + lateLeftEarly + weekOffs;
    return { working, weekOffs, present, late, leftEarly, lateLeftEarly, absent, attended };
  }, [dailyList]);

  // Leave balance calculation for this month
  const leaveCalc = useMemo(() => {
    const opening   = parseFloat(leaveBalance?.opening_balance ?? 0);
    const accrued   = 1;
    const used      = parseFloat(leavesUsed || 0);
    const rawClose  = opening + accrued - used;
    const payoutDays = Math.max(0, rawClose - 3);
    const closing   = Math.min(Math.max(rawClose, 0), 3);
    return { opening, accrued, available: opening + accrued, used, closing, payoutDays };
  }, [leaveBalance, leavesUsed]);

  const salaryCalc = useMemo(() => {
    const sal = parseFloat(monthlySalary);
    if (!sal || summary.working === 0) return null;
    const perDay          = sal / summary.working;
    // Absences: reduce by leaves used this month (those are paid)
    const effectiveAbsent = Math.max(0, summary.absent - leaveCalc.used);
    const absentDeduction = effectiveAbsent * perDay;
    const lateDeduction   = summary.late * parseFloat(lateDeductionPerDay || 0);
    const advDeduction    = parseFloat(advanceDeduction || 0);
    // Leave payout when balance would exceed 3 months
    const leavePayoutAmt  = leaveCalc.payoutDays * perDay;
    const totalDeduction  = absentDeduction + lateDeduction + advDeduction;
    const netSalary       = Math.max(0, sal - totalDeduction + leavePayoutAmt);
    return { perDay, effectiveAbsent, absentDeduction, lateDeduction, advDeduction,
             leavePayoutAmt, totalDeduction, netSalary };
  }, [monthlySalary, lateDeductionPerDay, advanceDeduction, summary, leaveCalc]);

  const handleDownloadCSV = async () => {
    if (!dateFrom || !dateTo) return;
    try {
      const res = await attendanceAPI.exportCsv(dateFrom, dateTo, selectedUser || undefined);
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
      const a   = document.createElement('a');
      a.href     = url;
      a.download = `attendance_${dateFrom}_to_${dateTo}${selectedUser ? '_' + selectedUser.split('@')[0] : ''}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { console.error('CSV export failed', e); }
  };

  const buildSlipPayload = () => {
    const employeeEmail = selectedUser || currentUser.email;
    const employeeName  = (usersData || []).find(u => u.email === employeeEmail)?.full_name || employeeEmail;
    return {
      user_email:            employeeEmail,
      user_name:             employeeName,
      month:                 slipMonth,
      gross_salary:          parseFloat(monthlySalary),
      working_days:          summary.working,
      days_present:          summary.present,
      days_late:             summary.late,
      days_left_early:       summary.leftEarly + summary.lateLeftEarly,
      days_absent:           summary.absent,
      paid_leaves_allowed:   leaveCalc.used,
      effective_absent:      salaryCalc.effectiveAbsent,
      late_deduction_per_day: parseFloat(lateDeductionPerDay || 0),
      late_deduction_total:  salaryCalc.lateDeduction,
      absent_deduction:      salaryCalc.absentDeduction,
      total_deduction:       salaryCalc.totalDeduction,
      net_salary:            salaryCalc.netSalary,
      advance_deduction:     salaryCalc.advDeduction,
      leave_opening:         leaveCalc.opening,
      leaves_used:           leaveCalc.used,
      leave_closing:         leaveCalc.closing,
      leave_payout_days:     leaveCalc.payoutDays,
      leave_payout_amt:      salaryCalc.leavePayoutAmt,
      notes:                 slipNotes || null,
    };
  };

  const handleSaveSlipFull = async () => {
    if (!salaryCalc) return;
    const employeeEmail = selectedUser || currentUser.email;
    const employeeName  = (usersData || []).find(u => u.email === employeeEmail)?.full_name || employeeEmail;
    // 1. Save the slip
    saveMutation.mutate(buildSlipPayload());
    // 2. Save/update leave balance
    try {
      await attendanceAPI.saveLeaveBalance({
        user_email: employeeEmail, user_name: employeeName,
        month: slipMonth, opening_balance: leaveCalc.opening,
        used: leaveCalc.used, payout_amount: salaryCalc.leavePayoutAmt,
      });
    } catch (e) { console.error('Leave balance save failed', e); }
    // 3. Mark advance as deducted if one was selected
    if (selectedAdvanceId && salaryCalc.advDeduction > 0) {
      try { await attendanceAPI.markAdvanceDeducted(selectedAdvanceId); } catch (e) {}
    }
  };

  const handleDownloadSlipPDF = () => {
    if (!salaryCalc) return;
    const slip = buildSlipPayload();
    const w = window.open('', '_blank');
    w.document.write(generateSlipHTML(slip));
    w.document.close();
    setTimeout(() => w.print(), 500);
  };

  const tableColumns = [
    {
      title: 'Date', dataIndex: 'date', key: 'date', width: 120,
      render: (d, r) => (
        <span style={{ color: r.isSunday ? '#722ed1' : undefined }}>
          {dayjs(d).format('DD MMM')}
        </span>
      ),
    },
    {
      title: 'Day', dataIndex: 'dayName', key: 'dayName', width: 60,
      render: (d, r) => <span style={{ color: r.isSunday ? '#722ed1' : undefined }}>{d}</span>,
    },
    {
      title: 'Status', dataIndex: 'status', key: 'status', width: 160,
      render: (s, r) => {
        if (r.isFuture || !s) return <Text type="secondary">—</Text>;
        return <Tag color={STATUS_TAG[s]?.color || 'default'}>{STATUS_TAG[s]?.label || s}</Tag>;
      },
    },
    { title: 'Check In',  dataIndex: 'check_in_at',  key: 'check_in_at',  width: 110, render: fmtTime },
    { title: 'Check Out', dataIndex: 'check_out_at', key: 'check_out_at', width: 110, render: fmtTime },
    { title: 'Hours', key: 'hours', width: 90, render: (_, r) => hoursWorked(r.check_in_at, r.check_out_at) },
  ];

  return (
    <div>
      {/* ── Filters ── */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <div>
            <div style={{ fontSize: 11, color: '#8c8c8c', marginBottom: 4 }}>Date Range</div>
            <DatePicker.RangePicker
              value={dateRange}
              onChange={(range) => range && range[0] && range[1] && setDateRange(range)}
              disabledDate={(d) => d && d > dayjs().endOf('day')}
              allowClear={false}
              presets={[
                { label: 'This Month',   value: [dayjs().startOf('month'), dayjs()] },
                { label: 'Last Month',   value: [dayjs().subtract(1, 'month').startOf('month'), dayjs().subtract(1, 'month').endOf('month')] },
                { label: 'Last 7 Days',  value: [dayjs().subtract(6, 'day'), dayjs()] },
                { label: 'Last 30 Days', value: [dayjs().subtract(29, 'day'), dayjs()] },
                { label: 'This Week',    value: [dayjs().startOf('week'), dayjs()] },
              ]}
            />
          </div>
          {isAdmin && (
            <div>
              <div style={{ fontSize: 11, color: '#8c8c8c', marginBottom: 4 }}>Employee</div>
              <Select
                style={{ width: 220 }} placeholder="All employees" allowClear
                value={selectedUser} onChange={setSelectedUser} showSearch optionFilterProp="label"
              >
                {(usersData || []).map(u => (
                  <Option key={u.email} value={u.email} label={u.full_name}>
                    {u.full_name} <Text type="secondary" style={{ fontSize: 11 }}>({u.role})</Text>
                  </Option>
                ))}
              </Select>
            </div>
          )}
          <div style={{ marginTop: 20 }}>
            <Button icon={<DownloadOutlined />} onClick={handleDownloadCSV}>Download CSV</Button>
          </div>
        </Space>
      </Card>

      {/* ── Summary stats ── */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        {[
          { label: 'Total Days',       value: summary.working,                           color: '#1890ff' },
          { label: 'Days Came',        value: summary.present + summary.late + summary.leftEarly + summary.lateLeftEarly, color: '#52c41a' },
          { label: 'Week Offs (Sun)',  value: summary.weekOffs,                          color: '#722ed1' },
          { label: 'Late',             value: summary.late,                              color: '#fa8c16' },
          { label: 'Left Early',       value: summary.leftEarly + summary.lateLeftEarly, color: '#fadb14' },
          { label: 'Absent',           value: summary.absent,                            color: '#ff4d4f' },
        ].map(s => (
          <Col key={s.label} xs={12} sm={8} md={4} style={{ marginBottom: 8 }}>
            <Card size="small" bodyStyle={{ padding: '12px 16px' }}>
              <Statistic
                title={<span style={{ fontSize: 11 }}>{s.label}</span>}
                value={s.value}
                valueStyle={{ color: s.color, fontSize: 22, fontWeight: 700 }}
              />
            </Card>
          </Col>
        ))}
      </Row>
      {/* payable days = days came + week offs */}
      <div style={{ marginBottom: 12, fontSize: 13, color: '#595959' }}>
        <span style={{ fontWeight: 600 }}>Payable days:</span>{' '}
        {summary.present + summary.late + summary.leftEarly + summary.lateLeftEarly} came
        {summary.weekOffs > 0 && <> + {summary.weekOffs} week off</>}
        {' '}= <span style={{ fontWeight: 700, color: '#389e0d' }}>{summary.attended}</span>
        {' '}out of {summary.working} total days
        {summary.absent > 0 && <span style={{ color: '#ff4d4f' }}> · {summary.absent} absent</span>}
      </div>

      {/* ── Daily table ── */}
      <Card
        title={<Space><CalendarOutlined />{dateRange[0]?.format('DD MMM YYYY')} → {dateRange[1]?.format('DD MMM YYYY')} — Attendance Report</Space>}
        style={{ marginBottom: 16 }}
      >
        {isLoading ? <Spin /> : dailyList.length === 0 ? <Empty description="No data" /> : (
          <Table
            columns={tableColumns} dataSource={dailyList} rowKey="key"
            size="small" pagination={false}
            rowClassName={(r) => r.isSunday ? 'ant-table-row-sunday' : ''}
            scroll={{ y: 420 }}
          />
        )}
      </Card>

      {/* ── Salary Calculator ── */}
      {(isAdmin || selectedUser === currentUser.email) && (
        <Card title={<Space><DollarOutlined />Salary Calculator &amp; Slip Generator</Space>} style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col xs={24} sm={6}>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 6 }}>Monthly Gross Salary (₹)</div>
                <InputNumber
                  style={{ width: '100%' }} placeholder="e.g. 25000" min={0}
                  value={monthlySalary} onChange={setMonthlySalary}
                  formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={v => v.replace(/,/g, '')} size="large"
                />
              </div>
            </Col>
            <Col xs={24} sm={6}>
              <Tooltip title="Amount deducted per late-arrival day. Set 0 to ignore late arrivals.">
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 6 }}>
                    Late Entry Deduction / Day (₹) <span style={{ color: '#fa8c16' }}>● {summary.late} late day{summary.late !== 1 ? 's' : ''}</span>
                  </div>
                  <InputNumber
                    style={{ width: '100%' }} placeholder="e.g. 200" min={0}
                    value={lateDeductionPerDay} onChange={(v) => setLateDeductionPerDay(v ?? 0)}
                    formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                    parser={v => v.replace(/,/g, '')} size="large"
                  />
                </div>
              </Tooltip>
            </Col>
            <Col xs={24} sm={6}>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 6 }}>Notes (for slip)</div>
                <TextArea rows={2} placeholder="e.g. Includes bonus, incentive…" value={slipNotes} onChange={e => setSlipNotes(e.target.value)} />
              </div>
            </Col>
          </Row>

          {salaryCalc ? (
            <>
              <Divider style={{ margin: '4px 0 16px' }} />
              <Row gutter={12} style={{ marginBottom: 12 }}>
                <Col xs={12} sm={6} style={{ marginBottom: 8 }}>
                  <Card size="small" bodyStyle={{ padding: '12px 16px', background: '#f6ffed', borderColor: '#b7eb8f' }}>
                    <div style={{ fontSize: 11, color: '#8c8c8c' }}>Total Days (incl. Sundays)</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#52c41a' }}>{summary.working}</div>
                  </Card>
                </Col>
                <Col xs={12} sm={6} style={{ marginBottom: 8 }}>
                  <Card size="small" bodyStyle={{ padding: '12px 16px', background: '#e6f7ff', borderColor: '#91d5ff' }}>
                    <div style={{ fontSize: 11, color: '#8c8c8c' }}>Payable Days (came + Sun)</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#1890ff' }}>{summary.attended}</div>
                    <div style={{ fontSize: 11, color: '#8c8c8c' }}>{summary.attended - summary.weekOffs} came + {summary.weekOffs} Sun</div>
                  </Card>
                </Col>
                <Col xs={12} sm={6} style={{ marginBottom: 8 }}>
                  <Card size="small" bodyStyle={{ padding: '12px 16px', background: '#fff7e6', borderColor: '#ffd591' }}>
                    <div style={{ fontSize: 11, color: '#8c8c8c' }}>Late Days (deduction)</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#fa8c16' }}>{summary.late}</div>
                    {lateDeductionPerDay > 0 && (
                      <div style={{ fontSize: 11, color: '#fa8c16' }}>− {fmtINR(salaryCalc.lateDeduction)}</div>
                    )}
                  </Card>
                </Col>
                <Col xs={12} sm={6} style={{ marginBottom: 8 }}>
                  <Card size="small" bodyStyle={{ padding: '12px 16px', background: '#fff2e8', borderColor: '#ffbb96' }}>
                    <div style={{ fontSize: 11, color: '#8c8c8c' }}>Effective Absent (after {leaveCalc.used} PL)</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#fa541c' }}>{salaryCalc.effectiveAbsent}</div>
                  </Card>
                </Col>
              </Row>

              <Row gutter={12}>
                <Col xs={24} sm={8} style={{ marginBottom: 8 }}>
                  <Card size="small" bodyStyle={{ padding: '14px 16px', background: '#f9f0ff', borderColor: '#d3adf7' }}>
                    <div style={{ fontSize: 11, color: '#8c8c8c' }}>Per Day Rate</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#722ed1' }}>{fmtINR(salaryCalc.perDay)}</div>
                  </Card>
                </Col>
                <Col xs={24} sm={8} style={{ marginBottom: 8 }}>
                  <Card size="small" bodyStyle={{ padding: '14px 16px', background: '#fff1f0', borderColor: '#ffa39e' }}>
                    <div style={{ fontSize: 12, color: '#8c8c8c' }}>Total Deduction</div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: '#cf1322' }}>− {fmtINR(salaryCalc.totalDeduction)}</div>
                    <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 4 }}>
                      {salaryCalc.effectiveAbsent > 0 && `Absent: ${fmtINR(salaryCalc.absentDeduction)}`}
                      {salaryCalc.effectiveAbsent > 0 && salaryCalc.lateDeduction > 0 && ' + '}
                      {salaryCalc.lateDeduction > 0 && `Late: ${fmtINR(salaryCalc.lateDeduction)}`}
                      {salaryCalc.advDeduction > 0 && ` + Advance: ${fmtINR(salaryCalc.advDeduction)}`}
                    </div>
                  </Card>
                </Col>
                <Col xs={24} sm={8} style={{ marginBottom: 8 }}>
                  <Card size="small" bodyStyle={{ padding: '14px 16px', background: '#f6ffed', borderColor: '#b7eb8f' }}>
                    <div style={{ fontSize: 12, color: '#8c8c8c' }}>Net Salary Payable</div>
                    <div style={{ fontSize: 26, fontWeight: 700, color: '#389e0d' }}>{fmtINR(salaryCalc.netSalary)}</div>
                    <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 4 }}>
                      {fmtINR(parseFloat(monthlySalary))} − {fmtINR(salaryCalc.totalDeduction)}
                      {salaryCalc.leavePayoutAmt > 0 && ` + ${fmtINR(salaryCalc.leavePayoutAmt)} leave encashment`}
                    </div>
                  </Card>
                </Col>
              </Row>

              {/* ── Leave Balance ── */}
              <Divider orientation="left" style={{ margin: '16px 0 12px', fontSize: 13 }}>Leave Balance</Divider>
              <Row gutter={12} style={{ marginBottom: 12 }} align="middle">
                <Col xs={24} sm={14}>
                  <div style={{ background: '#f0f5ff', border: '1px solid #adc6ff', borderRadius: 8, padding: '12px 16px', fontSize: 13 }}>
                    <Space size={16} wrap>
                      <span>Opening: <b>{leaveCalc.opening}</b></span>
                      <span>+ Accrued: <b>1</b></span>
                      <span>= Available: <b style={{ color: '#1890ff' }}>{leaveCalc.available}</b></span>
                      {leaveCalc.payoutDays > 0 && (
                        <span style={{ color: '#389e0d', fontWeight: 600 }}>
                          ⚠ {leaveCalc.payoutDays} day(s) encashed ({fmtINR(salaryCalc.leavePayoutAmt)})
                        </span>
                      )}
                    </Space>
                    <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 6 }}>
                      Closing balance: <b>{leaveCalc.closing}</b>/3 max carry-forward
                    </div>
                  </div>
                </Col>
                <Col xs={24} sm={10}>
                  <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 4 }}>Leaves used this month (paid, no deduction)</div>
                  <InputNumber
                    style={{ width: '100%' }} min={0} max={leaveCalc.available}
                    value={leavesUsed} onChange={v => setLeavesUsed(v ?? 0)}
                    placeholder="0" size="large"
                  />
                </Col>
              </Row>

              {/* ── Advance Deduction ── */}
              <Divider orientation="left" style={{ margin: '12px 0 12px', fontSize: 13 }}>Advance Deduction</Divider>
              <Row gutter={12} style={{ marginBottom: 12 }} align="middle">
                {pendingAdvances.length > 0 && (
                  <Col xs={24} sm={14} style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 4 }}>Select a pending advance to deduct</div>
                    <Select
                      style={{ width: '100%' }} allowClear placeholder="No advance"
                      value={selectedAdvanceId}
                      onChange={(val, opt) => {
                        setSelectedAdvanceId(val || null);
                        const adv = pendingAdvances.find(a => a.id === val);
                        setAdvanceDeduction(adv ? adv.amount : 0);
                      }}
                    >
                      {pendingAdvances.map(a => (
                        <Option key={a.id} value={a.id}>
                          {fmtINR(a.amount)} — given {dayjs(a.given_date).format('DD MMM YYYY')}
                          {a.notes ? ` (${a.notes})` : ''}
                        </Option>
                      ))}
                    </Select>
                  </Col>
                )}
                <Col xs={24} sm={10} style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 4 }}>Advance amount to deduct (₹)</div>
                  <InputNumber
                    style={{ width: '100%' }} min={0}
                    value={advanceDeduction} onChange={v => { setAdvanceDeduction(v ?? 0); setSelectedAdvanceId(null); }}
                    formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                    parser={v => v.replace(/,/g, '')} size="large" placeholder="0"
                  />
                </Col>
              </Row>

              <Divider style={{ margin: '12px 0 12px' }} />
              <Space>
                <Button
                  type="primary" icon={<SaveOutlined />}
                  onClick={handleSaveSlipFull}
                  loading={saveMutation.isPending}
                  disabled={!selectedUser && isAdmin}
                >
                  Save Salary Slip
                </Button>
                <Button icon={<FilePdfOutlined />} onClick={handleDownloadSlipPDF}>
                  Download PDF
                </Button>
              </Space>
              {!selectedUser && isAdmin && (
                <div style={{ marginTop: 8, fontSize: 12, color: '#fa8c16' }}>
                  Select a specific employee above to save their salary slip.
                </div>
              )}
            </>
          ) : (
            <Text type="secondary">Enter the monthly gross salary above to calculate net pay.</Text>
          )}
        </Card>
      )}
    </div>
  );
}

// ── Advances Panel (admin) ────────────────────────────────────────────────────
function AdvancesPanel() {
  const queryClient = useQueryClient();
  const [filterUser,   setFilterUser]   = useState(null);
  const [filterStatus, setFilterStatus] = useState(null);
  const [showForm,     setShowForm]     = useState(false);
  const [formEmail,    setFormEmail]    = useState(null);
  const [formAmount,   setFormAmount]   = useState('');
  const [formDate,     setFormDate]     = useState(dayjs());
  const [formNotes,    setFormNotes]    = useState('');

  const { data: usersData = [] } = useQuery({
    queryKey: ['users-all'],
    queryFn: () => usersAPI.getAll().then(r => r.data?.users || r.data || []),
  });

  const { data: advances = [], isLoading } = useQuery({
    queryKey: ['advances-all', filterUser, filterStatus],
    queryFn: () => attendanceAPI.listAdvances(filterUser || undefined, filterStatus || undefined).then(r => r.data),
  });

  const createMutation = useMutation({
    mutationFn: (payload) => attendanceAPI.createAdvance(payload),
    onSuccess: () => {
      message.success('Advance recorded.');
      setShowForm(false);
      setFormEmail(null);
      setFormAmount('');
      setFormNotes('');
      setFormDate(dayjs());
      queryClient.invalidateQueries({ queryKey: ['advances-all'] });
      queryClient.invalidateQueries({ queryKey: ['advances-pending'] });
    },
    onError: (e) => message.error('Failed: ' + (e?.response?.data?.detail || e.message)),
  });

  const handleCreate = () => {
    if (!formEmail) { message.warning('Select an employee.'); return; }
    if (!formAmount || parseFloat(formAmount) <= 0) { message.warning('Enter a valid amount.'); return; }
    const emp = usersData.find(u => u.email === formEmail);
    createMutation.mutate({
      user_email: formEmail,
      user_name:  emp?.full_name || formEmail,
      amount:     parseFloat(String(formAmount).replace(/,/g, '')),
      given_date: formDate.format('YYYY-MM-DD'),
      notes:      formNotes || null,
    });
  };

  const columns = [
    { title: 'Employee',    dataIndex: 'user_name',      key: 'user_name',  width: 160 },
    { title: 'Amount',      dataIndex: 'amount',         key: 'amount',     width: 120, render: v => fmtINR(v) },
    { title: 'Given Date',  dataIndex: 'given_date',     key: 'given_date', width: 130, render: d => dayjs(d).format('DD MMM YYYY') },
    {
      title: 'Status', dataIndex: 'status', key: 'status', width: 110,
      render: s => <Tag color={s === 'pending' ? 'orange' : 'green'}>{s === 'pending' ? 'Pending' : 'Deducted'}</Tag>,
    },
    { title: 'Notes',       dataIndex: 'notes',          key: 'notes' },
    { title: 'Deducted On', dataIndex: 'deducted_date',  key: 'deducted_date', width: 130, render: d => d ? dayjs(d).format('DD MMM YYYY') : '—' },
  ];

  return (
    <div>
      <Card
        title={<Space><DollarOutlined />Salary Advances</Space>}
        extra={
          <Button
            type={showForm ? 'default' : 'primary'}
            icon={<PlusOutlined />}
            onClick={() => setShowForm(v => !v)}
          >
            {showForm ? 'Cancel' : 'Record Advance'}
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        {showForm && (
          <>
            <Row gutter={12} style={{ marginBottom: 12 }}>
              <Col xs={24} sm={6}>
                <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 4 }}>Employee</div>
                <Select
                  style={{ width: '100%' }} placeholder="Select employee"
                  value={formEmail} onChange={setFormEmail}
                  showSearch optionFilterProp="label"
                >
                  {usersData.map(u => (
                    <Option key={u.email} value={u.email} label={u.full_name}>{u.full_name}</Option>
                  ))}
                </Select>
              </Col>
              <Col xs={24} sm={5}>
                <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 4 }}>Amount (₹)</div>
                <InputNumber
                  style={{ width: '100%' }} min={1} placeholder="e.g. 5000"
                  value={formAmount} onChange={setFormAmount}
                  formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={v => v.replace(/,/g, '')}
                />
              </Col>
              <Col xs={24} sm={5}>
                <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 4 }}>Given Date</div>
                <DatePicker style={{ width: '100%' }} value={formDate} onChange={d => d && setFormDate(d)} />
              </Col>
              <Col xs={24} sm={5}>
                <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 4 }}>Notes</div>
                <Input placeholder="Optional notes" value={formNotes} onChange={e => setFormNotes(e.target.value)} />
              </Col>
              <Col xs={24} sm={3} style={{ display: 'flex', alignItems: 'flex-end' }}>
                <Button type="primary" onClick={handleCreate} loading={createMutation.isPending} block>Save</Button>
              </Col>
            </Row>
            <Divider style={{ margin: '4px 0 16px' }} />
          </>
        )}

        <Space wrap style={{ marginBottom: 12 }}>
          <Select
            style={{ width: 200 }} placeholder="Filter by employee" allowClear
            value={filterUser} onChange={setFilterUser} showSearch optionFilterProp="label"
          >
            {usersData.map(u => (
              <Option key={u.email} value={u.email} label={u.full_name}>{u.full_name}</Option>
            ))}
          </Select>
          <Select
            style={{ width: 150 }} placeholder="All statuses" allowClear
            value={filterStatus} onChange={setFilterStatus}
          >
            <Option value="pending">Pending</Option>
            <Option value="deducted">Deducted</Option>
          </Select>
        </Space>

        {isLoading ? <Spin /> : advances.length === 0
          ? <Empty description="No advances recorded yet." />
          : (
            <Table
              columns={columns} dataSource={advances}
              rowKey="id" size="small" pagination={{ pageSize: 20 }}
            />
          )
        }
      </Card>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function AttendancePage() {
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const isAdmin     = ['Super Admin', 'Manager', 'Team Leader'].includes(currentUser.role);

  const items = [
    { key: 'self', label: <Space><ClockCircleOutlined />My Attendance</Space>, children: <SelfAttendance /> },
  ];
  if (isAdmin) {
    items.push({ key: 'team', label: <Space><TeamOutlined />Team Attendance</Space>, children: <TeamAttendance /> });
  }
  items.push(
    { key: 'reports', label: <Space><FileTextOutlined />Reports</Space>, children: <AttendanceReport /> },
    { key: 'slips',   label: <Space><DollarOutlined />{isAdmin ? 'Salary Slips' : 'My Pay Slips'}</Space>, children: <SalarySlips /> },
  );
  if (isAdmin) {
    items.push({ key: 'advances', label: <Space><DollarOutlined />Advances</Space>, children: <AdvancesPanel /> });
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <EnvironmentOutlined style={{ marginRight: 8 }} />Attendance
        </Title>
        <Text type="secondary">Check in/out at the office and view reports.</Text>
      </div>
      <Tabs items={items} />
    </div>
  );
}
