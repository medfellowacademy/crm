import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Table, Button, Tag, Space, Card, Form, Input, Select, Drawer, message,
  Popconfirm, Divider, Typography, Empty,
} from 'antd';
import {
  PlusOutlined, MedicineBoxOutlined, EditOutlined, DeleteOutlined,
  MinusCircleOutlined, EnvironmentOutlined, GlobalOutlined,
} from '@ant-design/icons';
import { hospitalsAPI, coursesAPI } from '../api/api';

const { Option } = Select;
const { Text, Link } = Typography;

// Mirrors the fellowship categories in backend/courses_data.py — the medical
// departments MedFellow actually runs programmes in. Free text is still allowed
// (the Select is in "tags" mode) so users can add anything else.
const DEPARTMENT_SUGGESTIONS = [
  'Cardiology', 'Critical Care & Emergency', 'Dermatology & Aesthetics',
  'Diabetes & Endocrinology', 'Gastroenterology', 'Nephrology & Urology',
  'Neurology', 'Obstetrics & Gynecology', 'Oncology', 'Paediatrics',
  'Pain & Anaesthesia', 'Radiology & Imaging', 'Reproductive Medicine & IVF',
  'Surgery', 'Other Specialties',
];

const COUNTRIES = ['India', 'UAE', 'Saudi Arabia', 'Kuwait', 'Qatar', 'Oman', 'Bahrain', 'UK', 'USA'];

const EMPTY_LOCATION = { label: '', address: '', city: '', state: '', departments: [], is_primary: false };

/** Unique, sorted list of every department across a hospital's locations. */
const mergedDepartments = (locations = []) => {
  const set = new Set();
  locations.forEach((l) => (l.departments || []).forEach((d) => d && set.add(d)));
  return [...set].sort();
};

const HospitalsPage = () => {
  const queryClient = useQueryClient();
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [editingHospital, setEditingHospital] = useState(null);
  const [form] = Form.useForm();

  const { data: hospitals, isLoading } = useQuery({
    queryKey: ['hospitals'],
    queryFn: () => hospitalsAPI.getAll().then((res) => res.data),
  });

  const { data: courses } = useQuery({
    queryKey: ['courses'],
    queryFn: () => coursesAPI.getAll().then((res) => res.data),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['hospitals'] });

  const createHospitalMutation = useMutation({
    mutationFn: (data) => hospitalsAPI.create(data),
    onSuccess: () => { message.success('Hospital added'); closeDrawer(); invalidate(); },
    onError: () => message.error('Failed to add hospital'),
  });

  const updateHospitalMutation = useMutation({
    mutationFn: ({ id, data }) => hospitalsAPI.update(id, data),
    onSuccess: () => { message.success('Hospital updated'); closeDrawer(); invalidate(); },
    onError: () => message.error('Failed to update hospital'),
  });

  const deleteHospitalMutation = useMutation({
    mutationFn: (id) => hospitalsAPI.delete(id),
    onSuccess: () => { message.success('Hospital deleted'); invalidate(); },
    onError: () => message.error('Failed to delete hospital'),
  });

  const closeDrawer = () => {
    setDrawerVisible(false);
    setEditingHospital(null);
    form.resetFields();
  };

  const openAddDrawer = () => {
    setEditingHospital(null);
    form.resetFields();
    form.setFieldsValue({
      collaboration_status: 'Active',
      country: 'India',
      locations: [{ ...EMPTY_LOCATION, label: 'Main', is_primary: true }],
    });
    setDrawerVisible(true);
  };

  const openEditDrawer = (hospital) => {
    setEditingHospital(hospital);
    form.resetFields();
    form.setFieldsValue({
      ...hospital,
      locations: (hospital.locations && hospital.locations.length
        ? hospital.locations
        : [{ ...EMPTY_LOCATION, label: 'Main', city: hospital.city, is_primary: true }]
      ).map((l) => ({ ...EMPTY_LOCATION, ...l })),
    });
    setDrawerVisible(true);
  };

  const handleSubmit = (values) => {
    const locations = (values.locations || []).filter(
      (l) => l && (l.city || l.address || l.label || (l.departments || []).length),
    );
    if (!locations.length) {
      message.error('Add at least one location');
      return;
    }
    // Exactly one primary; default to the first.
    if (!locations.some((l) => l.is_primary)) locations[0].is_primary = true;

    const payload = {
      ...values,
      locations,
      city: locations.find((l) => l.is_primary)?.city || locations[0].city || null,
    };

    if (editingHospital) {
      updateHospitalMutation.mutate({ id: editingHospital.id, data: payload });
    } else {
      createHospitalMutation.mutate(payload);
    }
  };

  const columns = [
    {
      title: 'Hospital',
      dataIndex: 'name',
      key: 'name',
      render: (text, record) => (
        <Space direction="vertical" size={0}>
          <strong>{text}</strong>
          {record.website && (
            <Link href={record.website} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12 }}>
              <GlobalOutlined /> {record.website.replace(/^https?:\/\//, '')}
            </Link>
          )}
        </Space>
      ),
    },
    {
      title: 'Country',
      dataIndex: 'country',
      key: 'country',
      render: (country) => (country ? <Tag color="blue">{country}</Tag> : '—'),
    },
    {
      title: 'Locations',
      dataIndex: 'locations',
      key: 'locations',
      render: (locations = []) => {
        if (!locations.length) return <Text type="secondary">—</Text>;
        const cities = locations.map((l) => l.city).filter(Boolean);
        return (
          <Space size={4} wrap>
            <Tag icon={<EnvironmentOutlined />} color="geekblue">
              {locations.length} {locations.length === 1 ? 'branch' : 'branches'}
            </Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>{cities.slice(0, 3).join(', ')}{cities.length > 3 ? '…' : ''}</Text>
          </Space>
        );
      },
    },
    {
      title: 'Departments',
      key: 'departments',
      render: (_, record) => {
        const depts = mergedDepartments(record.locations);
        if (!depts.length) return <Text type="secondary">—</Text>;
        return (
          <Space size={4} wrap>
            {depts.slice(0, 3).map((d) => <Tag key={d}>{d}</Tag>)}
            {depts.length > 3 && <Tag>+{depts.length - 3}</Tag>}
          </Space>
        );
      },
    },
    {
      title: 'Courses',
      dataIndex: 'courses_offered',
      key: 'courses_offered',
      align: 'center',
      render: (courseIds) => courseIds?.length || 0,
    },
    {
      title: 'Status',
      dataIndex: 'collaboration_status',
      key: 'collaboration_status',
      render: (status) => (
        <Tag color={status === 'Active' ? 'green' : status === 'Pending' ? 'gold' : 'red'}>{status || 'Active'}</Tag>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditDrawer(record)}>Edit</Button>
          <Popconfirm
            title="Delete this hospital?"
            description="This action cannot be undone."
            onConfirm={() => deleteHospitalMutation.mutate(record.id)}
            okText="Delete"
            okButtonProps={{ danger: true }}
            cancelText="Cancel"
          >
            <Button size="small" danger icon={<DeleteOutlined />} loading={deleteHospitalMutation.isPending}>
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const expandedRowRender = (record) => {
    const locations = record.locations || [];
    if (!locations.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No locations recorded" />;
    return (
      <Table
        size="small"
        pagination={false}
        rowKey={(_, i) => i}
        dataSource={locations}
        columns={[
          {
            title: 'Branch',
            dataIndex: 'label',
            width: 160,
            render: (label, loc) => (
              <Space size={4}>
                {label || '—'}
                {loc.is_primary && <Tag color="blue" style={{ marginInlineStart: 4 }}>Primary</Tag>}
              </Space>
            ),
          },
          { title: 'Address', dataIndex: 'address', render: (v) => v || <Text type="secondary">—</Text> },
          { title: 'City', dataIndex: 'city', width: 130, render: (v) => v || '—' },
          { title: 'State', dataIndex: 'state', width: 130, render: (v) => v || '—' },
          {
            title: 'Departments',
            dataIndex: 'departments',
            render: (depts = []) => (depts.length
              ? <Space size={4} wrap>{depts.map((d) => <Tag key={d}>{d}</Tag>)}</Space>
              : <Text type="secondary">—</Text>),
          },
        ]}
      />
    );
  };

  return (
    <div>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0 }}>
          <MedicineBoxOutlined /> Collaborated Hospitals
        </h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={openAddDrawer}>
          Add Hospital
        </Button>
      </div>

      <Card>
        <Table
          dataSource={hospitals}
          columns={columns}
          loading={isLoading}
          rowKey="id"
          pagination={{ pageSize: 10 }}
          expandable={{
            expandedRowRender,
            rowExpandable: (record) => (record.locations || []).length > 0,
          }}
        />
      </Card>

      <Drawer
        title={editingHospital ? 'Edit Hospital' : 'Add New Hospital'}
        width={720}
        onClose={closeDrawer}
        open={drawerVisible}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="name" label="Hospital Name" rules={[{ required: true, message: 'Required' }]}>
            <Input placeholder="Apollo Hospitals" />
          </Form.Item>

          <Form.Item
            name="website"
            label="Website"
            rules={[{ type: 'url', message: 'Enter a valid URL (https://…)' }]}
          >
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

          <Form.Item name="contact_person" label="Contact Person">
            <Input placeholder="Dr. John Doe" />
          </Form.Item>
          <Space size="middle" style={{ display: 'flex' }} align="start">
            <Form.Item name="contact_email" label="Contact Email" style={{ flex: 1 }}>
              <Input placeholder="contact@hospital.com" />
            </Form.Item>
            <Form.Item name="contact_phone" label="Contact Phone" style={{ flex: 1 }}>
              <Input placeholder="+91-9876543210" />
            </Form.Item>
          </Space>

          <Form.Item name="courses_offered" label="Courses Offered">
            <Select mode="multiple" placeholder="Select courses" optionFilterProp="children" allowClear>
              {courses?.map((course) => (
                <Option key={course.id} value={course.id}>{course.course_name}</Option>
              ))}
            </Select>
          </Form.Item>

          <Divider orientation="left" style={{ marginTop: 8 }}>
            <EnvironmentOutlined /> Locations
          </Divider>
          <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
            Add one row per branch. A hospital present in several cities gets several rows.
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
                      <Button
                        type="text"
                        danger
                        size="small"
                        icon={<MinusCircleOutlined />}
                        onClick={() => remove(name)}
                        aria-label={`Remove branch ${idx + 1}`}
                      >
                        Remove
                      </Button>
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
                      <Select
                        mode="tags"
                        placeholder="Cardiology, Nephrology & Urology, …"
                        tokenSeparators={[',']}
                        options={DEPARTMENT_SUGGESTIONS.map((d) => ({ value: d, label: d }))}
                      />
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

          <Button
            type="primary"
            htmlType="submit"
            block
            style={{ marginTop: 20 }}
            loading={createHospitalMutation.isPending || updateHospitalMutation.isPending}
          >
            {editingHospital ? 'Update Hospital' : 'Add Hospital'}
          </Button>
        </Form>
      </Drawer>
    </div>
  );
};

export default HospitalsPage;
