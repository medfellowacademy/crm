import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, Table, Tag, Button, Space, Typography, Alert, Popconfirm, message } from 'antd';
import { PlusOutlined, BookOutlined, LinkOutlined } from '@ant-design/icons';
import { enrollmentsAPI, coursesAPI, usersAPI } from '../../api/api';
import { fmtBoth } from '../../utils/finance';
import EnrollmentModal from './EnrollmentModal';

const { Text } = Typography;
const errorText = (e, fallback) => (typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : fallback);

/** Every course this doctor has taken, each with its own fee and payments, and a button to add another. */
export default function CoursesCard({ lead }) {
  const leadId = lead?.lead_id;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);

  const { data } = useQuery({
    queryKey: ['enrollments', leadId],
    queryFn: () => enrollmentsAPI.list(leadId).then((r) => r.data),
    enabled: !!leadId,
    retry: 1,
  });
  const courses = useQuery({ queryKey: ['courses'], queryFn: () => coursesAPI.getAll().then((r) => (Array.isArray(r.data) ? r.data : [])), enabled: adding, staleTime: 10 * 60 * 1000 });
  const users = useQuery({ queryKey: ['users-for-courses'], queryFn: () => usersAPI.getAll().then((r) => (Array.isArray(r.data) ? r.data : [])), enabled: adding, staleTime: 10 * 60 * 1000 });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['enrollments'] });
    qc.invalidateQueries({ queryKey: ['leads'] });
    qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith('payments') });
  };
  const add = useMutation({
    mutationFn: (payload) => enrollmentsAPI.add(leadId, payload).then((r) => r.data),
    onSuccess: (d) => { setAdding(false); refresh(); message.success(`${d.course} added. Its payments are tracked separately.`); },
    onError: (e) => message.error(errorText(e, 'Could not add the course')),
  });
  const link = useMutation({
    mutationFn: (other) => enrollmentsAPI.link(leadId, other),
    onSuccess: () => { refresh(); message.success('Records linked as the same doctor'); },
    onError: (e) => message.error(errorText(e, 'Could not link the records')),
  });
  const unlink = useMutation({
    mutationFn: (id) => enrollmentsAPI.unlink(id),
    onSuccess: () => { refresh(); message.success('Record unlinked'); },
    onError: (e) => message.error(errorText(e, 'Could not unlink')),
  });

  if (!data) return null;
  const items = data.items || [];
  const matches = data.matches || [];
  const relevant = lead?.status === 'Enrolled' || items.length > 1;
  if (!relevant && !matches.length) return null;
  if (data.supported === false) {
    return relevant ? <Alert type="info" showIcon style={{ marginBottom: 16 }} message={data.message} /> : null;
  }
  const t = data.totals || {};
  const options = (courses.data || []).map((c) => c.course_name || c.name).filter(Boolean);

  // Rupees on the first line, dollars small underneath, so the table fits beside the lead page's side menu.
  const money = (v, color) => {
    if (v === undefined) return '—';
    const [rupees, dollars] = String(fmtBoth(v)).split(' (');
    return (
      <div style={{ whiteSpace: 'nowrap' }}>
        <div style={{ color }}>{rupees}</div>
        {dollars && <Text type="secondary" style={{ fontSize: 11 }}>{dollars.replace(')', '')}</Text>}
      </div>
    );
  };
  const columns = [
    { title: 'Course', dataIndex: 'course', render: (v, r) => (
      <div style={{ minWidth: 180 }}>
        <Space size={6} wrap>
          <Text strong>{v || 'Course not set'}</Text>
          {r.is_current && <Tag color="blue" style={{ margin: 0 }}>This record</Tag>}
          {r.is_primary && items.length > 1 && <Tag style={{ margin: 0 }}>First</Tag>}
        </Space>
        <div style={{ marginTop: 2 }}>
          <Tag color={r.status === 'Enrolled' ? 'green' : 'default'}>{r.status}</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.assigned_to}</Text>
        </div>
      </div>) },
    { title: 'Fee', dataIndex: 'total', align: 'right', render: (v) => money(v) },
    { title: 'Received', dataIndex: 'collected', align: 'right', render: (v) => money(v, '#389e0d') },
    { title: 'Balance', dataIndex: 'balance', align: 'right', render: (v, r) => (
      <div>{money(v)}{r.overdue > 0 && <Tag color="red" style={{ margin: 0 }}>overdue</Tag>}</div>) },
    { title: '', key: 'actions', align: 'right', render: (_, r) => (
      <Space direction="vertical" size={2}>
        {!r.is_current && r.visible && <Button size="small" onClick={() => navigate(`/leads/${r.lead_id}`)}>Open</Button>}
        {!r.is_primary && (
          <Popconfirm title="Unlink this record from the doctor?" description="Nothing is deleted." onConfirm={() => unlink.mutate(r.lead_id)}>
            <Button size="small" type="text">Unlink</Button>
          </Popconfirm>)}
      </Space>) },
  ];

  return (
    <Card style={{ marginBottom: 16 }} size="small"
      title={<span><BookOutlined /> Courses taken{items.length > 1 ? ` (${items.length})` : ''}</span>}
      extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>Add another course</Button>}>
      {matches.map((m) => (
        <Alert key={m.lead_id} type="warning" showIcon style={{ marginBottom: 8 }}
          message={`Another record has the same phone or email: ${m.name} · ${m.course || 'no course'} (${m.status})`}
          action={(
            <Space>
              <Button size="small" onClick={() => navigate(`/leads/${m.lead_id}`)}>Open</Button>
              <Popconfirm title="Link as the same doctor?" description="Both courses then show together." onConfirm={() => link.mutate(m.lead_id)}>
                <Button size="small" type="primary" icon={<LinkOutlined />} loading={link.isPending}>Link</Button>
              </Popconfirm>
            </Space>)} />
      ))}
      <Table size="small" rowKey="lead_id" dataSource={items} columns={columns} pagination={false} scroll={{ x: 'max-content' }} />
      {t.courses > 1 && (
        <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
          All {t.courses} courses: fee {fmtBoth(t.total)} · received {fmtBoth(t.collected)} · balance {fmtBoth(t.balance)}
          {t.overdue > 0 ? ` · overdue ${fmtBoth(t.overdue)}` : ''}
        </Text>
      )}
      <EnrollmentModal
        open={adding}
        lead={{ full_name: lead?.full_name, assigned_to: lead?.assigned_to }}
        courseOptions={options}
        counselorOptions={(users.data || []).filter((u) => u.is_active !== false).map((u) => u.full_name).filter(Boolean)}
        loading={add.isPending}
        onCancel={() => setAdding(false)}
        onSave={({ status, ...payload }) => add.mutate(payload)}
      />
    </Card>
  );
}
