import React, { useEffect } from 'react';
import { Modal, Form, DatePicker, Select, Input, InputNumber, Alert, message } from 'antd';
import { useMutation } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { paymentsAPI } from '../../api/api';
import { fmt } from '../../utils/finance';

export const PAYMENT_METHODS = ['UPI', 'Bank transfer', 'Cash', 'Card', 'Cheque', 'Other'];

// Records money received against one instalment (an EMI, or the registration balance).
// Receiving less than scheduled is a PART-PAYMENT: what came in is recorded, and the rest
// stays as a new pending instalment with its own expected date, so it keeps being tracked.
export default function PayEmiModal({ target, onClose, onDone }) {
  const [form] = Form.useForm();
  const received = Form.useWatch('amount', form);
  const scheduled = Number(target?.amount) || 0;
  const rest = target && received != null && Number(received) > 0 && Number(received) < scheduled - 0.005
    ? scheduled - Number(received) : 0;
  const over = target && received != null && Number(received) > scheduled + 0.005 ? Number(received) - scheduled : 0;
  const label = target?.label || 'EMI';

  useEffect(() => {
    if (!target) return;
    const due = target.dueDate && !dayjs(target.dueDate).isBefore(dayjs(), 'day') ? dayjs(target.dueDate) : null;
    form.setFieldsValue({ paid_on: dayjs(), amount: Number(target.amount) || 0, remaining_due: due, method: undefined, note: '' });
  }, [target, form]);

  const pay = useMutation({
    mutationFn: (v) => paymentsAPI.markEmiPaid(target.leadId, target.index, {
      paid_on: v.paid_on.format('YYYY-MM-DD'),
      // only send an amount when it differs from the scheduled one
      amount: Number(v.amount) !== scheduled ? Number(v.amount) : undefined,
      remaining_due_date: Number(v.amount) < scheduled - 0.005 && v.remaining_due ? v.remaining_due.format('YYYY-MM-DD') : undefined,
      method: v.method || undefined,
      note: v.note || undefined,
    }),
    onSuccess: (res) => {
      const d = res?.data;
      message.success(d?.partial ? `Part-payment recorded — ${fmt(d.remaining)} still to come` : `${label} marked as paid`);
      onDone?.();
      onClose();
    },
    onError: (e) => message.error(e?.response?.data?.detail || 'Could not record the payment'),
  });

  return (
    <Modal
      open={!!target}
      title={target ? `Mark ${label} paid — ${target.name}` : ''}
      okText={rest ? 'Record part-payment' : 'Record payment'}
      confirmLoading={pay.isPending}
      onOk={() => form.validateFields().then((v) => pay.mutate(v))}
      onCancel={onClose}
      destroyOnClose
    >
      {target && (
        <div style={{ marginBottom: 12, color: '#6b7280' }}>
          Scheduled <b style={{ color: '#111827' }}>{fmt(target.amount)}</b>
          {target.dueDate ? <> · due {dayjs(target.dueDate).format('DD MMM YYYY')}</> : null}
        </div>
      )}
      <Form form={form} layout="vertical">
        <Form.Item name="paid_on" label="Date received" rules={[{ required: true, message: 'Pick the date' }]}>
          <DatePicker style={{ width: '100%' }} format="DD MMM YYYY" disabledDate={(d) => d.isAfter(dayjs(), 'day')} />
        </Form.Item>
        <Form.Item name="amount" label="Amount received"
          extra="Enter less to record a part-payment; the rest will stay pending."
          rules={[{ required: true, message: 'Enter the amount' }, {
            validator: (_, v) => (v != null && Number(v) <= 0 ? Promise.reject(new Error('Must be more than zero')) : Promise.resolve()),
          }]}>
          <InputNumber min={0} style={{ width: '100%' }} prefix="₹"
            formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} parser={(v) => v.replace(/,/g, '')} />
        </Form.Item>
        {rest > 0 && (
          <>
            <Alert type="info" showIcon style={{ marginBottom: 12 }}
              message={`${fmt(rest)} will stay pending`}
              description="It becomes its own pending instalment, so it still shows as due and, if the date passes, as overdue." />
            <Form.Item name="remaining_due" label="Rest expected by"
              rules={[{ required: true, message: 'When will the rest come?' }]}>
              <DatePicker style={{ width: '100%' }} format="DD MMM YYYY" disabledDate={(d) => d.isBefore(dayjs(), 'day')} />
            </Form.Item>
          </>
        )}
        {over > 0 && (
          <Alert type="warning" showIcon style={{ marginBottom: 12 }}
            message={`${fmt(over)} more than scheduled`}
            description="The extra is recorded on this instalment, and the student's balance goes down by the full amount." />
        )}
        <Form.Item name="method" label="Payment method">
          <Select allowClear placeholder="Optional" options={PAYMENT_METHODS.map((m) => ({ value: m, label: m }))} />
        </Form.Item>
        <Form.Item name="note" label="Note (reference / transaction id)">
          <Input.TextArea rows={2} maxLength={500} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
