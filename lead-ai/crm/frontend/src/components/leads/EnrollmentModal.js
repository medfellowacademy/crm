import React, { useState, useEffect } from 'react';
import {
  Modal, Form, InputNumber, Button, Space, Divider,
  DatePicker, Select, Tag, Row, Col, message, Typography, Badge,
} from 'antd';
import { PlusOutlined, DeleteOutlined, CheckCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

const { Text } = Typography;
const { Option } = Select;

// All monetary values are stored in INR - if entered in USD, everything is
// converted at this fixed rate before saving, so revenue analytics never
// have to deal with a mix of currencies/scales.
const USD_TO_INR = 94;

const fmtNum = (symbol) => (v) => v != null ? `${symbol} ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : '';
const parseNum = (symbol) => (v) => {
  const n = Number(String(v ?? '').replace(new RegExp(`\\${symbol}\\s?|,`, 'g'), '').trim());
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
  const [lmsModules, setLmsModules] = useState([]);
  // Forces a re-render on every field change so the summary bar (computed
  // straight from form.getFieldsValue in the render body below) stays live.
  const [, forceUpdate] = useState(0);
  // Input currency for this session only - values are always stored in INR
  // (converted at save time), so reopening an already-saved enrollment
  // always starts back on INR, showing the true stored value.
  const [currency, setCurrency] = useState('INR');
  const symbol = currency === 'USD' ? '$' : '₹';
  const fmt = fmtNum(symbol);
  const parse = parseNum(symbol);

  useEffect(() => {
    if (!open) return;
    setCurrency('INR');
    const existing  = lead || {};
    const savedEmis = safeParse(existing.emi_details, []).map(e => ({
      amount: e.amount ?? null,
      date:   e.date ? dayjs(e.date) : null,
      status: e.status || 'pending',
    }));
    const savedModules = safeParse(existing.lms_modules, []);
    setLmsModules(savedModules);

    // registration_payments is the source of truth going forward; if a lead
    // only has the legacy single registration_fees total (no payments list
    // yet), seed the list with that one value so it displays and re-saves
    // correctly without losing data.
    const savedRegPayments = safeParse(existing.registration_payments, []);
    const regPayments = savedRegPayments.length > 0
      ? savedRegPayments.map(p => ({ amount: p.amount ?? null, date: p.date ? dayjs(p.date) : null }))
      : (existing.registration_fees ? [{ amount: Number(existing.registration_fees), date: null }] : []);

    form.setFieldsValue({
      actual_revenue:         existing.actual_revenue ? Number(existing.actual_revenue) : null,
      enrolled_at:            existing.enrolled_at ? dayjs(existing.enrolled_at) : dayjs(),
      lms_status:             existing.lms_status     || 'Not Started',
      emis:                   savedEmis,
      registration_payments:  regPayments,
    });
    forceUpdate(n => n + 1);
  }, [open, lead]);

  const handleValuesChange = () => forceUpdate(n => n + 1);

  // Switching currency reinterprets whatever is currently typed in the
  // fields as the new currency's amount (converting the displayed number),
  // rather than silently changing what a same-looking number means.
  const handleCurrencyChange = (next) => {
    if (next === currency) return;
    const factor = next === 'USD' ? (1 / USD_TO_INR) : USD_TO_INR;
    const vals = form.getFieldsValue(true);
    form.setFieldsValue({
      actual_revenue: vals.actual_revenue != null ? Math.round(vals.actual_revenue * factor) : null,
      emis: (vals.emis || []).map(e => ({
        ...e,
        amount: e?.amount != null ? Math.round(e.amount * factor) : null,
      })),
      registration_payments: (vals.registration_payments || []).map(p => ({
        ...p,
        amount: p?.amount != null ? Math.round(p.amount * factor) : null,
      })),
    });
    setCurrency(next);
    forceUpdate(n => n + 1);
  };

  const handleSave = () => {
    form.validateFields().then(vals => {
      const toINR = (n) => currency === 'USD' ? Math.round(n * USD_TO_INR) : n;
      const serializedEmis = (vals.emis || []).map(e => ({
        amount: toINR(Number(e?.amount) || 0),
        date:   e?.date ? dayjs(e.date).format('YYYY-MM-DD') : null,
        status: e?.status || 'pending',
      }));
      const serializedRegPayments = (vals.registration_payments || []).map(p => ({
        amount: toINR(Number(p?.amount) || 0),
        date:   p?.date ? dayjs(p.date).format('YYYY-MM-DD') : null,
      }));
      const registrationTotal = serializedRegPayments.reduce((s, p) => s + p.amount, 0);
      onSave({
        status:                'Enrolled',
        enrolled_at:           vals.enrolled_at ? dayjs(vals.enrolled_at).format('YYYY-MM-DD') : null,
        actual_revenue:        vals.actual_revenue != null ? toINR(vals.actual_revenue) : null,
        registration_fees:     registrationTotal,
        registration_payments: serializedRegPayments,
        emi_details:           serializedEmis,
        lms_status:            vals.lms_status || 'Not Started',
        lms_modules:           lmsModules,
      });
    }).catch(() => message.warning('Please fill in Enrollment Date and Total Course Fee'));
  };

  // Live summary values — always shown in INR regardless of input currency,
  // so the totals stay meaningful even mid-conversion.
  const allVals  = form.getFieldsValue(true);
  const toINRPreview = (n) => (n || 0) * (currency === 'USD' ? USD_TO_INR : 1);
  const total    = toINRPreview(allVals.actual_revenue);
  const reg      = (allVals.registration_payments || []).reduce((s, p) => s + toINRPreview(Number(p?.amount) || 0), 0);
  const emiTotal = (allVals.emis || []).reduce((s, e) => s + toINRPreview(Number(e?.amount) || 0), 0);
  const collected = reg + emiTotal;
  const remaining = Math.max(0, total - collected);

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

        {/* ── Enrollment Date ───────────────────────────────────────── */}
        <Form.Item name="enrolled_at" label="Enrollment Date (when the sale closed)"
          rules={[{ required: true, message: 'Enter the enrollment date' }]}>
          <DatePicker style={{ width: '100%' }} format="DD MMM YYYY" disabledDate={d => d && d.isAfter(dayjs(), 'day')} />
        </Form.Item>

        {/* ── Revenue ────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Enter fees in either currency — USD is converted to INR (× {USD_TO_INR}) on save,
            so everything is stored in one currency for accurate reporting.
          </Text>
          <Select
            value={currency}
            onChange={handleCurrencyChange}
            style={{ width: 100 }}
            options={[{ value: 'INR', label: '₹ INR' }, { value: 'USD', label: '$ USD' }]}
          />
        </div>
        <Form.Item name="actual_revenue" label={`Total Course Fee (${symbol})`}
          rules={[{ required: true, message: 'Enter total fee' }]}>
          <InputNumber
            style={{ width: '100%' }} min={0}
            formatter={fmt} parser={parse}
            placeholder={currency === 'USD' ? 'e.g. 1600' : 'e.g. 150000'}
          />
        </Form.Item>

        {/* ── Registration / Advance Paid (Form.List) ──────────────────
            Some doctors pay their advance across 2-3 installments rather
            than one lump sum, so this mirrors the EMI list below. The
            individual entries sum into registration_fees on save. */}
        <Divider orientation="left" style={{ fontSize: 13, marginBottom: 12 }}>
          Registration / Advance Paid
        </Divider>

        <Form.List name="registration_payments">
          {(fields, { add, remove }) => (
            <>
              {fields.length === 0 && (
                <div style={{ textAlign: 'center', color: '#9ca3af', padding: '4px 0 12px', fontSize: 13 }}>
                  No registration payments added yet
                </div>
              )}

              {fields.map(({ key, name }) => (
                <Row key={key} gutter={10} align="middle" style={{ marginBottom: 8 }}>
                  <Col span={10}>
                    <Form.Item name={[name, 'amount']} noStyle
                      rules={[{ required: true, message: 'Enter amount' }]}>
                      <InputNumber
                        style={{ width: '100%' }} min={0}
                        formatter={fmt} parser={parse}
                        placeholder={`Amount (${symbol})`}
                      />
                    </Form.Item>
                  </Col>

                  <Col span={11}>
                    <Form.Item name={[name, 'date']} noStyle>
                      <DatePicker style={{ width: '100%' }} placeholder="Payment date" />
                    </Form.Item>
                  </Col>

                  <Col span={3}>
                    <Button danger type="text" icon={<DeleteOutlined />}
                      onClick={() => remove(name)} />
                  </Col>
                </Row>
              ))}

              <Button
                icon={<PlusOutlined />}
                onClick={() => add({ amount: null, date: null })}
                type="dashed"
                style={{ width: '100%', marginBottom: 4 }}
              >
                Add Payment
              </Button>
            </>
          )}
        </Form.List>

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
                        formatter={fmt} parser={parse}
                        placeholder={`Amount (${symbol})`}
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
