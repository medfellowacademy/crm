import React, { useState, useEffect } from 'react';
import {
  Modal, Form, InputNumber, Button, Space, Divider,
  DatePicker, Select, Row, Col, message, Typography, Badge, Alert,
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
const inr = (n) => `₹${Math.round(Number(n) || 0).toLocaleString('en-IN')}`;
const ymd = (d) => dayjs(d).format('YYYY-MM-DD');

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

// One instalment (an EMI, or the part of the registration still to come) as a form row.
// The original object rides along in `_orig` so that fields written elsewhere (who received
// it, how, the exact amount, ...) survive an edit instead of being rebuilt from three fields.
const toRow = (e) => ({
  amount: e.amount ?? null,
  date: e.date ? dayjs(e.date) : null,
  status: e.status === 'paid' ? 'paid' : 'pending',
  paid_on: e.paid_date ? dayjs(e.paid_date) : null,
  _orig: e,
});

const PAID_FIELDS = ['paid_date', 'paid_amount', 'method', 'paid_recorded_by'];

const serializeRow = (r, toINR, kind) => {
  const orig = r?._orig || {};
  const amount = toINR(Number(r?.amount) || 0);
  const out = { ...orig, amount, date: r?.date ? ymd(r.date) : null };
  if (kind) out.kind = kind;
  if (r?.status === 'paid') {
    out.status = 'paid';
    out.paid_date = r.paid_on ? ymd(r.paid_on) : (orig.paid_date || dayjs().format('YYYY-MM-DD'));
    // an edited scheduled amount no longer matches a previously recorded part-/over-payment
    if (orig.paid_amount != null && Number(orig.amount) !== amount) delete out.paid_amount;
  } else {
    out.status = 'pending';
    PAID_FIELDS.forEach((k) => delete out[k]);
  }
  return out;
};

const EnrollmentModal = ({ open, lead, onSave, onCancel, loading }) => {
  const [form] = Form.useForm();
  const [lmsModules, setLmsModules] = useState([]);
  // instalments cancelled because the student dropped: not editable here, kept as they are
  const [cancelled, setCancelled] = useState([]);
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
  const isEdit = lead?.status === 'Enrolled';

  useEffect(() => {
    if (!open) return;
    setCurrency('INR');
    const existing = lead || {};
    const saved = safeParse(existing.emi_details, []).filter((e) => e && typeof e === 'object');
    setCancelled(saved.filter((e) => e.status === 'cancelled'));
    const live = saved.filter((e) => e.status !== 'cancelled');
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
      reg_balances:           live.filter((e) => e.kind === 'registration').map(toRow),
      emis:                   live.filter((e) => e.kind !== 'registration').map(toRow),
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
    const scale = (list) => (list || []).map(e => ({ ...e, amount: e?.amount != null ? Math.round(e.amount * factor) : null }));
    form.setFieldsValue({
      actual_revenue: vals.actual_revenue != null ? Math.round(vals.actual_revenue * factor) : null,
      emis: scale(vals.emis),
      reg_balances: scale(vals.reg_balances),
      registration_payments: scale(vals.registration_payments),
    });
    setCurrency(next);
    forceUpdate(n => n + 1);
  };

  const toINRPreview = (n) => (n || 0) * (currency === 'USD' ? USD_TO_INR : 1);

  // ── Live summary, always in INR. Only money that has actually been RECEIVED counts as collected:
  //    registration payments, plus instalments marked Paid. Pending instalments are "to come". ──
  const allVals = form.getFieldsValue(true);
  const instalments = [...(allVals.reg_balances || []), ...(allVals.emis || [])].filter(Boolean);
  const receivedOf = (r) => {
    const amt = toINRPreview(Number(r.amount) || 0);
    const orig = r._orig;
    return orig && orig.paid_amount != null && Number(orig.amount) === amt ? Number(orig.paid_amount) : amt;
  };
  const total      = toINRPreview(allVals.actual_revenue);
  const regPaid    = (allVals.registration_payments || []).reduce((s, p) => s + toINRPreview(Number(p?.amount) || 0), 0);
  const instPaid   = instalments.filter((r) => r.status === 'paid').reduce((s, r) => s + receivedOf(r), 0);
  const toCome     = instalments.filter((r) => r.status !== 'paid').reduce((s, r) => s + toINRPreview(Number(r.amount) || 0), 0);
  const collected  = regPaid + instPaid;
  const unscheduled   = total > 0 ? Math.max(0, total - collected - toCome) : 0;
  const overScheduled = total > 0 ? Math.max(0, collected + toCome - total) : 0;
  const remaining  = Math.max(0, total - collected);

  // Adds an EMI row for the part of the fee that is in no instalment (the user then picks its due date).
  const scheduleRemaining = () => {
    const vals = form.getFieldsValue(true);
    const amount = currency === 'USD' ? Math.round(unscheduled / USD_TO_INR) : Math.round(unscheduled);
    form.setFieldsValue({ emis: [...(vals.emis || []), { amount, date: null, status: 'pending' }] });
    forceUpdate(n => n + 1);
  };

  const handleSave = () => {
    form.validateFields().then(vals => {
      const toINR = (n) => currency === 'USD' ? Math.round(n * USD_TO_INR) : n;
      const serializedRegPayments = (vals.registration_payments || []).map(p => ({
        amount: toINR(Number(p?.amount) || 0),
        date:   p?.date ? ymd(p.date) : null,
      }));
      const registrationTotal = serializedRegPayments.reduce((s, p) => s + p.amount, 0);
      const instalmentList = [
        ...(vals.reg_balances || []).map((r) => serializeRow(r, toINR, 'registration')),
        ...(vals.emis || []).map((r) => serializeRow(r, toINR)),
        ...cancelled,
      ];
      onSave({
        status:                'Enrolled',
        enrolled_at:           vals.enrolled_at ? ymd(vals.enrolled_at) : null,
        actual_revenue:        vals.actual_revenue != null ? toINR(vals.actual_revenue) : null,
        registration_fees:     registrationTotal,
        registration_payments: serializedRegPayments,
        emi_details:           instalmentList,
        lms_status:            vals.lms_status || 'Not Started',
        lms_modules:           lmsModules,
      });
    }).catch(() => message.warning('Please fix the highlighted fields'));
  };

  const amountRules = [{ required: true, message: 'Enter the amount' }, {
    validator: (_, v) => (v != null && Number(v) <= 0 ? Promise.reject(new Error('Must be more than zero')) : Promise.resolve()),
  }];
  const dueRules = (getStatus) => [({ getFieldValue }) => ({
    validator: (_, v) => (v || getStatus(getFieldValue) === 'paid' ? Promise.resolve() : Promise.reject(new Error('Pick the due date'))),
  })];

  // One instalment row: amount, due date, Pending/Paid, delete, and "received on" once paid.
  const renderInstalments = (listName, { addLabel, emptyText, amountPlaceholder, datePlaceholder }) => (
    <Form.List name={listName}>
      {(fields, { add, remove }) => (
        <>
          {fields.length === 0 && (
            <div style={{ textAlign: 'center', color: '#9ca3af', padding: '4px 0 12px', fontSize: 13 }}>{emptyText}</div>
          )}
          {fields.map(({ key, name }) => (
            <div key={key} style={{ marginBottom: 8 }}>
              <Form.Item name={[name, '_orig']} hidden><input /></Form.Item>
              <Row gutter={10} align="top">
                <Col span={7}>
                  <Form.Item name={[name, 'amount']} style={{ marginBottom: 0 }} rules={amountRules}>
                    <InputNumber style={{ width: '100%' }} min={0} formatter={fmt} parser={parse} placeholder={amountPlaceholder} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name={[name, 'date']} style={{ marginBottom: 0 }}
                    rules={dueRules((gf) => gf([listName, name, 'status']))}>
                    <DatePicker style={{ width: '100%' }} placeholder={datePlaceholder} />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item name={[name, 'status']} initialValue="pending" style={{ marginBottom: 0 }}>
                    <Select style={{ width: '100%' }}>
                      <Option value="pending"><Badge status="warning" text="Pending" /></Option>
                      <Option value="paid"><Badge status="success" text="Paid" /></Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={3}>
                  <Button danger type="text" icon={<DeleteOutlined />} onClick={() => remove(name)} />
                </Col>
              </Row>
              <Form.Item noStyle shouldUpdate={(a, b) => a?.[listName]?.[name]?.status !== b?.[listName]?.[name]?.status}>
                {({ getFieldValue }) => getFieldValue([listName, name, 'status']) === 'paid' && (
                  <Row gutter={10} style={{ marginTop: 6 }}>
                    <Col span={7}><Text type="secondary" style={{ fontSize: 12, lineHeight: '32px' }}>Received on</Text></Col>
                    <Col span={8}>
                      <Form.Item name={[name, 'paid_on']} style={{ marginBottom: 0 }}>
                        <DatePicker style={{ width: '100%' }} placeholder="Date received" disabledDate={(d) => d && d.isAfter(dayjs(), 'day')} />
                      </Form.Item>
                    </Col>
                  </Row>
                )}
              </Form.Item>
            </div>
          ))}
          <Button icon={<PlusOutlined />} onClick={() => add({ amount: null, date: null, status: 'pending' })}
            type="dashed" style={{ width: '100%', marginBottom: 4 }}>
            {addLabel}
          </Button>
        </>
      )}
    </Form.List>
  );

  return (
    <Modal
      title={
        <Space>
          <CheckCircleOutlined style={{ color: '#10b981', fontSize: 18 }} />
          <span>{isEdit ? 'Payment Details' : 'Enrollment Details'} — {lead?.full_name}</span>
        </Space>
      }
      open={open}
      onCancel={onCancel}
      width={680}
      destroyOnClose
      footer={
        <Space>
          <Button onClick={onCancel}>Cancel</Button>
          <Button type="primary" loading={loading} onClick={handleSave}
            style={{ background: '#10b981', borderColor: '#10b981' }}>
            {isEdit ? 'Save payment details' : 'Confirm Enrollment'}
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" onValuesChange={handleValuesChange}>
        {/* ── Summary Bar: only money actually received counts as collected ───── */}
        <div style={{
          background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8,
          padding: '12px 16px', marginBottom: 12,
          display: 'flex', gap: 22, flexWrap: 'wrap',
        }}>
          {[
            { label: 'Total fee',              val: total,       color: '#059669' },
            { label: 'Received',               val: collected,   color: '#2563eb' },
            { label: 'Scheduled to come',      val: toCome,      color: '#d97706' },
            { label: 'Not scheduled yet',      val: unscheduled, color: unscheduled > 0 ? '#dc2626' : '#6b7280' },
            { label: 'Remaining to collect',   val: remaining,   color: remaining > 0 ? '#dc2626' : '#059669', bold: true },
          ].map(({ label, val, color, bold }) => (
            <div key={label}>
              <div style={{ fontSize: 11, color: '#6b7280' }}>{label}</div>
              <div style={{ fontWeight: bold ? 800 : 700, color }}>{inr(val)}</div>
            </div>
          ))}
        </div>

        {unscheduled > 0.5 && (
          <Alert
            type="warning" showIcon style={{ marginBottom: 12 }}
            message={`${inr(unscheduled)} of the fee is not in any instalment yet`}
            description="It has no due date, so it will never show as due or overdue. Schedule it, or add it as registration balance below."
            action={<Button size="small" onClick={scheduleRemaining}>Schedule it</Button>}
          />
        )}
        {overScheduled > 0.5 && (
          <Alert
            type="error" showIcon style={{ marginBottom: 12 }}
            message={`The payments add up to ${inr(overScheduled)} more than the total fee`}
            description="Check the amounts: received plus scheduled should not be more than the course fee."
          />
        )}

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

        {/* ── Registration / Advance ─────────────────────────────────── */}
        <Divider orientation="left" style={{ fontSize: 13, marginBottom: 12 }}>
          Registration / Advance — received
        </Divider>
        <Form.List name="registration_payments">
          {(fields, { add, remove }) => (
            <>
              {fields.length === 0 && (
                <div style={{ textAlign: 'center', color: '#9ca3af', padding: '4px 0 12px', fontSize: 13 }}>
                  No registration payments received yet
                </div>
              )}
              {fields.map(({ key, name }) => (
                <Row key={key} gutter={10} align="middle" style={{ marginBottom: 8 }}>
                  <Col span={10}>
                    <Form.Item name={[name, 'amount']} noStyle rules={amountRules}>
                      <InputNumber style={{ width: '100%' }} min={0} formatter={fmt} parser={parse} placeholder={`Amount received (${symbol})`} />
                    </Form.Item>
                  </Col>
                  <Col span={11}>
                    <Form.Item name={[name, 'date']} noStyle>
                      <DatePicker style={{ width: '100%' }} placeholder="Date received" />
                    </Form.Item>
                  </Col>
                  <Col span={3}>
                    <Button danger type="text" icon={<DeleteOutlined />} onClick={() => remove(name)} />
                  </Col>
                </Row>
              ))}
              <Button icon={<PlusOutlined />} onClick={() => add({ amount: null, date: null })}
                type="dashed" style={{ width: '100%', marginBottom: 4 }}>
                Add payment received
              </Button>
            </>
          )}
        </Form.List>

        <Divider orientation="left" style={{ fontSize: 13, margin: '16px 0 4px' }}>
          Registration balance — still to come
        </Divider>
        <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 10 }}>
          If only part of the registration was received, add the rest here with the date it is expected.
          It will show as due, and as overdue if that date passes.
        </Text>
        {renderInstalments('reg_balances', {
          addLabel: 'Add registration balance to come',
          emptyText: 'No registration balance pending',
          amountPlaceholder: `Balance (${symbol})`,
          datePlaceholder: 'Expected by',
        })}

        {/* ── EMI Schedule ───────────────────────────────────────────── */}
        <Divider orientation="left" style={{ fontSize: 13, margin: '16px 0 12px' }}>
          EMI Schedule
        </Divider>
        {renderInstalments('emis', {
          addLabel: 'Add EMI',
          emptyText: 'No EMIs — everything is paid upfront, or add the balance to come above',
          amountPlaceholder: `EMI amount (${symbol})`,
          datePlaceholder: 'Due date',
        })}

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
