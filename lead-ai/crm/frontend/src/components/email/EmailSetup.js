import React, { useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Form, Input, Select, InputNumber, Button, Alert, Space, Typography, Popconfirm, message } from 'antd';
import { MailOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { emailAPI } from '../../api/api';

const { Text } = Typography;
const errorText = (e, fallback) => e?.response?.data?.detail || fallback;

/** Connect my own mailbox (Gmail / Outlook / Zoho / other SMTP) so leads receive email from my address. */
export default function EmailSetup() {
  const qc = useQueryClient();
  const [form] = Form.useForm();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['email-account'],
    queryFn: () => emailAPI.account().then((r) => r.data),
  });

  useEffect(() => {
    if (data) {
      form.setFieldsValue({
        provider: data.provider, smtp_user: data.smtp_user, from_name: data.from_name,
        signature: data.signature, daily_limit: data.daily_limit, smtp_host: data.smtp_host, smtp_port: data.smtp_port,
      });
    }
  }, [data, form]);

  const save = useMutation({
    mutationFn: (values) => emailAPI.save(values).then((r) => r.data),
    onSuccess: () => {
      message.success('Mailbox connected');
      form.setFieldsValue({ password: '' });
      qc.invalidateQueries({ queryKey: ['email-account'] });
    },
    onError: (e) => message.error(errorText(e, 'Could not connect the mailbox')),
  });
  const test = useMutation({
    mutationFn: () => emailAPI.test().then((r) => r.data),
    onSuccess: (d) => message.success(`Test email sent to ${d.sent_to}`),
    onError: (e) => message.error(errorText(e, 'Test email failed')),
  });
  const disconnect = useMutation({
    mutationFn: () => emailAPI.disconnect(),
    onSuccess: () => { message.success('Mailbox disconnected'); form.resetFields(['password']); qc.invalidateQueries({ queryKey: ['email-account'] }); },
  });

  const watched = Form.useWatch('provider', form);
  const provider = watched || data?.provider || 'gmail';
  const preset = data?.providers?.[provider];

  if (isError) {
    return <Alert type="error" showIcon message="Email settings could not be loaded"
      action={<Button size="small" onClick={() => refetch()}>Retry</Button>} />;
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', maxWidth: 640 }}>
      {data && !data.server_ready && (
        <Alert type="warning" showIcon message="Email is not switched on for this CRM yet"
          description="The administrator must set EMAIL_SECRET_KEY on the server (it encrypts saved passwords). Until then a mailbox cannot be saved." />
      )}
      {data?.configured ? (
        <Alert type="success" showIcon icon={<MailOutlined />}
          message={`Sending from ${data.smtp_user}`}
          description={`${data.sent_today} of ${data.daily_limit} emails used today${data.last_ok_at ? ` · verified ${dayjs(data.last_ok_at).format('DD/MM, h:mm A')}` : ''}`} />
      ) : data?.shared_sender ? (
        <Alert type="info" showIcon message="Not connected: emails currently go from the company mailbox"
          description="Replies still reach you. Connect your own mailbox so leads see your address." />
      ) : (
        <Alert type="info" showIcon message="Connect your mailbox to email leads from your own address" />
      )}

      <Form form={form} layout="vertical" disabled={isLoading} initialValues={{ provider: 'gmail', daily_limit: 400 }}
        onFinish={(v) => save.mutate(v)}>
        <Form.Item name="provider" label="Email provider">
          <Select options={Object.entries(data?.providers || {}).map(([value, p]) => ({ value, label: p.label }))} />
        </Form.Item>
        {preset?.help && <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>{preset.help}</Text>}
        {provider === 'custom' && (
          <Space style={{ width: '100%' }} align="start">
            <Form.Item name="smtp_host" label="SMTP host" rules={[{ required: true }]}><Input placeholder="smtp.example.com" /></Form.Item>
            <Form.Item name="smtp_port" label="Port"><InputNumber min={1} max={65535} placeholder="587" /></Form.Item>
          </Space>
        )}
        <Form.Item name="smtp_user" label="Your email address" rules={[{ required: true, type: 'email', message: 'Enter your email address' }]}>
          <Input placeholder="you@gmail.com" autoComplete="off" />
        </Form.Item>
        <Form.Item name="password" label="App password"
          rules={[{ required: !data?.configured, message: 'Enter your app password' }]}
          extra={data?.configured ? 'Leave blank to keep the saved password.' : 'Not your normal password. It is stored encrypted.'}>
          <Input.Password autoComplete="new-password" placeholder={data?.configured ? '••••••••••••••••' : 'abcd efgh ijkl mnop'} />
        </Form.Item>
        <Form.Item name="from_name" label="Name shown to leads"><Input maxLength={100} placeholder="Your name" /></Form.Item>
        <Form.Item name="signature" label="Signature (added under every email)">
          <Input.TextArea rows={3} maxLength={1000} placeholder={'Your name\nMedFellow Academy\n+91 …'} />
        </Form.Item>
        <Form.Item name="daily_limit" label="Daily sending limit" extra="Gmail allows about 500 a day. Keep this below your provider's limit.">
          <InputNumber min={1} max={2000} />
        </Form.Item>
        <Space wrap>
          <Button type="primary" htmlType="submit" loading={save.isPending}>Save and verify</Button>
          <Button onClick={() => test.mutate()} loading={test.isPending} disabled={!data?.configured}>Send test email to myself</Button>
          {data?.configured && (
            <Popconfirm title="Disconnect your mailbox?" onConfirm={() => disconnect.mutate()}>
              <Button danger>Disconnect</Button>
            </Popconfirm>)}
        </Space>
      </Form>
    </Space>
  );
}
