import React, { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Row, Col, Card, Button, Input, Select, Modal, Form, Upload, message, Empty,
  Space, Typography, Popconfirm, Spin, Tag,
} from 'antd';
import {
  FilePdfOutlined, UploadOutlined, SearchOutlined, DownloadOutlined,
  EyeOutlined, DeleteOutlined, InboxOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { brochuresAPI } from '../api/api';

const { Text } = Typography;

const currentUser = (() => {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
})();
const myName = currentUser.full_name || currentUser.email;

const prettySize = (bytes) => {
  if (!bytes) return '';
  const kb = bytes / 1024;
  return kb < 1024 ? `${Math.round(kb)} KB` : `${(kb / 1024).toFixed(1)} MB`;
};

const BrochuresPage = () => {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [form] = Form.useForm();
  const [pendingFile, setPendingFile] = useState(null);

  const { data: brochures, isLoading } = useQuery({
    queryKey: ['brochures'],
    queryFn: () => brochuresAPI.getAll().then((r) => r.data),
  });

  const uploadMut = useMutation({
    mutationFn: ({ name, file }) => brochuresAPI.upload(name, file),
    onSuccess: () => {
      message.success('Brochure uploaded');
      setUploadOpen(false);
      form.resetFields();
      setPendingFile(null);
      qc.invalidateQueries({ queryKey: ['brochures'] });
    },
    onError: (e) => message.error(e?.response?.data?.detail || 'Upload failed'),
  });

  const deleteMut = useMutation({
    mutationFn: (id) => brochuresAPI.delete(id),
    onSuccess: () => { message.success('Deleted'); qc.invalidateQueries({ queryKey: ['brochures'] }); },
    onError: (e) => message.error(e?.response?.data?.detail || 'Delete failed'),
  });

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (brochures || []).filter((b) => !needle || (b.name || '').toLowerCase().includes(needle));
  }, [brochures, q]);

  const canDelete = (b) => currentUser.role === 'Super Admin' || b.uploaded_by === myName;

  const openFile = (url) => window.open(url, '_blank', 'noopener,noreferrer');

  const submitUpload = (values) => {
    if (!pendingFile) { message.error('Choose a PDF file'); return; }
    uploadMut.mutate({ name: values.name.trim(), file: pendingFile });
  };

  return (
    <div>
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0 }}>
          <FilePdfOutlined /> Brochures
        </h1>
        <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
          Upload Brochure
        </Button>
      </div>

      <Card styles={{ body: { padding: 16 } }} style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            allowClear prefix={<SearchOutlined />} placeholder="Search brochures…"
            style={{ width: 320 }} value={q} onChange={(e) => setQ(e.target.value)}
          />
          <Select
            showSearch
            allowClear
            placeholder="All available brochures"
            style={{ width: 320 }}
            value={null}
            optionFilterProp="label"
            onChange={(url) => url && openFile(url)}
            options={(brochures || []).map((b) => ({ value: b.file_url, label: b.name }))}
          />
          <Text type="secondary">{filtered.length} of {brochures?.length || 0}</Text>
        </Space>
      </Card>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : filtered.length === 0 ? (
        <Empty description={brochures?.length ? 'No brochures match your search' : 'No brochures yet — upload the first one'} />
      ) : (
        <Row gutter={[16, 16]}>
          {filtered.map((b) => (
            <Col key={b.id} xs={24} sm={12} lg={8} xxl={6}>
              <Card
                styles={{ body: { padding: 18 } }}
                actions={[
                  <Button type="text" icon={<EyeOutlined />} onClick={() => openFile(b.file_url)}>View</Button>,
                  <a href={b.file_url} download={`${b.name}.pdf`} target="_blank" rel="noopener noreferrer">
                    <Button type="text" icon={<DownloadOutlined />}>Download</Button>
                  </a>,
                  canDelete(b) ? (
                    <Popconfirm title="Delete this brochure?" okText="Delete" okButtonProps={{ danger: true }}
                      onConfirm={() => deleteMut.mutate(b.id)}>
                      <Button type="text" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  ) : <span />,
                ]}
              >
                <Space align="start">
                  <FilePdfOutlined style={{ fontSize: 32, color: '#d4380d' }} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 15, wordBreak: 'break-word' }}>{b.name}</div>
                    <Space size={4} wrap style={{ marginTop: 6 }}>
                      {b.file_size ? <Tag>{prettySize(b.file_size)}</Tag> : null}
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {b.uploaded_by || 'Unknown'} · {b.created_at ? dayjs(b.created_at).format('DD MMM YYYY') : ''}
                      </Text>
                    </Space>
                  </div>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      <Modal
        title="Upload Brochure"
        open={uploadOpen}
        onCancel={() => { setUploadOpen(false); form.resetFields(); setPendingFile(null); }}
        onOk={() => form.submit()}
        confirmLoading={uploadMut.isPending}
        okText="Upload"
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={submitUpload}>
          <Form.Item name="name" label="Brochure name" rules={[{ required: true, message: 'Give it a name' }]}>
            <Input placeholder="e.g. Fellowship in Cardiology — 2026" />
          </Form.Item>
          <Form.Item label="PDF file" required>
            <Upload.Dragger
              accept="application/pdf,.pdf"
              maxCount={1}
              multiple={false}
              beforeUpload={(file) => {
                const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
                if (!isPdf) { message.error('Only PDF files are accepted'); return Upload.LIST_IGNORE; }
                if (file.size > 25 * 1024 * 1024) { message.error('File is larger than 25 MB'); return Upload.LIST_IGNORE; }
                setPendingFile(file);
                return false; // keep it local; we upload on submit
              }}
              onRemove={() => setPendingFile(null)}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">Click or drag a PDF here</p>
              <p className="ant-upload-hint">Single PDF, up to 25 MB.</p>
            </Upload.Dragger>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default BrochuresPage;
