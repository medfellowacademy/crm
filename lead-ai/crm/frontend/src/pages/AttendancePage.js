import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card, Button, Tag, Table, Typography, Space, Alert, Spin, Tabs, DatePicker, Empty,
} from 'antd';
import {
  LoginOutlined, LogoutOutlined, EnvironmentOutlined, ClockCircleOutlined,
  CheckCircleOutlined, WarningOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { attendanceAPI } from '../api/api';

const { Title, Text } = Typography;

const STATUS_TAG = {
  present: { color: 'green', label: 'Present' },
  late: { color: 'orange', label: 'Late' },
  left_early: { color: 'gold', label: 'Left Early' },
  late_and_left_early: { color: 'red', label: 'Late & Left Early' },
  absent: { color: 'default', label: 'Absent' },
};

const fmtTime = (iso) => iso ? dayjs(iso).format('hh:mm A') : '—';

// Wraps the browser Geolocation API in a promise. Requires HTTPS (or
// localhost) and the user granting location permission - this is what
// actually enforces "must be at the office", not anything server-side.
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

  const record = data?.record;
  const hasCheckedIn = !!record?.check_in_at;
  const hasCheckedOut = !!record?.check_out_at;

  const historyColumns = [
    { title: 'Date', dataIndex: 'date', key: 'date', render: (d) => dayjs(d).format('DD MMM YYYY') },
    { title: 'Check In', dataIndex: 'check_in_at', key: 'check_in_at', render: fmtTime },
    { title: 'Check Out', dataIndex: 'check_out_at', key: 'check_out_at', render: fmtTime },
    {
      title: 'Status', dataIndex: 'status', key: 'status',
      render: (s) => <Tag color={STATUS_TAG[s]?.color || 'default'}>{STATUS_TAG[s]?.label || s}</Tag>,
    },
  ];

  return (
    <div>
      <Card style={{ marginBottom: 24 }}>
        {isLoading ? (
          <Spin />
        ) : (
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
              <Button
                type="primary"
                size="large"
                icon={<LoginOutlined />}
                loading={checkInMutation.isPending}
                disabled={hasCheckedIn}
                onClick={() => checkInMutation.mutate()}
              >
                {hasCheckedIn ? 'Checked In' : 'Check In'}
              </Button>
              <Button
                size="large"
                icon={<LogoutOutlined />}
                loading={checkOutMutation.isPending}
                disabled={!hasCheckedIn || hasCheckedOut}
                onClick={() => checkOutMutation.mutate()}
              >
                {hasCheckedOut ? 'Checked Out' : 'Check Out'}
              </Button>
            </Space>
          </>
        )}
      </Card>

      <Card title="Attendance History (Last 30 Days)">
        {history.length === 0 ? (
          <Empty description="No attendance records yet" />
        ) : (
          <Table columns={historyColumns} dataSource={history} rowKey="id" pagination={{ pageSize: 10 }} size="small" />
        )}
      </Card>
    </div>
  );
}

function TeamAttendance() {
  const [date, setDate] = useState(dayjs());

  const { data, isLoading } = useQuery({
    queryKey: ['attendance-team', date.format('YYYY-MM-DD')],
    queryFn: () => attendanceAPI.team(date.format('YYYY-MM-DD')).then(res => res.data),
  });

  const columns = [
    { title: 'Name', dataIndex: 'user_name', key: 'user_name' },
    { title: 'Role', dataIndex: 'role', key: 'role' },
    { title: 'Check In', dataIndex: 'check_in_at', key: 'check_in_at', render: fmtTime },
    { title: 'Check Out', dataIndex: 'check_out_at', key: 'check_out_at', render: fmtTime },
    {
      title: 'Status', dataIndex: 'status', key: 'status',
      render: (s) => <Tag color={STATUS_TAG[s]?.color || 'default'} icon={s === 'absent' ? <WarningOutlined /> : <CheckCircleOutlined />}>
        {STATUS_TAG[s]?.label || s}
      </Tag>,
    },
  ];

  return (
    <Card
      title="Team Attendance"
      extra={<DatePicker value={date} onChange={(d) => d && setDate(d)} disabledDate={(d) => d && d > dayjs().endOf('day')} />}
    >
      {isLoading ? (
        <Spin />
      ) : (
        <Table columns={columns} dataSource={data?.rows || []} rowKey="user_email" pagination={false} size="small" />
      )}
    </Card>
  );
}

export default function AttendancePage() {
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const isAdmin = ['Super Admin', 'Manager', 'Team Leader'].includes(currentUser.role);

  const items = [
    { key: 'self', label: 'My Attendance', children: <SelfAttendance /> },
  ];
  if (isAdmin) {
    items.push({ key: 'team', label: 'Team Attendance', children: <TeamAttendance /> });
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <EnvironmentOutlined style={{ marginRight: 8 }} />
          Attendance
        </Title>
        <Text type="secondary">Check in and out when you're physically at the office.</Text>
      </div>
      <Tabs items={items} />
    </div>
  );
}
