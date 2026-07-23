import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card, Button, Tag, Table, Typography, Space, Alert, Spin, Tabs, DatePicker,
  Empty, Select, InputNumber, Row, Col, Statistic, Divider, Tooltip,
} from 'antd';
import {
  LoginOutlined, LogoutOutlined, EnvironmentOutlined, ClockCircleOutlined,
  CheckCircleOutlined, WarningOutlined, DownloadOutlined, FileTextOutlined,
  DollarOutlined, TeamOutlined, CalendarOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { attendanceAPI, usersAPI } from '../api/api';

const { Title, Text } = Typography;
const { Option } = Select;

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

  const record      = data?.record;
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

// ── Team Attendance ─────────────────────────────────────────────────────────
function TeamAttendance() {
  const [date, setDate] = useState(dayjs());

  const { data, isLoading } = useQuery({
    queryKey: ['attendance-team', date.format('YYYY-MM-DD')],
    queryFn: () => attendanceAPI.team(date.format('YYYY-MM-DD')).then(res => res.data),
  });

  const columns = [
    { title: 'Name', dataIndex: 'user_name', key: 'user_name' },
    { title: 'Role', dataIndex: 'role',      key: 'role' },
    { title: 'Check In',  dataIndex: 'check_in_at',  key: 'check_in_at',  render: fmtTime },
    { title: 'Check Out', dataIndex: 'check_out_at', key: 'check_out_at', render: fmtTime },
    {
      title: 'Status', dataIndex: 'status', key: 'status',
      render: (s) => (
        <Tag color={STATUS_TAG[s]?.color || 'default'}
          icon={s === 'absent' ? <WarningOutlined /> : <CheckCircleOutlined />}>
          {STATUS_TAG[s]?.label || s}
        </Tag>
      ),
    },
  ];

  return (
    <Card
      title="Team Attendance"
      extra={<DatePicker value={date} onChange={(d) => d && setDate(d)} disabledDate={(d) => d && d > dayjs().endOf('day')} />}
    >
      {isLoading
        ? <Spin />
        : <Table columns={columns} dataSource={data?.rows || []} rowKey="user_email" pagination={false} size="small" />
      }
    </Card>
  );
}

// ── Reports + Salary Calculator ─────────────────────────────────────────────
function AttendanceReport() {
  const currentUser   = JSON.parse(localStorage.getItem('user') || '{}');
  const isAdmin       = ['Super Admin', 'Manager', 'Team Leader'].includes(currentUser.role);

  const [month,        setMonth]        = useState(dayjs());
  const [selectedUser, setSelectedUser] = useState(isAdmin ? null : currentUser.email);

  // salary calc state
  const [monthlySalary,    setMonthlySalary]    = useState('');
  const [paidLeavesAllowed, setPaidLeavesAllowed] = useState(1);

  // users for admin dropdown
  const { data: usersData } = useQuery({
    queryKey: ['users-all'],
    queryFn:  () => usersAPI.getAll().then(r => r.data?.users || r.data || []),
    enabled:  isAdmin,
  });

  const monthStr = month.format('YYYY-MM');

  const { data: reportData, isLoading } = useQuery({
    queryKey: ['attendance-report', monthStr, selectedUser],
    queryFn:  () => attendanceAPI.report(monthStr, selectedUser || undefined).then(r => r.data),
  });

  // Build full daily list (one row per calendar day)
  const dailyList = useMemo(() => {
    const records = reportData?.records || [];
    const daysInMonth = month.daysInMonth();
    const today = dayjs();

    // For single-user view, index by date
    const byDate = {};
    records.forEach(r => { byDate[r.date] = r; });

    const rows = [];
    for (let d = 1; d <= daysInMonth; d++) {
      const dt      = month.date(d);
      const dateStr = dt.format('YYYY-MM-DD');
      const isSun   = dt.day() === 0;
      const isFuture = dt.isAfter(today, 'day');
      const rec     = byDate[dateStr];

      rows.push({
        key:          dateStr,
        date:         dateStr,
        dayName:      dt.format('ddd'),
        isSunday:     isSun,
        isFuture,
        status:       isSun ? 'week_off' : isFuture ? null : (rec?.status || 'absent'),
        check_in_at:  rec?.check_in_at  || null,
        check_out_at: rec?.check_out_at || null,
      });
    }
    return rows;
  }, [reportData, month]);

  // Summary counts
  const summary = useMemo(() => {
    const working         = dailyList.filter(r => !r.isSunday && !r.isFuture).length;
    const present         = dailyList.filter(r => r.status === 'present').length;
    const late            = dailyList.filter(r => r.status === 'late').length;
    const leftEarly       = dailyList.filter(r => r.status === 'left_early').length;
    const lateLeftEarly   = dailyList.filter(r => r.status === 'late_and_left_early').length;
    const absent          = dailyList.filter(r => r.status === 'absent').length;
    const attended        = present + late + leftEarly + lateLeftEarly;
    return { working, present, late, leftEarly, lateLeftEarly, absent, attended };
  }, [dailyList]);

  // Salary calculation
  const salaryCalc = useMemo(() => {
    const sal = parseFloat(monthlySalary);
    if (!sal || summary.working === 0) return null;
    const perDay        = sal / summary.working;
    const effectiveAbsent = Math.max(0, summary.absent - paidLeavesAllowed);
    const deduction     = effectiveAbsent * perDay;
    const netSalary     = sal - deduction;
    return { perDay, effectiveAbsent, deduction, netSalary };
  }, [monthlySalary, paidLeavesAllowed, summary]);

  // Client-side CSV download
  const handleDownloadCSV = async () => {
    if (!selectedUser && isAdmin) {
      // use backend CSV (all users or filtered)
    }
    try {
      const res = await attendanceAPI.exportCsv(monthStr, selectedUser || undefined);
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
      const a   = document.createElement('a');
      a.href     = url;
      a.download = `attendance_${monthStr}${selectedUser ? '_' + selectedUser.split('@')[0] : ''}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('CSV export failed', e);
    }
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
        if (r.isFuture)  return <Text type="secondary">—</Text>;
        if (!s)          return <Text type="secondary">—</Text>;
        return <Tag color={STATUS_TAG[s]?.color || 'default'}>{STATUS_TAG[s]?.label || s}</Tag>;
      },
    },
    {
      title: 'Check In', dataIndex: 'check_in_at', key: 'check_in_at', width: 110,
      render: fmtTime,
    },
    {
      title: 'Check Out', dataIndex: 'check_out_at', key: 'check_out_at', width: 110,
      render: fmtTime,
    },
    {
      title: 'Hours', key: 'hours', width: 90,
      render: (_, r) => hoursWorked(r.check_in_at, r.check_out_at),
    },
  ];

  return (
    <div>
      {/* ── Filters ── */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <div>
            <div style={{ fontSize: 11, color: '#8c8c8c', marginBottom: 4 }}>Month</div>
            <DatePicker
              picker="month"
              value={month}
              onChange={(d) => d && setMonth(d)}
              disabledDate={(d) => d && d > dayjs().endOf('month')}
              allowClear={false}
            />
          </div>

          {isAdmin && (
            <div>
              <div style={{ fontSize: 11, color: '#8c8c8c', marginBottom: 4 }}>Employee</div>
              <Select
                style={{ width: 220 }}
                placeholder="All employees"
                allowClear
                value={selectedUser}
                onChange={setSelectedUser}
                showSearch
                optionFilterProp="label"
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
            <Button icon={<DownloadOutlined />} onClick={handleDownloadCSV}>
              Download Report
            </Button>
          </div>
        </Space>
      </Card>

      {/* ── Summary stats ── */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        {[
          { label: 'Working Days',  value: summary.working,   color: '#1890ff' },
          { label: 'Present',       value: summary.present,   color: '#52c41a' },
          { label: 'Late',          value: summary.late,      color: '#fa8c16' },
          { label: 'Left Early',    value: summary.leftEarly + summary.lateLeftEarly, color: '#fadb14' },
          { label: 'Absent',        value: summary.absent,    color: '#ff4d4f' },
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

      {/* ── Daily table ── */}
      <Card title={<Space><CalendarOutlined />{month.format('MMMM YYYY')} — Daily Report</Space>}
        style={{ marginBottom: 16 }}>
        {isLoading
          ? <Spin />
          : dailyList.length === 0
            ? <Empty description="No data" />
            : (
              <Table
                columns={tableColumns}
                dataSource={dailyList}
                rowKey="key"
                size="small"
                pagination={false}
                rowClassName={(r) => r.isSunday ? 'ant-table-row-sunday' : ''}
                scroll={{ y: 420 }}
              />
            )
        }
      </Card>

      {/* ── Salary Calculator ── */}
      {(isAdmin || selectedUser === currentUser.email) && (
        <Card
          title={<Space><DollarOutlined />Salary Calculator</Space>}
          style={{ marginBottom: 16 }}
        >
          <Row gutter={24}>
            <Col xs={24} sm={8}>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 6 }}>Monthly Gross Salary (₹)</div>
                <InputNumber
                  style={{ width: '100%' }}
                  placeholder="e.g. 25000"
                  min={0}
                  value={monthlySalary}
                  onChange={setMonthlySalary}
                  formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={v => v.replace(/,/g, '')}
                  size="large"
                />
              </div>
            </Col>
            <Col xs={24} sm={8}>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 6 }}>Paid Leave Allowance (days)</div>
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  max={summary.working}
                  value={paidLeavesAllowed}
                  onChange={(v) => setPaidLeavesAllowed(v ?? 0)}
                  size="large"
                />
              </div>
            </Col>
          </Row>

          {salaryCalc ? (
            <>
              <Divider style={{ margin: '8px 0 16px' }} />
              <Row gutter={16}>
                <Col xs={12} sm={6}>
                  <Card size="small" bodyStyle={{ padding: '12px 16px', background: '#f6ffed', borderColor: '#b7eb8f' }}>
                    <div style={{ fontSize: 11, color: '#8c8c8c' }}>Working Days</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#52c41a' }}>{summary.working}</div>
                  </Card>
                </Col>
                <Col xs={12} sm={6}>
                  <Card size="small" bodyStyle={{ padding: '12px 16px', background: '#e6f7ff', borderColor: '#91d5ff' }}>
                    <div style={{ fontSize: 11, color: '#8c8c8c' }}>Days Attended</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#1890ff' }}>{summary.attended}</div>
                  </Card>
                </Col>
                <Col xs={12} sm={6}>
                  <Card size="small" bodyStyle={{ padding: '12px 16px', background: '#fff2e8', borderColor: '#ffbb96' }}>
                    <div style={{ fontSize: 11, color: '#8c8c8c' }}>Absent (after {paidLeavesAllowed} paid leave{paidLeavesAllowed !== 1 ? 's' : ''})</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#fa541c' }}>{salaryCalc.effectiveAbsent}</div>
                  </Card>
                </Col>
                <Col xs={12} sm={6}>
                  <Card size="small" bodyStyle={{ padding: '12px 16px', background: '#f9f0ff', borderColor: '#d3adf7' }}>
                    <div style={{ fontSize: 11, color: '#8c8c8c' }}>Per Day Rate</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#722ed1' }}>{fmtINR(salaryCalc.perDay)}</div>
                  </Card>
                </Col>
              </Row>

              <Row gutter={16} style={{ marginTop: 12 }}>
                <Col xs={24} sm={12}>
                  <Card size="small" bodyStyle={{ padding: '16px', background: '#fff1f0', borderColor: '#ffa39e' }}>
                    <div style={{ fontSize: 12, color: '#8c8c8c' }}>Salary Deduction</div>
                    <div style={{ fontSize: 26, fontWeight: 700, color: '#cf1322' }}>
                      - {fmtINR(salaryCalc.deduction)}
                    </div>
                    <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 4 }}>
                      {salaryCalc.effectiveAbsent} days × {fmtINR(salaryCalc.perDay)}/day
                    </div>
                  </Card>
                </Col>
                <Col xs={24} sm={12}>
                  <Card size="small" bodyStyle={{ padding: '16px', background: '#f6ffed', borderColor: '#b7eb8f' }}>
                    <div style={{ fontSize: 12, color: '#8c8c8c' }}>Net Salary Payable</div>
                    <div style={{ fontSize: 26, fontWeight: 700, color: '#389e0d' }}>
                      {fmtINR(salaryCalc.netSalary)}
                    </div>
                    <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 4 }}>
                      {fmtINR(parseFloat(monthlySalary))} − {fmtINR(salaryCalc.deduction)} deduction
                    </div>
                  </Card>
                </Col>
              </Row>
            </>
          ) : (
            <Text type="secondary">Enter the monthly salary above to calculate net pay.</Text>
          )}
        </Card>
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function AttendancePage() {
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const isAdmin     = ['Super Admin', 'Manager', 'Team Leader'].includes(currentUser.role);

  const items = [
    { key: 'self',   label: <Space><ClockCircleOutlined />My Attendance</Space>, children: <SelfAttendance /> },
  ];
  if (isAdmin) {
    items.push({ key: 'team',   label: <Space><TeamOutlined />Team Attendance</Space>,  children: <TeamAttendance /> });
  }
  items.push({
    key: 'reports',
    label: <Space><FileTextOutlined />Reports</Space>,
    children: <AttendanceReport />,
  });

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <EnvironmentOutlined style={{ marginRight: 8 }} />
          Attendance
        </Title>
        <Text type="secondary">Check in/out at the office and view reports.</Text>
      </div>
      <Tabs items={items} />
    </div>
  );
}
