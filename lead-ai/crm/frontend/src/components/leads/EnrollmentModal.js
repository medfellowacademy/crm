import React, { useState, useEffect } from 'react';
import {
  Modal, Form, InputNumber, Button, Space, Divider,
  DatePicker, Select, Tag, Row, Col, message, Typography,
} from 'antd';
import { PlusOutlined, DeleteOutlined, CheckCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

const { Text } = Typography;
const fmt = (v) => `₹ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
const parse = (v) => Number(String(v).replace(/₹\s?|(,*)/g, ''));

const EnrollmentModal = ({ open, lead, onSave, onCancel, loading }) => {
  const [form] = Form.useForm();
  const [emis, setEmis] = useState([]);
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    if (!open) return;
    const existing = lead || {};
    const savedEmis = Array.isArray(existing.emi_details)
      ? existing.emi_details.map(e => ({
          ...e,
          date: e.date ? dayjs(e.date) : null,
        }))
      : [];
    setEmis(savedEmis);
    form.setFieldsValue({
      actual_revenue:   existing.actual_revenue   || null,
      registration_fees: existing.registration_fees || null,
    });
    recalc(existing.actual_revenue || 0, existing.registration_fees || 0, savedEmis);
  }, [open, lead]);

  const recalc = (total, reg, emiList) => {
    const paid = (reg || 0) + (emiList || emis).reduce((s, e) => s + (Number(e.amount) || 0), 0);
    setRemaining(Math.max(0, (total || 0) - paid));
  };

  const handleValuesChange = (_, all) => {
    recalc(all.actual_revenue || 0, all.registration_fees || 0, emis);
  };

  const addEmi = () => setEmis(prev => [...prev, { amount: null, date: null, status: 'pending' }]);

  const updateEmi = (idx, field, val) => {
    const updated = emis.map((e, i) => i === idx ? { ...e, [field]: val } : e);
    setEmis(updated);
    const vals = form.getFieldsValue();
    recalc(vals.actual_revenue || 0, vals.registration_fees || 0, updated);
  };

  const removeEmi = (idx) => {
    const updated = emis.filter((_, i) => i !== idx);
    setEmis(updated);
    const vals = form.getFieldsValue();
    recalc(vals.actual_revenue || 0, vals.registration_fees || 0, updated);
  };

  const handleSave = () => {
    form.validateFields().then(vals => {
      const serializedEmis = emis.map(e => ({
        amount: Number(e.amount) || 0,
        date:   e.date ? dayjs(e.date).format('YYYY-MM-DD') : null,
        status: e.status || 'pending',
      }));
      onSave({
        status:             'Enrolled',
        actual_revenue:     vals.actual_revenue    || null,
        registration_fees:  vals.registration_fees || null,
        emi_details:        serializedEmis,
      });
    }).catch(() => message.warning('Please fill in all required fields'));
  };

  const total    = form.getFieldValue('actual_revenue')    || 0;
  const regFees  = form.getFieldValue('registration_fees') || 0;
  const emiTotal = emis.reduce((s, e) => s + (Number(e.amount) || 0), 0);
  const collected = regFees + emiTotal;

  return (
    <Modal
      title={
        <Space>
          <CheckCircleOutlined style={{ color: '#10b981', fontSize: 18 }} />
          <span>Enrollment Details — {lead?.full_name}</span>
        </Space>
      }
      open={open}
      onCancel={onCancel}
      width={580}
      footer={
        <Space>
          <Button onClick={onCancel}>Cancel</Button>
          <Button type="primary" loading={loading} onClick={handleSave}
            style={{ background: '#10b981', borderColor: '#10b981' }}>
            Confirm Enrollment
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" onValuesChange={handleValuesChange}>

        {/* Revenue Summary Bar */}
        <div style={{
          background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8,
          padding: '12px 16px', marginBottom: 20,
          display: 'flex', gap: 24, flexWrap: 'wrap',
        }}>
          <div>
            <div style={{ fontSize: 11, color: '#6b7280' }}>Total Fee</div>
            <div style={{ fontWeight: 700, color: '#059669' }}>₹{Number(total).toLocaleString('en-IN')}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: '#6b7280' }}>Collected</div>
            <div style={{ fontWeight: 700, color: '#2563eb' }}>₹{Number(collected).toLocaleString('en-IN')}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: '#6b7280' }}>Remaining</div>
            <div style={{ fontWeight: 700, color: remaining > 0 ? '#dc2626' : '#059669' }}>
              ₹{Number(remaining).toLocaleString('en-IN')}
            </div>
          </div>
        </div>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="actual_revenue" label="Total Course Fee (₹)"
              rules={[{ required: true, message: 'Enter total fee' }]}>
              <InputNumber style={{ width: '100%' }} min={0} formatter={fmt} parser={parse}
                placeholder="e.g. 150000" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="registration_fees" label="Registration / Advance Paid (₹)"
              rules={[{ required: true, message: 'Enter registration fees' }]}>
              <InputNumber style={{ width: '100%' }} min={0} formatter={fmt} parser={parse}
                placeholder="e.g. 50000" />
            </Form.Item>
          </Col>
        </Row>

        <Divider orientation="left" style={{ fontSize: 13 }}>
          EMI Schedule&nbsp;<Text type="secondary" style={{ fontSize: 12 }}>({emis.length} instalment{emis.length !== 1 ? 's' : ''})</Text>
        </Divider>

        {emis.length === 0 && (
          <div style={{ textAlign: 'center', color: '#9ca3af', padding: '8px 0 12px', fontSize: 13 }}>
            No EMIs — full payment collected upfront
          </div>
        )}

        {emis.map((emi, idx) => (
          <Row key={idx} gutter={10} align="middle" style={{ marginBottom: 10 }}>
            <Col span={7}>
              <InputNumber
                style={{ width: '100%' }} min={0} formatter={fmt} parser={parse}
                placeholder="Amount"
                value={emi.amount}
                onChange={v => updateEmi(idx, 'amount', v)}
              />
            </Col>
            <Col span={8}>
              <DatePicker
                style={{ width: '100%' }}
                placeholder="Due date"
                value={emi.date ? dayjs(emi.date) : null}
                onChange={d => updateEmi(idx, 'date', d)}
              />
            </Col>
            <Col span={6}>
              <Select
                value={emi.status}
                onChange={v => updateEmi(idx, 'status', v)}
                style={{ width: '100%' }}
              >
                <Select.Option value="pending"><Tag color="orange">Pending</Tag></Select.Option>
                <Select.Option value="paid"><Tag color="green">Paid</Tag></Select.Option>
                <Select.Option value="overdue"><Tag color="red">Overdue</Tag></Select.Option>
              </Select>
            </Col>
            <Col span={3}>
              <Button danger type="text" icon={<DeleteOutlined />}
                onClick={() => removeEmi(idx)} />
            </Col>
          </Row>
        ))}

        <Button icon={<PlusOutlined />} onClick={addEmi} style={{ width: '100%', marginTop: 4 }}
          type="dashed">
          Add EMI
        </Button>

      </Form>
    </Modal>
  );
};

export default EnrollmentModal;
