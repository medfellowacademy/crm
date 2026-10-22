import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Form, Input, DatePicker, Button, Typography, Spin, Modal, Tag, message } from 'antd';
import dayjs from 'dayjs';
import { paymentsAPI } from '../../api/api';
import { fmt } from '../../utils/finance';

const { Text } = Typography;

// Payment history (who recorded what, when, how) + free-text comments about this
// lead's payments, with a box to add one. Comments live in `payment_followups`.
export function PaymentActivity({ leadId, compact = false }) {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();

  const { data, isLoading } = useQuery({
    queryKey: ['payment-history', leadId],
    queryFn: () => paymentsAPI.history(leadId).then((r) => r.data),
  });

  const add = useMutation({
    mutationFn: (v) => paymentsAPI.addFollowup(leadId, {
      note: v.note.trim(),
      promised_date: v.promised_date ? v.promised_date.format('YYYY-MM-DD') : undefined,
    }),
    onSuccess: () => {
      form.resetFields();
      message.success('Comment added');
      ['payment-history', 'payments-overdue', 'payments-emis'].forEach((k) => queryClient.invalidateQueries({ queryKey: [k] }));
    },
    onError: (e) => message.error(e?.response?.data?.detail || 'Could not save the comment'),
  });

  const payments = data?.payments || [];
  const comments = data?.followups || [];

  return (
    <div style={{ fontSize: 12 }}>
      <Form form={form} layout="vertical" onFinish={(v) => add.mutate(v)} style={{ marginBottom: 12 }}>
        <Form.Item name="note" style={{ marginBottom: 6 }} rules={[{ required: true, whitespace: true, message: 'Write a comment first' }]}>
          <Input.TextArea rows={compact ? 2 : 3} maxLength={1000} showCount placeholder="Write a comment about this payment… (e.g. parent asked to move the date, cheque in transit)" />
        </Form.Item>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <Form.Item name="promised_date" style={{ marginBottom: 0 }}>
            <DatePicker size="small" format="DD MMM YYYY" placeholder="Promised date (optional)" />
          </Form.Item>
          <Button type="primary" size="small" htmlType="submit" loading={add.isPending}>Add comment</Button>
        </div>
      </Form>

      {isLoading ? <Spin size="small" /> : (
        <>
          {comments.length === 0 && payments.length === 0 && <Text type="secondary">No comments or payments recorded yet.</Text>}
          {comments.map((c) => (
            <div key={`c${c.id}`} style={{ padding: '6px 0', borderBottom: '1px solid #e5e7eb' }}>
              <div style={{ whiteSpace: 'pre-wrap' }}>{c.note}</div>
              <Text type="secondary">
                {c.created_by} · {dayjs(c.created_at).format('DD MMM YYYY, h:mm A')}
                {c.promised_date ? ` · promised ${dayjs(c.promised_date).format('DD MMM')}` : ''}
                {c.emi_index != null ? ` · EMI ${Number(c.emi_index) + 1}` : ''}
              </Text>
            </div>
          ))}
          {payments.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <Text strong style={{ fontSize: 12 }}>Payments recorded</Text>
              {payments.map((p) => (
                <div key={`p${p.id}`} style={{ padding: '4px 0', borderBottom: '1px solid #e5e7eb' }}>
                  <b>{fmt(p.amount)}</b> · EMI {Number(p.emi_index) + 1} · {dayjs(p.paid_on).format('DD MMM YYYY')}
                  {p.method ? ` · ${p.method}` : ''} <Text type="secondary">· {p.recorded_by}</Text>
                  {p.note ? <div style={{ color: '#6b7280' }}>{p.note}</div> : null}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function CommentsModal({ target, onClose }) {
  return (
    <Modal
      open={!!target}
      title={target ? <span>Payment comments — {target.name} {target.count ? <Tag>{target.count}</Tag> : null}</span> : ''}
      footer={null}
      onCancel={onClose}
      destroyOnClose
      width={560}
    >
      {target && <PaymentActivity leadId={target.leadId} />}
    </Modal>
  );
}
