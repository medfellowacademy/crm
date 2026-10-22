import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, Table, Tag, Button, Space, Typography, Modal, Form, Input, DatePicker, message, Result, Empty, Statistic } from 'antd';
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
      note: v.note, emi_index: target.emi_index,
      promised_date: v.promised_date ? v.promised_date.format('YYYY-MM-DD') : undefined,
    }),
    onSuccess: () => { message.success('Follow-up logged'); onDone?.(); onClose(); },
    onError: (e) => message.error(e?.response?.data?.detail || 'Could not save the follow-up'),
  });
  return (
    <Modal
      open={!!target} title={target ? `Log follow-up — ${target.name}` : ''} okText="Save"
      confirmLoading={save.isPending} onCancel={onClose} destroyOnClose
      onOk={() => form.validateFields().then((v) => save.mutate(v))}
    >
      <Form form={form} layout="vertical">
        <Form.Item name="note" label="What happened?" rules={[{ required: true, message: 'Add a short note' }]}>
          <Input.TextArea rows={3} maxLength={1000} placeholder="e.g. Called, will pay by Friday" />
        </Form.Item>
        <Form.Item name="promised_date" label="Promised payment date">
          <DatePicker style={{ width: '100%' }} format="DD MMM YYYY" />
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
            { title: 'EMI', dataIndex: 'emi_index', align: 'center', render: (i) => `#${i + 1}` },
            { title: 'Due', dataIndex: 'due_date', render: (d) => dayjs(d).format('DD MMM YYYY') },
            { title: 'Overdue', dataIndex: 'days_overdue', sorter: (a, b) => a.days_overdue - b.days_overdue, defaultSortOrder: 'descend',
              render: (d) => <Tag color={ageColor(d)}>{d} day{d !== 1 ? 's' : ''}</Tag> },
            { title: 'Amount', dataIndex: 'amount', align: 'right', render: (v) => <Text strong style={{ color: '#cf1322' }}>{fmt(v)}</Text> },
            { title: 'Last follow-up', key: 'last', width: 240, render: (_, r) => {
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
                <Button size="small" icon={<MessageOutlined />} onClick={() => setFollow(r)}>Log</Button>
                <Button size="small" type="primary" icon={<CheckOutlined />}
                  onClick={() => setPay({ leadId: r.lead_id, index: r.emi_index, name: r.name, amount: r.amount, dueDate: r.due_date })}>
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
