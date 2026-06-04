import React, { useState, useEffect } from 'react';
import {
  Modal, Form, InputNumber, Button, Space, Divider,
  DatePicker, Select, Tag, Row, Col, message, Typography, Badge,
} from 'antd';
import { PlusOutlined, DeleteOutlined, CheckCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

const { Text } = Typography;
const { Option } = Select;

const fmt   = v => `₹ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
const parse = v => Number(String(v).replace(/₹\s?|(,*)/g, ''));

// All 12 LMS module options
const MODULE_OPTIONS = ['M1','M2','M3','M4','M5','M6','M7','M8','M9','M10','M11','M12'];
const LMS_STATUS_OPTIONS = [
  { value: 'Not Started', color: 'default'    },
  { value: 'Active',      color: 'processing' },
  { value: 'On Hold',     color: 'warning'    },
  { value: 'Completed',   color: 'success'    },
];

// Safe JSON parse for emi_details / lms_modules which may arrive as a string
const safeParse = (val, fallback = []) => {
  if (!val) return fallback;
  if (Array.isArray(val)) return val;
  try { return JSON.parse(val); } catch { return fallback; }
};

const EnrollmentModal = ({ open, lead, onSave, onCancel, loading }) => {
  const [form]       = Form.useForm();
  const [emis,       setEmis]       = useState([]);
  const [remaining,  setRemaining]  = useState(0);
  const [lmsModules, setLmsModules] = useState([]);

  useEffect(() => {
    if (!open) return;
    const existing     = lead || {};
    const savedEmis    = safeParse(existing.emi_details, []).map(e => ({
      ...e,
      date: e.date ? dayjs(e.date) : null,
    }));
    const savedModules = safeParse(existing.lms_modules, []);

    setEmis(savedModules.length ? savedEmis : savedEmis);
    setLmsModules(savedModules);

    form.setFieldsValue({
      actual_revenue:    existing.actual_revenue    || null,
      registration_fees: existing.registration_fees || null,
      lms_status:        existing.lms_status        || 'Not Started',
    });
    recalc(existing.actual_revenue || 0, existing.registration_fees || 0, savedEmis);
  }, [open, lead]);

  const recalc = (total, reg, emiList) => {
    const emiTotal = (emiList || emis).reduce((s, e) => s + (Number(e.amount) || 0), 0);
    setRemaining(Math.max(0, (total || 0) - ((reg || 0) + emiTotal)));
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
        status:            'Enrolled',
        actual_revenue:    vals.actual_revenue    || null,
        registration_fees: vals.registration_fees || null,
        emi_details:       serializedEmis,
        lms_status:        vals.lms_status        || 'Not Started',
        lms_modules:       lmsModules,
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
      width={600}
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
          {[
            { label: 'Total Fee',   val: total,      color: '#059669' },
            { label: 'Collected',   val: collected,  color: '#2563eb' },
            { label: 'Remaining',   val: remaining,  color: remaining > 0 ? '#dc2626' : '#059669' },
          ].map(({ label, val, color }) => (
            <div key={label}>
              <div style={{ fontSize: 11, color: '#6b7280' }}>{label}</div>
              <div style={{ fontWeight: 700, color }}>₹{Number(val).toLocaleString('en-IN')}</div>
            </div>
          ))}
        </div>

        {/* Revenue Fields */}
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

        {/* EMI Schedule */}
        <Divider orientation="left" style={{ fontSize: 13 }}>
          EMI Schedule&nbsp;
          <Text type="secondary" style={{ fontSize: 12 }}>
            ({emis.length} instalment{emis.length !== 1 ? 's' : ''})
          </Text>
        </Divider>

        {emis.length === 0 && (
          <div style={{ textAlign: 'center', color: '#9ca3af', padding: '4px 0 10px', fontSize: 13 }}>
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
                value={emi.status || 'pending'}
                onChange={v => updateEmi(idx, 'status', v)}
                style={{ width: '100%' }}
              >
                <Option value="pending"><Tag color="orange">Pending</Tag></Option>
                <Option value="paid"><Tag color="green">Paid</Tag></Option>
                <Option value="overdue"><Tag color="red">Overdue</Tag></Option>
              </Select>
            </Col>
            <Col span={3}>
              <Button danger type="text" icon={<DeleteOutlined />}
                onClick={() => removeEmi(idx)} />
            </Col>
          </Row>
        ))}

        <Button icon={<PlusOutlined />} onClick={addEmi}
          style={{ width: '100%', marginBottom: 8 }} type="dashed">
          Add EMI
        </Button>

        {/* LMS Section */}
        <Divider orientation="left" style={{ fontSize: 13 }}>LMS Access</Divider>

        <Row gutter={16}>
          <Col span={10}>
            <Form.Item name="lms_status" label="LMS Status" initialValue="Not Started">
              <Select>
                {LMS_STATUS_OPTIONS.map(o => (
                  <Option key={o.value} value={o.value}>
                    <Badge status={o.color} text={o.value} />
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={14}>
            <Form.Item label="Modules Unlocked">
              <Select
                mode="multiple"
                placeholder="Select modules (M1, M2 …)"
                value={lmsModules}
                onChange={setLmsModules}
                maxTagCount="responsive"
              >
                {MODULE_OPTIONS.map(m => (
                  <Option key={m} value={m}>{m}</Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
        </Row>

      </Form>
    </Modal>
  );
};

export default EnrollmentModal;
