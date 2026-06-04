import React, { useState, useEffect } from 'react';
import {
  Modal, Form, InputNumber, Button, Space, Divider,
  DatePicker, Select, Tag, Row, Col, message, Typography, Badge,
} from 'antd';
import { PlusOutlined, DeleteOutlined, CheckCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

const { Text } = Typography;
const { Option } = Select;

const fmtNum = v => v != null ? `₹ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : '';
const parseNum = v => {
  const n = Number(String(v ?? '').replace(/₹\s?|,/g, '').trim());
  return isNaN(n) ? 0 : n;
};

const MODULE_OPTIONS    = ['M1','M2','M3','M4','M5','M6','M7','M8','M9','M10','M11','M12'];
const LMS_STATUS_OPTIONS = [
  { value: 'Not Started', color: 'default'    },
  { value: 'Active',      color: 'processing' },
  { value: 'On Hold',     color: 'warning'    },
  { value: 'Completed',   color: 'success'    },
];

const safeParse = (val, fallback = []) => {
  if (!val) return fallback;
  if (Array.isArray(val)) return val;
  try { return JSON.parse(val); } catch { return fallback; }
};

const EnrollmentModal = ({ open, lead, onSave, onCancel, loading }) => {
  const [form] = Form.useForm();
  const [remaining,  setRemaining]  = useState(0);
  const [lmsModules, setLmsModules] = useState([]);

  // Recalculate remaining from current form values on every change
  const recalcFromForm = (allValues) => {
    const total    = allValues.actual_revenue    || 0;
    const reg      = allValues.registration_fees || 0;
    const emiTotal = (allValues.emis || []).reduce((s, e) => s + (Number(e?.amount) || 0), 0);
    setRemaining(Math.max(0, total - reg - emiTotal));
  };

  useEffect(() => {
    if (!open) return;
    const existing  = lead || {};
    const savedEmis = safeParse(existing.emi_details, []).map(e => ({
      amount: e.amount ?? null,
      date:   e.date ? dayjs(e.date) : null,
      status: e.status || 'pending',
    }));
    const savedModules = safeParse(existing.lms_modules, []);
    setLmsModules(savedModules);

    form.setFieldsValue({
      actual_revenue:    existing.actual_revenue    ?? null,
      registration_fees: existing.registration_fees ?? null,
      lms_status:        existing.lms_status        || 'Not Started',
      emis:              savedEmis,
    });

    recalcFromForm({
      actual_revenue:    existing.actual_revenue    || 0,
      registration_fees: existing.registration_fees || 0,
      emis:              savedEmis,
    });
  }, [open, lead]);

  const handleValuesChange = (_, allValues) => recalcFromForm(allValues);

  const handleSave = () => {
    form.validateFields().then(vals => {
      const serializedEmis = (vals.emis || []).map(e => ({
        amount: Number(e?.amount) || 0,
        date:   e?.date ? dayjs(e.date).format('YYYY-MM-DD') : null,
        status: e?.status || 'pending',
      }));
      onSave({
        status:            'Enrolled',
        actual_revenue:    vals.actual_revenue    || null,
        registration_fees: vals.registration_fees || null,
        emi_details:       serializedEmis,
        lms_status:        vals.lms_status        || 'Not Started',
        lms_modules:       lmsModules,
      });
    }).catch(() => message.warning('Please fill in Total Course Fee and Registration Fees'));
  };

  // Live summary values — read from form
  const allVals  = form.getFieldsValue(true);
  const total    = allVals.actual_revenue    || 0;
  const reg      = allVals.registration_fees || 0;
  const emiTotal = (allVals.emis || []).reduce((s, e) => s + (Number(e?.amount) || 0), 0);
  const collected = reg + emiTotal;

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
      width={640}
      destroyOnClose
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
      <Form
        form={form}
        layout="vertical"
        onValuesChange={handleValuesChange}
      >
        {/* ── Summary Bar ────────────────────────────────────────────── */}
        <div style={{
          background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8,
          padding: '12px 16px', marginBottom: 20,
          display: 'flex', gap: 24, flexWrap: 'wrap',
        }}>
          {[
            { label: 'Total Fee',  val: total,     color: '#059669' },
            { label: 'Collected',  val: collected, color: '#2563eb' },
            { label: 'Remaining',  val: remaining, color: remaining > 0 ? '#dc2626' : '#059669' },
          ].map(({ label, val, color }) => (
            <div key={label}>
              <div style={{ fontSize: 11, color: '#6b7280' }}>{label}</div>
              <div style={{ fontWeight: 700, color }}>₹{Number(val).toLocaleString('en-IN')}</div>
            </div>
          ))}
        </div>

        {/* ── Revenue ────────────────────────────────────────────────── */}
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="actual_revenue" label="Total Course Fee (₹)"
              rules={[{ required: true, message: 'Enter total fee' }]}>
              <InputNumber
                style={{ width: '100%' }} min={0}
                formatter={fmtNum} parser={parseNum}
                placeholder="e.g. 150000"
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="registration_fees" label="Registration / Advance Paid (₹)"
              rules={[{ required: true, message: 'Enter registration fees' }]}>
              <InputNumber
                style={{ width: '100%' }} min={0}
                formatter={fmtNum} parser={parseNum}
                placeholder="e.g. 50000"
              />
            </Form.Item>
          </Col>
        </Row>

        {/* ── EMI Schedule (Form.List) ───────────────────────────────── */}
        <Divider orientation="left" style={{ fontSize: 13, marginBottom: 12 }}>
          EMI Schedule
        </Divider>

        <Form.List name="emis">
          {(fields, { add, remove }) => (
            <>
              {fields.length === 0 && (
                <div style={{ textAlign: 'center', color: '#9ca3af', padding: '4px 0 12px', fontSize: 13 }}>
                  No EMIs — full payment collected upfront
                </div>
              )}

              {fields.map(({ key, name }) => (
                <Row key={key} gutter={10} align="middle" style={{ marginBottom: 8 }}>
                  {/* Amount */}
                  <Col span={7}>
                    <Form.Item name={[name, 'amount']} noStyle>
                      <InputNumber
                        style={{ width: '100%' }} min={0}
                        formatter={fmtNum} parser={parseNum}
                        placeholder="Amount (₹)"
                      />
                    </Form.Item>
                  </Col>

                  {/* Due Date */}
                  <Col span={8}>
                    <Form.Item name={[name, 'date']} noStyle>
                      <DatePicker style={{ width: '100%' }} placeholder="Due date" />
                    </Form.Item>
                  </Col>

                  {/* Status */}
                  <Col span={6}>
                    <Form.Item name={[name, 'status']} initialValue="pending" noStyle>
                      <Select style={{ width: '100%' }}>
                        <Option value="pending"><Tag color="orange">Pending</Tag></Option>
                        <Option value="paid"><Tag color="green">Paid</Tag></Option>
                        <Option value="overdue"><Tag color="red">Overdue</Tag></Option>
                      </Select>
                    </Form.Item>
                  </Col>

                  {/* Remove */}
                  <Col span={3}>
                    <Button danger type="text" icon={<DeleteOutlined />}
                      onClick={() => remove(name)} />
                  </Col>
                </Row>
              ))}

              <Button
                icon={<PlusOutlined />}
                onClick={() => add({ amount: null, date: null, status: 'pending' })}
                type="dashed"
                style={{ width: '100%', marginBottom: 4 }}
              >
                Add EMI
              </Button>
            </>
          )}
        </Form.List>

        {/* ── LMS ───────────────────────────────────────────────────── */}
        <Divider orientation="left" style={{ fontSize: 13, marginTop: 16 }}>LMS Access</Divider>

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
