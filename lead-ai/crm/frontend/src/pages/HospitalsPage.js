import React, { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Row, Col, Card, Button, Tag, Space, Form, Input, Select, Drawer, Modal, message,
  Popconfirm, Divider, Typography, Empty, Badge, Tabs, Table, Progress, DatePicker,
  InputNumber, Statistic, Spin,
} from 'antd';
import {
  PlusOutlined, MedicineBoxOutlined, EditOutlined, DeleteOutlined,
  MinusCircleOutlined, EnvironmentOutlined, GlobalOutlined, TeamOutlined,
  UsergroupAddOutlined, SearchOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { hospitalsAPI, leadsAPI } from '../api/api';

const { Option } = Select;
const { Text, Link, Paragraph } = Typography;

// Mirrors the fellowship categories in backend/courses_data.py.
const DEPARTMENT_SUGGESTIONS = [
  'Cardiology', 'Critical Care & Emergency', 'Dermatology & Aesthetics',
  'Diabetes & Endocrinology', 'Gastroenterology', 'Nephrology & Urology',
  'Neurology', 'Obstetrics & Gynecology', 'Oncology', 'Paediatrics',
  'Pain & Anaesthesia', 'Radiology & Imaging', 'Reproductive Medicine & IVF',
  'Surgery', 'Other Specialties',
];
const COUNTRIES = ['India', 'UAE', 'Saudi Arabia', 'Kuwait', 'Qatar', 'Oman', 'Bahrain', 'UK', 'USA'];
const STUDENT_STATUS = ['Ongoing', 'Completed', 'On Hold', 'Dropped'];
const EMPTY_LOCATION = { label: '', address: '', city: '', state: '', departments: [], is_primary: false };

const statusColor = (s) => (s === 'Active' || s === 'Completed' ? 'green'
  : s === 'Pending' || s === 'On Hold' ? 'gold'
    : s === 'Ongoing' ? 'blue' : 'red');

const mergedDepartments = (locations = []) => {
  const set = new Set();
  locations.forEach((l) => (l.departments || []).forEach((d) => d && set.add(d)));
  return [...set].sort();
};

/* ------------------------------------------------------------------ */
/*  Add / edit a clinical-practice student                            */
/* ------------------------------------------------------------------ */
function StudentModal({ open, onClose, hospital, student, onSaved }) {
  const [form] = Form.useForm();
  const isEdit = !!student;

  React.useEffect(() => {
    if (!open) return;
    form.resetFields();
    if (student) {
      form.setFieldsValue({
        ...student,
        start_date: student.start_date ? dayjs(student.start_date) : null,
        end_date: student.end_date ? dayjs(student.end_date) : null,
        sessions: (student.sessions || []).map((s) => ({ ...s, date: s.date ? dayjs(s.date) : null })),
      });
    } else {
      form.setFieldsValue({ status: 'Ongoing', required_hours: 0, sessions: [] });
    }
  }, [open, student, form]);

  const save = useMutation({
    mutationFn: (payload) => (isEdit
      ? hospitalsAPI.updateStudent(hospital.id, student.id, payload)
      : hospitalsAPI.addStudent(hospital.id, payload)),
    onSuccess: () => { message.success(isEdit ? 'Student updated' : 'Student added'); onSaved(); onClose(); },
    onError: () => message.error('Save failed'),
  });

  const submit = (v) => {
    const sessions = (v.sessions || [])
      .filter((s) => s && (s.hours || s.date || s.note))
      .map((s) => ({ date: s.date ? s.date.format('YYYY-MM-DD') : null, hours: Number(s.hours) || 0, note: s.note || null }));
    save.mutate({
      ...v,
      start_date: v.start_date ? v.start_date.format('YYYY-MM-DD') : null,
      end_date: v.end_date ? v.end_date.format('YYYY-MM-DD') : null,
      required_hours: Number(v.required_hours) || 0,
      sessions,
    });
  };

  const branchOptions = (hospital?.locations || []).map((l) => l.label).filter(Boolean);

  return (
    <Modal
      title={isEdit ? 'Edit training record' : 'Add student — clinical practice'}
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={save.isPending}
      width={640}
      okText={isEdit ? 'Save' : 'Add student'}
      destroyOnClose
    >
      <Form form={form} layout="vertical" onFinish={submit}>
        <Space size="middle" style={{ display: 'flex' }} align="start">
          <Form.Item name="full_name" label="Full name" rules={[{ required: true }]} style={{ flex: 2 }}>
            <Input placeholder="Dr. Asha Rao" />
          </Form.Item>
          <Form.Item name="status" label="Status" style={{ flex: 1 }}>
            <Select>{STUDENT_STATUS.map((s) => <Option key={s} value={s}>{s}</Option>)}</Select>
          </Form.Item>
        </Space>
        <Space size="middle" style={{ display: 'flex' }} align="start">
          <Form.Item name="phone" label="Phone" style={{ flex: 1 }}><Input /></Form.Item>
          <Form.Item name="email" label="Email" style={{ flex: 1 }}><Input /></Form.Item>
        </Space>
        <Space size="middle" style={{ display: 'flex' }} align="start">
          <Form.Item name="department" label="Department" style={{ flex: 1 }}>
            <Select allowClear showSearch placeholder="Cardiology…"
              options={DEPARTMENT_SUGGESTIONS.map((d) => ({ value: d, label: d }))} />
          </Form.Item>
          <Form.Item name="branch_label" label="Branch" style={{ flex: 1 }}>
            <Select allowClear placeholder="Which location">
              {branchOptions.map((b) => <Option key={b} value={b}>{b}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="supervisor" label="Supervisor" style={{ flex: 1 }}><Input /></Form.Item>
        </Space>
        <Space size="middle" style={{ display: 'flex' }} align="start">
          <Form.Item name="start_date" label="Start date" style={{ flex: 1 }}><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="end_date" label="Planned end" style={{ flex: 1 }}><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="required_hours" label="Required hours" style={{ flex: 1 }}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Space>

        <Divider orientation="left"><ClockCircleOutlined /> Training log</Divider>
        <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
          Log each session — completed hours are totalled automatically.
        </Text>
        <Form.List name="sessions">
          {(fields, { add, remove }) => (
            <>
              {fields.map(({ key, name, ...rest }) => (
                <Space key={key} align="baseline" style={{ display: 'flex', marginBottom: 4 }}>
                  <Form.Item {...rest} name={[name, 'date']} style={{ marginBottom: 0 }}>
                    <DatePicker placeholder="Date" />
                  </Form.Item>
                  <Form.Item {...rest} name={[name, 'hours']} style={{ marginBottom: 0 }}>
                    <InputNumber min={0} placeholder="Hrs" style={{ width: 80 }} />
                  </Form.Item>
                  <Form.Item {...rest} name={[name, 'note']} style={{ marginBottom: 0, flex: 1 }}>
                    <Input placeholder="Note (procedure, ward…)" style={{ width: 260 }} />
                  </Form.Item>
                  <MinusCircleOutlined onClick={() => remove(name)} />
                </Space>
              ))}
              <Button type="dashed" size="small" onClick={() => add()} icon={<PlusOutlined />}>Add session</Button>
            </>
          )}
        </Form.List>

        <Form.Item name="notes" label="Notes" style={{ marginTop: 16 }}>
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/*  Hospital detail — locations / students / leads                    */
/* ------------------------------------------------------------------ */
function HospitalDetail({ hospital, onClose }) {
  const qc = useQueryClient();
  const hid = hospital?.id;
  const [studentModal, setStudentModal] = useState({ open: false, student: null });
  const [leadSearch, setLeadSearch] = useState('');
  const [leadToAdd, setLeadToAdd] = useState(null);

  const students = useQuery({
    queryKey: ['hospital-students', hid],
    queryFn: () => hospitalsAPI.getStudents(hid).then((r) => r.data),
    enabled: !!hid,
  });
  const links = useQuery({
    queryKey: ['hospital-leads', hid],
    queryFn: () => hospitalsAPI.getLeads(hid).then((r) => r.data),
    enabled: !!hid,
  });
  const leadOptions = useQuery({
    queryKey: ['lead-search', leadSearch],
    queryFn: () => leadsAPI.getAll({ search: leadSearch, limit: 20 }).then((r) => r.data?.leads || r.data || []),
    enabled: leadSearch.length >= 2,
  });

  const refetchAll = () => {
    qc.invalidateQueries({ queryKey: ['hospital-students', hid] });
    qc.invalidateQueries({ queryKey: ['hospital-leads', hid] });
    qc.invalidateQueries({ queryKey: ['hospitals'] });
  };

  const delStudent = useMutation({
    mutationFn: (sid) => hospitalsAPI.deleteStudent(hid, sid),
    onSuccess: () => { message.success('Removed'); refetchAll(); },
  });
  const linkLead = useMutation({
    mutationFn: (leadId) => hospitalsAPI.linkLead(hid, { lead_id: leadId }),
    onSuccess: () => { message.success('Lead linked'); setLeadToAdd(null); setLeadSearch(''); refetchAll(); },
    onError: (e) => message.error(e?.response?.data?.detail || 'Failed to link'),
  });
  const unlinkLead = useMutation({
    mutationFn: (leadId) => hospitalsAPI.unlinkLead(hid, leadId),
    onSuccess: () => { message.success('Unlinked'); refetchAll(); },
  });

  const locations = hospital?.locations || [];

  const studentCols = [
    { title: 'Name', dataIndex: 'full_name', render: (v, r) => <><strong>{v}</strong>{r.branch_label ? <div><Text type="secondary" style={{ fontSize: 12 }}>{r.branch_label}</Text></div> : null}</> },
    { title: 'Department', dataIndex: 'department', render: (v) => v || '—' },
    { title: 'Supervisor', dataIndex: 'supervisor', render: (v) => v || '—' },
    {
      title: 'Period',
      render: (_, r) => (r.start_date || r.end_date
        ? `${r.start_date || '?'} → ${r.end_date || '?'}` : '—'),
    },
    {
      title: 'Training time',
      render: (_, r) => {
        const req = Number(r.required_hours) || 0;
        const done = Number(r.completed_hours) || 0;
        const pct = req ? Math.min(100, Math.round((done / req) * 100)) : 0;
        return (
          <div style={{ minWidth: 140 }}>
            <Text style={{ fontSize: 12 }}>{done} / {req || '—'} hrs</Text>
            {req > 0 && <Progress percent={pct} size="small" status={pct >= 100 ? 'success' : 'active'} />}
          </div>
        );
      },
    },
    { title: 'Status', dataIndex: 'status', render: (s) => <Tag color={statusColor(s)}>{s}</Tag> },
    {
      title: '',
      width: 90,
      render: (_, r) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => setStudentModal({ open: true, student: r })} />
          <Popconfirm title="Remove this record?" onConfirm={() => delStudent.mutate(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const leadCols = [
    { title: 'Lead', render: (_, r) => <><strong>{r.lead?.full_name || r.lead_id}</strong><div><Text type="secondary" style={{ fontSize: 12 }}>{r.lead?.phone}</Text></div></> },
    { title: 'Course', render: (_, r) => r.lead?.course_interested || '—' },
    { title: 'Status', render: (_, r) => (r.lead?.status ? <Tag>{r.lead.status}</Tag> : '—') },
    { title: 'Owner', render: (_, r) => r.lead?.assigned_to || '—' },
    { title: 'Note', dataIndex: 'note', render: (v) => v || '—' },
    {
      title: '',
      width: 50,
      render: (_, r) => (
        <Popconfirm title="Unlink this lead?" onConfirm={() => unlinkLead.mutate(r.lead_id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Drawer
      title={<Space><MedicineBoxOutlined />{hospital?.name}</Space>}
      width={880}
      open={!!hospital}
      onClose={onClose}
      destroyOnClose
    >
      <Space wrap style={{ marginBottom: 16 }}>
        {hospital?.country && <Tag color="blue">{hospital.country}</Tag>}
        <Tag color={statusColor(hospital?.collaboration_status)}>{hospital?.collaboration_status || 'Active'}</Tag>
        {hospital?.website && (
          <Link href={hospital.website} target="_blank" rel="noopener noreferrer">
            <GlobalOutlined /> {hospital.website.replace(/^https?:\/\//, '')}
          </Link>
        )}
      </Space>

      <Tabs
        defaultActiveKey="locations"
        items={[
          {
            key: 'locations',
            label: <span><EnvironmentOutlined /> Locations ({locations.length})</span>,
            children: locations.length ? (
              <Table
                size="small"
                pagination={false}
                rowKey={(_, i) => i}
                dataSource={locations}
                columns={[
                  { title: 'Branch', dataIndex: 'label', render: (v, l) => <Space>{v || '—'}{l.is_primary && <Tag color="blue">Primary</Tag>}</Space> },
                  { title: 'Address', dataIndex: 'address', render: (v) => v || '—' },
                  { title: 'City', dataIndex: 'city', render: (v) => v || '—' },
                  { title: 'State', dataIndex: 'state', render: (v) => v || '—' },
                  { title: 'Departments', dataIndex: 'departments', render: (d = []) => (d.length ? <Space size={4} wrap>{d.map((x) => <Tag key={x}>{x}</Tag>)}</Space> : '—') },
                ]}
              />
            ) : <Empty description="No locations" />,
          },
          {
            key: 'students',
            label: <span><TeamOutlined /> Clinical practice ({students.data?.length || 0})</span>,
            children: (
              <>
                <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }}
                  onClick={() => setStudentModal({ open: true, student: null })}>
                  Add student
                </Button>
                <Table
                  size="small"
                  rowKey="id"
                  loading={students.isLoading}
                  dataSource={students.data || []}
                  columns={studentCols}
                  pagination={{ pageSize: 8 }}
                  expandable={{
                    rowExpandable: (r) => (r.sessions || []).length > 0 || r.notes,
                    expandedRowRender: (r) => (
                      <div>
                        {r.notes && <Paragraph type="secondary" style={{ marginBottom: 8 }}>{r.notes}</Paragraph>}
                        {(r.sessions || []).length > 0 && (
                          <Table
                            size="small" pagination={false} rowKey={(_, i) => i}
                            dataSource={r.sessions}
                            columns={[
                              { title: 'Date', dataIndex: 'date' },
                              { title: 'Hours', dataIndex: 'hours' },
                              { title: 'Note', dataIndex: 'note', render: (v) => v || '—' },
                            ]}
                          />
                        )}
                      </div>
                    ),
                  }}
                />
              </>
            ),
          },
          {
            key: 'leads',
            label: <span><UsergroupAddOutlined /> Leads ({links.data?.length || 0})</span>,
            children: (
              <>
                <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
                  <Select
                    showSearch
                    value={leadToAdd}
                    placeholder="Search a lead by name or phone…"
                    style={{ flex: 1 }}
                    filterOption={false}
                    onSearch={setLeadSearch}
                    onChange={setLeadToAdd}
                    notFoundContent={leadOptions.isFetching ? <Spin size="small" /> : (leadSearch.length < 2 ? 'Type 2+ characters' : 'No matches')}
                    options={(leadOptions.data || []).map((l) => ({
                      value: l.lead_id,
                      label: `${l.full_name || 'Unknown'} · ${l.phone || ''} · ${l.status || ''}`,
                    }))}
                  />
                  <Button type="primary" disabled={!leadToAdd} loading={linkLead.isPending}
                    onClick={() => linkLead.mutate(leadToAdd)}>
                    Link lead
                  </Button>
                </Space.Compact>
                <Table
                  size="small" rowKey="id"
                  loading={links.isLoading}
                  dataSource={links.data || []}
                  columns={leadCols}
                  pagination={{ pageSize: 8 }}
                />
              </>
            ),
          },
        ]}
      />

      <StudentModal
        open={studentModal.open}
        student={studentModal.student}
        hospital={hospital}
        onClose={() => setStudentModal({ open: false, student: null })}
        onSaved={refetchAll}
      />
    </Drawer>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                              */
/* ------------------------------------------------------------------ */
const HospitalsPage = () => {
  const queryClient = useQueryClient();
  const [formDrawer, setFormDrawer] = useState(false);
  const [editing, setEditing] = useState(null);
  const [selected, setSelected] = useState(null);
  const [form] = Form.useForm();

  const [q, setQ] = useState('');
  const [fCountry, setFCountry] = useState();
  const [fStatus, setFStatus] = useState();

  const { data: hospitals, isLoading } = useQuery({
    queryKey: ['hospitals'],
    queryFn: () => hospitalsAPI.getAll().then((res) => res.data),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['hospitals'] });

  const createMut = useMutation({
    mutationFn: (data) => hospitalsAPI.create(data),
    onSuccess: () => { message.success('Hospital added'); closeForm(); invalidate(); },
    onError: () => message.error('Failed to add hospital'),
  });
  const updateMut = useMutation({
    mutationFn: ({ id, data }) => hospitalsAPI.update(id, data),
    onSuccess: () => { message.success('Hospital updated'); closeForm(); invalidate(); },
    onError: () => message.error('Failed to update hospital'),
  });
  const deleteMut = useMutation({
    mutationFn: (id) => hospitalsAPI.delete(id),
    onSuccess: () => { message.success('Hospital deleted'); setSelected(null); invalidate(); },
    onError: () => message.error('Failed to delete hospital'),
  });

  const closeForm = () => { setFormDrawer(false); setEditing(null); form.resetFields(); };

  const openAdd = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      collaboration_status: 'Active', country: 'India',
      locations: [{ ...EMPTY_LOCATION, label: 'Main', is_primary: true }],
    });
    setFormDrawer(true);
  };
  const openEdit = (h) => {
    setEditing(h);
    form.resetFields();
    form.setFieldsValue({
      ...h,
      locations: (h.locations?.length ? h.locations
        : [{ ...EMPTY_LOCATION, label: 'Main', city: h.city, is_primary: true }]
      ).map((l) => ({ ...EMPTY_LOCATION, ...l })),
    });
    setFormDrawer(true);
  };

  const submit = (values) => {
    const locations = (values.locations || []).filter((l) => l && (l.city || l.address || l.label || (l.departments || []).length));
    if (!locations.length) { message.error('Add at least one location'); return; }
    if (!locations.some((l) => l.is_primary)) locations[0].is_primary = true;
    const payload = { ...values, locations, city: locations.find((l) => l.is_primary)?.city || locations[0].city || null };
    if (editing) updateMut.mutate({ id: editing.id, data: payload });
    else createMut.mutate(payload);
  };

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (hospitals || []).filter((h) => {
      if (fCountry && h.country !== fCountry) return false;
      if (fStatus && (h.collaboration_status || 'Active') !== fStatus) return false;
      if (!needle) return true;
      const hay = [
        h.name, h.country, h.website,
        ...(h.locations || []).flatMap((l) => [l.label, l.city, l.state, l.address, ...(l.departments || [])]),
      ].filter(Boolean).join(' ').toLowerCase();
      return hay.includes(needle);
    });
  }, [hospitals, q, fCountry, fStatus]);

  return (
    <div>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0 }}>
          <MedicineBoxOutlined /> Collaborated Hospitals
        </h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>Add Hospital</Button>
      </div>

      <Card styles={{ body: { padding: 16 } }} style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            allowClear prefix={<SearchOutlined />} placeholder="Search name, city, department…"
            style={{ width: 320 }} value={q} onChange={(e) => setQ(e.target.value)}
          />
          <Select allowClear placeholder="Country" style={{ width: 160 }} value={fCountry} onChange={setFCountry}>
            {COUNTRIES.map((c) => <Option key={c} value={c}>{c}</Option>)}
          </Select>
          <Select allowClear placeholder="Status" style={{ width: 140 }} value={fStatus} onChange={setFStatus}>
            <Option value="Active">Active</Option>
            <Option value="Pending">Pending</Option>
            <Option value="Inactive">Inactive</Option>
          </Select>
          <Text type="secondary">{filtered.length} of {hospitals?.length || 0}</Text>
        </Space>
      </Card>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : filtered.length === 0 ? (
        <Empty description="No hospitals match" />
      ) : (
        <Row gutter={[16, 16]}>
          {filtered.map((h) => {
            const locCount = (h.locations || []).length;
            const depts = mergedDepartments(h.locations);
            const card = (
              <Card
                hoverable
                onClick={() => setSelected(h)}
                styles={{ body: { padding: 18 } }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 16, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {h.name}
                    </div>
                    {h.website && (
                      <Link href={h.website} target="_blank" rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()} style={{ fontSize: 12 }}>
                        <GlobalOutlined /> {h.website.replace(/^https?:\/\//, '')}
                      </Link>
                    )}
                  </div>
                  <Tag color={statusColor(h.collaboration_status)} style={{ marginInlineEnd: 0 }}>
                    {h.collaboration_status || 'Active'}
                  </Tag>
                </div>

                <Space size={4} wrap style={{ marginTop: 10 }}>
                  {h.country && <Tag color="blue">{h.country}</Tag>}
                  <Tag icon={<EnvironmentOutlined />}>
                    {(h.locations || []).map((l) => l.city).filter(Boolean).slice(0, 2).join(', ') || '—'}
                  </Tag>
                </Space>

                {depts.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <Space size={4} wrap>
                      {depts.slice(0, 3).map((d) => <Tag key={d} style={{ fontSize: 11 }}>{d}</Tag>)}
                      {depts.length > 3 && <Tag style={{ fontSize: 11 }}>+{depts.length - 3}</Tag>}
                    </Space>
                  </div>
                )}

                <Divider style={{ margin: '12px 0' }} />
                <Row>
                  <Col span={8}><Statistic title="Branches" value={locCount} valueStyle={{ fontSize: 18 }} /></Col>
                  <Col span={8}><Statistic title="Students" value={h.student_count || 0} valueStyle={{ fontSize: 18 }} /></Col>
                  <Col span={8}><Statistic title="Leads" value={h.lead_count || 0} valueStyle={{ fontSize: 18 }} /></Col>
                </Row>

                <div style={{ marginTop: 12 }} onClick={(e) => e.stopPropagation()}>
                  <Space>
                    <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(h)}>Edit</Button>
                    <Popconfirm
                      title="Delete this hospital?" description="This also removes its students and lead links."
                      okText="Delete" okButtonProps={{ danger: true }}
                      onConfirm={() => deleteMut.mutate(h.id)}
                    >
                      <Button size="small" danger icon={<DeleteOutlined />}>Delete</Button>
                    </Popconfirm>
                  </Space>
                </div>
              </Card>
            );
            return (
              <Col key={h.id} xs={24} sm={12} lg={8} xxl={6}>
                {locCount > 1
                  ? <Badge count={locCount} offset={[-6, 6]} style={{ backgroundColor: '#2563eb' }}>{card}</Badge>
                  : card}
              </Col>
            );
          })}
        </Row>
      )}

      {/* Detail */}
      {selected && <HospitalDetail hospital={selected} onClose={() => setSelected(null)} />}

      {/* Add / edit hospital */}
      <Drawer
        title={editing ? 'Edit Hospital' : 'Add New Hospital'}
        width={720}
        onClose={closeForm}
        open={formDrawer}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item name="name" label="Hospital Name" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="Apollo Hospitals" />
          </Form.Item>
          <Form.Item name="website" label="Website" rules={[{ type: 'url', message: 'Enter a valid URL (https://…)' }]}>
            <Input placeholder="https://www.apollohospitals.com" />
          </Form.Item>
          <Space size="middle" style={{ display: 'flex' }} align="start">
            <Form.Item name="country" label="Country" rules={[{ required: true, message: 'Required' }]} style={{ flex: 1 }}>
              <Select showSearch placeholder="Select country">
                {COUNTRIES.map((c) => <Option key={c} value={c}>{c}</Option>)}
              </Select>
            </Form.Item>
            <Form.Item name="collaboration_status" label="Status" style={{ flex: 1 }}>
              <Select>
                <Option value="Active">Active</Option>
                <Option value="Pending">Pending</Option>
                <Option value="Inactive">Inactive</Option>
              </Select>
            </Form.Item>
          </Space>
          <Form.Item name="contact_person" label="Contact Person"><Input placeholder="Dr. John Doe" /></Form.Item>
          <Space size="middle" style={{ display: 'flex' }} align="start">
            <Form.Item name="contact_email" label="Contact Email" style={{ flex: 1 }}><Input placeholder="contact@hospital.com" /></Form.Item>
            <Form.Item name="contact_phone" label="Contact Phone" style={{ flex: 1 }}><Input placeholder="+91-9876543210" /></Form.Item>
          </Space>

          <Divider orientation="left" style={{ marginTop: 8 }}><EnvironmentOutlined /> Locations</Divider>
          <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
            One row per branch. A hospital present in several cities gets several rows.
          </Text>
          <Form.List name="locations">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }, idx) => (
                  <Card
                    key={key}
                    size="small"
                    style={{ marginBottom: 12, background: 'var(--surface-2, #fafafa)' }}
                    title={`Branch ${idx + 1}`}
                    extra={fields.length > 1 && (
                      <Button type="text" danger size="small" icon={<MinusCircleOutlined />}
                        onClick={() => remove(name)} aria-label={`Remove branch ${idx + 1}`}>Remove</Button>
                    )}
                  >
                    <Space size="middle" style={{ display: 'flex' }} align="start">
                      <Form.Item {...rest} name={[name, 'label']} label="Label" style={{ flex: 1 }}>
                        <Input placeholder="Main / OMR campus / …" />
                      </Form.Item>
                      <Form.Item {...rest} name={[name, 'city']} label="City" style={{ flex: 1 }}>
                        <Input placeholder="Chennai" />
                      </Form.Item>
                      <Form.Item {...rest} name={[name, 'state']} label="State" style={{ flex: 1 }}>
                        <Input placeholder="Tamil Nadu" />
                      </Form.Item>
                    </Space>
                    <Form.Item {...rest} name={[name, 'address']} label="Address">
                      <Input.TextArea rows={2} placeholder="Street, area, PIN" />
                    </Form.Item>
                    <Form.Item {...rest} name={[name, 'departments']} label="Departments">
                      <Select mode="tags" placeholder="Cardiology, Nephrology & Urology, …" tokenSeparators={[',']}
                        options={DEPARTMENT_SUGGESTIONS.map((d) => ({ value: d, label: d }))} />
                    </Form.Item>
                    <Form.Item {...rest} name={[name, 'is_primary']} valuePropName="checked" noStyle hidden>
                      <input type="checkbox" />
                    </Form.Item>
                  </Card>
                ))}
                <Button type="dashed" onClick={() => add({ ...EMPTY_LOCATION })} block icon={<PlusOutlined />}>
                  Add location
                </Button>
              </>
            )}
          </Form.List>

          <Button type="primary" htmlType="submit" block style={{ marginTop: 20 }}
            loading={createMut.isPending || updateMut.isPending}>
            {editing ? 'Update Hospital' : 'Add Hospital'}
          </Button>
        </Form>
      </Drawer>
    </div>
  );
};

export default HospitalsPage;
