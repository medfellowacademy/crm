import React, { useEffect } from 'react';
import { Modal, Form, DatePicker, Select, Input, InputNumber, Alert, message } from 'antd';
import { useMutation } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { paymentsAPI } from '../../api/api';
import { financeFor, fmt } from '../../utils/finance';

export const DROP_REASONS = [
  'Financial reasons', 'Personal / family reasons', 'Joined another course', 'Not satisfied with the course',
  'Not eligible / documents issue', 'Unreachable / stopped responding', 'Other',
];

// Marks an enrolled student as Dropped: the lead's status becomes "Dropped", their
// remaining (unpaid) instalments are cancelled, and why / when / refund are recorded.
export default function DropStudentModal({ lead, onClose, onDone }) {
  const [form] = Form.useForm();
  const f = lead ? financeFor(lead) : null;
  const open = lead ? f.emis.filter((e) => e.status !== 'paid' && e.status !== 'cancelled') : [];
  const openAmount = open.reduce((s, e) => s + (Number(e.amount) || 0), 0);

  useEffect(() => {
    if (lead) form.setFieldsValue({ reason: undefined, note: '', dropped_on: dayjs(), refund_amount: 0 });
  }, [lead, form]);

  const drop = useMutation({
    mutationFn: (v) => paymentsAPI.drop(lead.lead_id, {
      reason: v.reason,
      note: v.note || undefined,
      dropped_on: v.dropped_on.format('YYYY-MM-DD'),
      refund_amount: Number(v.refund_amount) || 0,
    }),
    onSuccess: () => {
      message.success(`${lead.full_name} marked as dropped`);
      onDone?.();
      onClose();
    },
    onError: (e) => message.error(e?.response?.data?.detail || 'Could not mark the student as dropped'),
  });

  return (
    <Modal
      open={!!lead}
      title={lead ? `Mark ${lead.full_name} as dropped` : ''}
      okText="Mark as dropped" okButtonProps={{ danger: true }}
      confirmLoading={drop.isPending}
      onOk={() => form.validateFields().then((v) => drop.mutate(v))}
      onCancel={onClose}
      destroyOnClose
    >
      {lead && (
        <Alert
          type="warning" showIcon style={{ marginBottom: 16 }}
          message="This changes their status to Dropped"
          description={(
            <div>
              <div>They leave the enrolled list and stop counting in sales and revenue reports.</div>
              <div>
                {open.length
                  ? <><b>{open.length}</b> unpaid EMI{open.length > 1 ? 's' : ''} ({fmt(openAmount)}) will be cancelled so they stop showing as overdue.</>
                  : 'They have no unpaid EMIs left to cancel.'}
              </div>
              <div>Already collected: <b>{fmt(f.collected)}</b> (stays on record). You can undo this later from the Dropped tab.</div>
            </div>
          )}
        />
      )}
      <Form form={form} layout="vertical">
        <Form.Item name="reason" label="Reason for dropping" rules={[{ required: true, message: 'Pick a reason' }]}>
          <Select placeholder="Select a reason" options={DROP_REASONS.map((r) => ({ value: r, label: r }))} />
        </Form.Item>
        <Form.Item name="dropped_on" label="Date dropped" rules={[{ required: true, message: 'Pick the date' }]}>
          <DatePicker style={{ width: '100%' }} format="DD MMM YYYY" disabledDate={(d) => d.isAfter(dayjs(), 'day')} />
        </Form.Item>
        <Form.Item
          name="refund_amount" label="Refund given (if any)"
          extra={lead ? `Money returned to the student. Can't be more than the ${fmt(f.collected)} collected.` : ''}
        >
          <InputNumber min={0} max={lead ? f.collected : undefined} style={{ width: '100%' }} prefix="₹"
            formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} parser={(v) => v.replace(/,/g, '')} />
        </Form.Item>
        <Form.Item name="note" label="Note (optional)">
          <Input.TextArea rows={2} maxLength={500} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
