import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Table, Button, Tag, Space, Card, Form, Input, Select, Drawer, message } from 'antd';
import { PlusOutlined, MedicineBoxOutlined } from '@ant-design/icons';
import { hospitalsAPI, coursesAPI } from '../api/api';

const { Option } = Select;

const HospitalsPage = () => {
  const queryClient = useQueryClient();
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [form] = Form.useForm();

  const { data: hospitals, isLoading } = useQuery({
    queryKey: ['hospitals'],
    queryFn: () => hospitalsAPI.getAll().then(res => res.data)
  });

  const { data: courses } = useQuery({
    queryKey: ['courses'],
    queryFn: () => coursesAPI.getAll().then(res => res.data)
  });

  const createHospitalMutation = useMutation({
    mutationFn: (data) => hospitalsAPI.create(data),
    onSuccess: () => {
      message.success('Hospital added successfully!');
      setDrawerVisible(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['hospitals'] });
    },
  });

  const columns = [
    {
      title: 'Hospital Name',
      dataIndex: 'name',
      key: 'name',
      render: (text) => <strong>{text}</strong>,
    },
    {
      title: 'Country',
      dataIndex: 'country',
      key: 'country',
      render: (country) => <Tag color="blue">{country}</Tag>,
    },
    {
      title: 'City',
      dataIndex: 'city',
      key: 'city',
    },
    {
      title: 'Contact Person',
      dataIndex: 'contact_person',
      key: 'contact_person',
    },
    {
      title: 'Contact Email',
      dataIndex: 'contact_email',
      key: 'contact_email',
    },
    {
      title: 'Phone',
      dataIndex: 'contact_phone',
      key: 'contact_phone',
    },
    {
      title: 'Status',
      dataIndex: 'collaboration_status',
      key: 'collaboration_status',
      render: (status) => (
        <Tag color={status === 'Active' ? 'green' : 'red'}>
          {status}
        </Tag>
      ),
    },
    {
      title: 'Courses Offered',
      dataIndex: 'courses_offered',
      key: 'courses_offered',
      render: (courseIds) => courseIds?.length || 0,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 600, margin: 0 }}>
          <MedicineBoxOutlined /> Collaborated Hospitals
        </h1>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setDrawerVisible(true)}
        >
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
        />
      </Card>

      <Drawer
        title="Add New Hospital"
        width={600}
        onClose={() => setDrawerVisible(false)}
        open={drawerVisible}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => createHospitalMutation.mutate(values)}
        >
          <Form.Item
            name="name"
            label="Hospital Name"
            rules={[{ required: true }]}
          >
            <Input placeholder="Apollo Hospitals" />
          </Form.Item>

          <Form.Item name="country" label="Country" rules={[{ required: true }]}>
            <Select placeholder="Select country">
              <Option value="India">India</Option>
              <Option value="UAE">UAE</Option>
              <Option value="Saudi Arabia">Saudi Arabia</Option>
              <Option value="Kuwait">Kuwait</Option>
            </Select>
          </Form.Item>

          <Form.Item name="city" label="City" rules={[{ required: true }]}>
            <Input placeholder="Chennai" />
          </Form.Item>

          <Form.Item name="contact_person" label="Contact Person">
            <Input placeholder="Dr. John Doe" />
          </Form.Item>

          <Form.Item name="contact_email" label="Contact Email">
            <Input placeholder="contact@hospital.com" />
          </Form.Item>

          <Form.Item name="contact_phone" label="Contact Phone">
            <Input placeholder="+91-9876543210" />
          </Form.Item>

          <Form.Item name="courses_offered" label="Courses Offered">
            <Select mode="multiple" placeholder="Select courses">
              {courses?.map(course => (
                <Option key={course.id} value={course.id}>
                  {course.course_name}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Button type="primary" htmlType="submit" block>
            Add Hospital
          </Button>
        </Form>
      </Drawer>
    </div>
  );
};

export default HospitalsPage;
