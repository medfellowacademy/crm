import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, Table, Tag, Button, Space, Typography, Modal, Form, Input, DatePicker, message, Result, Empty, Statistic, Tooltip } from 'antd';
import { PhoneOutlined, CheckOutlined, MessageOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { paymentsAPI } from '../../api/api';
import { fmt } from '../../utils/finance';
import PayEmiModal from './PayEmiModal';

const { Text } = Typography;
const ageColor = (d) => (d > 60 ? 'red' : d > 30 ? 'volcano' : d > 7 ? 'orange' : 'gold');

function FollowupModal({ target, onClose, onDone }) {
  const [form] = Form.useForm();
  const save = useMutation({
    mutationFn: (v) => paymentsAPI.addFollowup(target.lead_id, {
      note: v.note?.trim() || `Expected payment on ${v.promised_date.format('DD MMM YYYY')}`,
      emi_index: target.emi_index,
      promised_date: v.promised_date ? v.promised_date.format('YYYY-MM-DD') : undefined,
    }),
    onSuccess: () => { message.success('Saved'); onDone?.(); onClose(); },
    onError: (e) => message.error(e?.response?.data?.detail || 'Could not save the follow-up'),
  });
  return (
    <Modal
      open={!!target} title={target ? `Payment update — ${target.name}` : ''} okText="Save"
      confirmLoading={save.isPending} onCancel={onClose} destroyOnClose
      onOk={() => form.validateFields().then((v) => save.mutate(v))}
    >
      <Form form={form} layout="vertical" initialValues={{ promised_date: target?.expected_date ? dayjs(target.expected_date) : undefined }}>
        <Form.Item name="promised_date" label="Expected payment date" dependencies={['note']}
          rules={[({ getFieldValue }) => ({
            validator: (_, v) => (v || getFieldValue('note')?.trim() ? Promise.resolve() : Promise.reject(new Error('Pick the expected date or add a note'))),
          })]}>
          <DatePicker style={{ width: '100%' }} format="DD MMM YYYY" />
        </Form.Item>
        <Form.Item name="note" label="Comment (optional when a date is set)" dependencies={['promised_date']}>
          <Input.TextArea rows={3} maxLength={1000} placeholder="e.g. Called, will pay after salary" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default function OverdueTab({ onChanged }) {
  const queryClient = useQueryClient();
  const [pay, setPay] = useState(null);
  const [follow, setFollow] = useState(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['payments-overdue'],
    queryFn: () => paymentsAPI.overdue().then((r) => r.data),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['payments-overdue'] });
    queryClient.invalidateQueries({ queryKey: ['payment-history'] });
    onChanged?.();
  };

  if (isError) {
    return <Result status="warning" title="Couldn't load overdue EMIs" extra={<Button type="primary" onClick={() => refetch()}>Retry</Button>} />;
  }

  const items = data?.items || [];
  return (
    <div>
      <Space size={24} style={{ marginBottom: 16 }}>
        <Statistic title="Overdue EMIs" value={items.length} />
        <Statistic title="Total overdue" value={data?.total || 0} formatter={fmt} valueStyle={{ color: items.length ? '#cf1322' : undefined }} />
      </Space>
      <Card styles={{ body: { padding: 0 } }}>
        <Table
          loading={isLoading} size="middle" rowKey={(r) => `${r.lead_id}-${r.emi_index}`}
          dataSource={items} pagination={{ pageSize: 15, hideOnSinglePage: true }} scroll={{ x: 'max-content' }}
          locale={{ emptyText: <Empty description="No overdue EMIs — nice" /> }}
          columns={[
            { title: 'Lead', key: 'lead', render: (_, r) => (
              <div><div style={{ fontWeight: 600 }}>{r.name}</div><Text type="secondary" style={{ fontSize: 12 }}>{r.phone}</Text></div>
            ) },
            { title: 'Counselor', dataIndex: 'counselor' },
            { title: 'Instalment', dataIndex: 'label', render: (l, r) => l || `EMI ${r.emi_index + 1}` },
            { title: 'Due', dataIndex: 'due_date', render: (d) => dayjs(d).format('DD MMM YYYY') },
            { title: 'Overdue', dataIndex: 'days_overdue', sorter: (a, b) => a.days_overdue - b.days_overdue, defaultSortOrder: 'descend',
              render: (d) => <Tag color={ageColor(d)}>{d} day{d !== 1 ? 's' : ''}</Tag> },
            { title: 'Amount', dataIndex: 'amount', align: 'right', render: (v) => <Text strong style={{ color: '#cf1322' }}>{fmt(v)}</Text> },
            { title: 'Expected on', key: 'expected', width: 150,
              sorter: (a, b) => (a.expected_date || '9999').localeCompare(b.expected_date || '9999'),
              render: (_, r) => {
                if (!r.expected_date) return <Button size="small" type="dashed" onClick={() => setFollow(r)}>Set date</Button>;
                const days = dayjs(r.expected_date).startOf('day').diff(dayjs().startOf('day'), 'day');
                const [color, hint] = days < 0 ? ['red', `missed by ${-days}d`] : days === 0 ? ['gold', 'today'] : ['green', `in ${days}d`];
                return (
                  <Tooltip title="Change the expected date">
                    <Tag color={color} style={{ cursor: 'pointer' }} onClick={() => setFollow(r)}>
                      {dayjs(r.expected_date).format('DD MMM')} · {hint}
                    </Tag>
                  </Tooltip>
                );
              } },
            { title: 'Last comment', key: 'last', width: 240, render: (_, r) => {
              const f = r.last_followup;
              if (!f) return <Text type="secondary">None yet</Text>;
              return (
                <div style={{ fontSize: 12 }}>
                  <div>{f.note}</div>
                  <Text type="secondary">{f.created_by} · {dayjs(f.created_at).format('DD MMM')}{f.promised_date ? ` · promised ${dayjs(f.promised_date).format('DD MMM')}` : ''}</Text>
                </div>
              );
            } },
            { title: '', key: 'actions', render: (_, r) => (
              <Space size={4} wrap>
                {r.phone && <Button size="small" icon={<PhoneOutlined />} href={`tel:${r.phone}`} />}
                <Button size="small" icon={<MessageOutlined />} onClick={() => setFollow(r)}>Comment</Button>
                <Button size="small" type="primary" icon={<CheckOutlined />}
                  onClick={() => setPay({ leadId: r.lead_id, index: r.emi_index, name: r.name, amount: r.amount, dueDate: r.due_date, label: r.label })}>
                  Mark paid
                </Button>
              </Space>
            ) },
          ]}
        />
      </Card>
      <PayEmiModal target={pay} onClose={() => setPay(null)} onDone={refresh} />
      <FollowupModal target={follow} onClose={() => setFollow(null)} onDone={refresh} />
    </div>
  );
}
