import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Modal, Form, Input, Select, Button, Alert, Space, Typography, message } from 'antd';
import { MailOutlined } from '@ant-design/icons';
import { emailAPI, leadsAPI } from '../../api/api';

const { Text } = Typography;

function Compose({ lead, leadId, onClose }) {
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const account = useQuery({ queryKey: ['email-account'], queryFn: () => emailAPI.account().then((r) => r.data), staleTime: 60 * 1000 });
  const templates = useQuery({ queryKey: ['email-templates'], queryFn: () => emailAPI.templates().then((r) => r.data), staleTime: 10 * 60 * 1000 });

  const send = useMutation({
    mutationFn: (v) => leadsAPI.sendEmail(leadId, v.subject, v.body).then((r) => r.data),
    onSuccess: (d) => {
      message.success(`Email sent to ${d.to}`);
      qc.invalidateQueries({ queryKey: ['email-account'] });
      qc.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes(String(leadId)) });
      onClose();
    },
    onError: (e) => message.error(e?.response?.data?.detail || 'The email could not be sent'),
  });

  const a = account.data;
  const noSender = a && !a.configured && !a.shared_sender;
  const from = a?.configured ? a.smtp_user : (a?.shared_sender ? 'the company mailbox (replies come to you)' : null);

  return (
    <>
      <Space direction="vertical" size={4} style={{ width: '100%', marginBottom: 12 }}>
        <Text><b>To:</b> {lead?.full_name} &lt;{lead?.email || 'no email address'}&gt;</Text>
        {from && <Text type="secondary"><b>From:</b> {from}{a?.configured ? ` · ${a.sent_today}/${a.daily_limit} sent today` : ''}</Text>}
      </Space>
      {!lead?.email && <Alert type="warning" showIcon style={{ marginBottom: 12 }} message="This lead has no email address. Add one first." />}
      {noSender && (
        <Alert type="warning" showIcon style={{ marginBottom: 12 }} message="Connect your email first"
          description="Add your Gmail, Outlook or Zoho app password once, then you can email leads from your own address."
          action={<Button size="small" type="primary" onClick={() => { onClose(); navigate('/settings'); }}>Connect</Button>} />
      )}
      <Form form={form} layout="vertical" onFinish={(v) => send.mutate(v)}>
        <Form.Item label="Template">
          <Select allowClear placeholder="Start from a template (optional)" loading={templates.isLoading}
            options={(templates.data || []).map((t) => ({ value: t.id, label: t.name }))}
            onChange={(id) => {
              const t = (templates.data || []).find((x) => x.id === id);
              if (t) form.setFieldsValue({ subject: t.subject, body: t.body });
            }} />
        </Form.Item>
        <Form.Item name="subject" label="Subject" rules={[{ required: true, whitespace: true, message: 'Enter a subject' }]}>
          <Input placeholder="Email subject" maxLength={200} />
        </Form.Item>
        <Form.Item name="body" label="Message" rules={[{ required: true, whitespace: true, message: 'Write a message' }]}
          extra="{name}, {course} and {counselor} are filled in automatically. Your signature is added.">
          <Input.TextArea rows={9} placeholder="Email message..." />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={send.isPending} disabled={!lead?.email || noSender}>
          Send email
        </Button>
      </Form>
    </>
  );
}

/** Compose and send an email to a lead from the user's own mailbox. */
export default function EmailComposeModal({ open, onClose, lead, leadId }) {
  return (
    <Modal title={<span><MailOutlined /> Send Email</span>} open={open} onCancel={onClose} footer={null} width={640} destroyOnClose>
      {open && <Compose lead={lead} leadId={leadId} onClose={onClose} />}
    </Modal>
  );
}
