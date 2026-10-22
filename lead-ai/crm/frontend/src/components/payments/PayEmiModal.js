import React, { useEffect } from 'react';
import { Modal, Form, DatePicker, Select, Input, InputNumber, message } from 'antd';
import { useMutation } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { paymentsAPI } from '../../api/api';
import { fmt } from '../../utils/finance';

export const PAYMENT_METHODS = ['UPI', 'Bank transfer', 'Cash', 'Card', 'Cheque', 'Other'];

// Records one EMI as paid: updates the schedule on the lead AND writes an audit
// row (who / when / how) to the payment ledger.
export default function PayEmiModal({ target, onClose, onDone }) {
  const [form] = Form.useForm();

  useEffect(() => {
    if (target) form.setFieldsValue({ paid_on: dayjs(), amount: Number(target.amount) || 0, method: undefined, note: '' });
  }, [target, form]);

  const pay = useMutation({
    mutationFn: (v) => paymentsAPI.markEmiPaid(target.leadId, target.index, {
      paid_on: v.paid_on.format('YYYY-MM-DD'),
      // only send an amount when it differs from the scheduled EMI
      amount: Number(v.amount) !== Number(target.amount) ? Number(v.amount) : undefined,
      method: v.method || undefined,
      note: v.note || undefined,
    }),
    onSuccess: () => {
      message.success('EMI marked as paid');
      onDone?.();
      onClose();
    },
    onError: (e) => message.error(e?.response?.data?.detail || 'Could not record the payment'),
  });

  return (
    <Modal
      open={!!target}
      title={target ? `Mark EMI ${target.index + 1} paid — ${target.name}` : ''}
      okText="Record payment"
      confirmLoading={pay.isPending}
      onOk={() => form.validateFields().then((v) => pay.mutate(v))}
      onCancel={onClose}
      destroyOnClose
    >
      {target && (
        <div style={{ marginBottom: 12, color: '#6b7280' }}>
          Amount <b style={{ color: '#111827' }}>{fmt(target.amount)}</b>
          {target.dueDate ? <> · due {dayjs(target.dueDate).format('DD MMM YYYY')}</> : null}
        </div>
      )}
      <Form form={form} layout="vertical">
        <Form.Item name="paid_on" label="Date received" rules={[{ required: true, message: 'Pick the date' }]}>
          <DatePicker style={{ width: '100%' }} format="DD MMM YYYY" disabledDate={(d) => d.isAfter(dayjs(), 'day')} />
        </Form.Item>
        <Form.Item name="amount" label="Amount actually received"
          extra="Change this if the payment was more or less than the scheduled EMI."
          rules={[{ required: true, message: 'Enter the amount' }]}>
          <InputNumber min={0} style={{ width: '100%' }} prefix="₹"
            formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} parser={(v) => v.replace(/,/g, '')} />
        </Form.Item>
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
