import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Modal, Tabs, Input, Select, Button, Alert, Space, Typography, Tag, Avatar, Popover, DatePicker, Table, Popconfirm,
  Row, Col, Empty, message, theme,
} from 'antd';
import { MailOutlined, SendOutlined, ClockCircleOutlined, DownOutlined, UserOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { emailAPI, leadsAPI } from '../../api/api';
import RichTextEditor from './RichTextEditor';
import { sanitizeEmailHtml, htmlToText, textToHtml, fillVariables } from './emailHtml';

const { Text } = Typography;
const errorText = (e, fallback) => e?.response?.data?.detail || fallback;
const STATUS = { pending: ['blue', 'Scheduled'], sending: ['processing', 'Sending'], sent: ['green', 'Sent'], failed: ['red', 'Failed'], cancelled: ['default', 'Cancelled'] };

const draftKey = (leadId) => `emaildraft:${leadId}`;
const readDraft = (leadId) => { try { return JSON.parse(localStorage.getItem(draftKey(leadId)) || 'null'); } catch (e) { return null; } };
const writeDraft = (leadId, d) => { try { if (d) localStorage.setItem(draftKey(leadId), JSON.stringify(d)); else localStorage.removeItem(draftKey(leadId)); } catch (e) { /* storage may be unavailable */ } };

function quickTimes() {
  const now = dayjs();
  const at = (d, h) => d.hour(h).minute(0).second(0).millisecond(0);
  const tomorrow = now.add(1, 'day');
  const monday = now.day() === 1 && now.hour() < 9 ? now : now.add((8 - now.day()) % 7 || 7, 'day');
  return [
    { label: 'In 1 hour', when: now.add(1, 'hour').minute(0).second(0).millisecond(0) },
    { label: 'Tomorrow morning', when: at(tomorrow, 9) },
    { label: 'Tomorrow afternoon', when: at(tomorrow, 14) },
    { label: 'Monday morning', when: at(monday, 9) },
  ];
}

function Compose({ lead, leadId, onClose }) {
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const draft = useMemo(() => readDraft(leadId), [leadId]);
  const [subject, setSubject] = useState(draft?.subject || '');
  const [html, setHtml] = useState(draft?.html || '');
  const [custom, setCustom] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const account = useQuery({ queryKey: ['email-account'], queryFn: () => emailAPI.account().then((r) => r.data), staleTime: 60 * 1000 });
  const templates = useQuery({ queryKey: ['email-templates'], queryFn: () => emailAPI.templates().then((r) => r.data), staleTime: 10 * 60 * 1000 });

  const a = account.data;
  const me = (() => { try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch (e) { return {}; } })();
  const counselor = a?.from_name || me.full_name || '';
  const noSender = a && !a.configured && !a.shared_sender;
  const empty = !subject.trim() || !htmlToText(html).trim();
  const canSend = !!lead?.email && !noSender && !empty;

  // Keep a draft so closing the window by accident loses nothing.
  useEffect(() => { writeDraft(leadId, subject || html ? { subject, html } : null); }, [leadId, subject, html]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['email-account'] });
    qc.invalidateQueries({ queryKey: ['email-sent', leadId] });
    qc.invalidateQueries({ queryKey: ['email-scheduled', leadId] });
    qc.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes(String(leadId)) });
  };
  const payload = () => ({ subject, body: htmlToText(html), body_html: html });

  const send = useMutation({
    mutationFn: () => leadsAPI.sendEmail(leadId, payload().subject, payload().body, payload().body_html).then((r) => r.data),
    onSuccess: (d) => { message.success(`Email sent to ${d.to}`); writeDraft(leadId, null); refresh(); onClose(); },
    onError: (e) => message.error(errorText(e, 'The email could not be sent')),
  });
  const schedule = useMutation({
    mutationFn: (when) => emailAPI.schedule({ lead_id: leadId, ...payload(), send_at: when.toISOString() }).then((r) => r.data),
    onSuccess: (d) => {
      message.success(`Scheduled for ${dayjs(d.send_at).format('ddd, DD MMM, h:mm A')}`);
      writeDraft(leadId, null); setMenuOpen(false); refresh(); onClose();
    },
    onError: (e) => message.error(errorText(e, 'The email could not be scheduled')),
  });

  const pickTemplate = (id) => {
    const t = (templates.data || []).find((x) => x.id === id);
    if (!t) return;
    setSubject(t.subject);
    setHtml(textToHtml(t.body));
  };

  const schedulePanel = (
    <div style={{ width: 280 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>Send later from your mailbox</Text>
      <div style={{ display: 'grid', gap: 6, margin: '8px 0' }}>
        {quickTimes().map((q) => (
          <Button key={q.label} block style={{ textAlign: 'left', display: 'flex', justifyContent: 'space-between' }}
            disabled={!canSend} loading={schedule.isPending} onClick={() => schedule.mutate(q.when)}>
            <span>{q.label}</span><Text type="secondary">{q.when.format('ddd D MMM, h:mm A')}</Text>
          </Button>
        ))}
      </div>
      <Text type="secondary" style={{ fontSize: 12 }}>Pick a date and time</Text>
      <DatePicker showTime={{ format: 'h:mm A', use12Hours: true }} format="DD MMM YYYY, h:mm A" style={{ width: '100%', margin: '6px 0 8px' }}
        value={custom} onChange={setCustom} disabledDate={(d) => d && d.isBefore(dayjs().startOf('day'))} getPopupContainer={(n) => n.parentNode} />
      <Button type="primary" block icon={<ClockCircleOutlined />} loading={schedule.isPending}
        disabled={!canSend || !custom || custom.isBefore(dayjs().add(1, 'minute'))} onClick={() => schedule.mutate(custom)}>
        Schedule{custom ? ` for ${custom.format('D MMM, h:mm A')}` : ''}
      </Button>
    </div>
  );

  const previewSubject = fillVariables(subject, lead, counselor) || 'Subject';
  const previewHtml = sanitizeEmailHtml(fillVariables(html, lead, counselor, { html: true }));
  const field = { display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: `1px solid ${token.colorBorderSecondary}` };
  const label = { width: 56, color: token.colorTextSecondary, fontSize: 13 };

  return (
    <Row gutter={20}>
      <Col xs={24} lg={15}>
        {!lead?.email && <Alert type="warning" showIcon style={{ marginBottom: 12 }} message="This lead has no email address. Add one first." />}
        {noSender && (
          <Alert type="warning" showIcon style={{ marginBottom: 12 }} message="Connect your email first"
            description="Add your Gmail, Outlook or Zoho app password once, then email leads from your own address."
            action={<Button size="small" type="primary" onClick={() => { onClose(); navigate('/settings'); }}>Connect</Button>} />
        )}
        <div style={field}>
          <span style={label}>From</span>
          <Space>
            <Avatar size="small" icon={<UserOutlined />} style={{ background: token.colorPrimary }} />
            <Text strong>{counselor || 'You'}</Text>
            <Text type="secondary">{a?.configured ? `<${a.smtp_user}>` : (a?.shared_sender ? '(company mailbox, replies come to you)' : '')}</Text>
          </Space>
          {a?.configured && <Text type="secondary" style={{ marginLeft: 'auto', fontSize: 12 }}>{a.sent_today}/{a.daily_limit} today</Text>}
        </div>
        <div style={field}>
          <span style={label}>To</span>
          <Tag style={{ margin: 0, padding: '2px 10px', borderRadius: 14 }} color={lead?.email ? 'blue' : 'red'}>
            {lead?.full_name || 'Lead'} &lt;{lead?.email || 'no email'}&gt;
          </Tag>
          {lead?.course_interested && <Text type="secondary" style={{ fontSize: 12 }}>{lead.course_interested}</Text>}
        </div>
        <div style={field}>
          <span style={label}>Subject</span>
          <Input variant="borderless" placeholder="Subject" maxLength={200} value={subject} onChange={(e) => setSubject(e.target.value)} style={{ padding: 0 }} />
        </div>
        <div style={{ padding: '10px 0' }}>
          <Select allowClear size="small" style={{ width: 240, marginBottom: 10 }} placeholder="Start from a template"
            loading={templates.isLoading} options={(templates.data || []).map((t) => ({ value: t.id, label: t.name }))} onChange={pickTemplate} />
          <RichTextEditor value={html} onChange={setHtml} />
          {a?.configured && a.signature && (
            <div style={{ marginTop: 8, color: token.colorTextTertiary, fontSize: 13, whiteSpace: 'pre-wrap' }}>
              {`--\n${a.signature}`}
            </div>
          )}
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 6 }}>
            {'{name}'}, {'{course}'} and {'{counselor}'} are filled in for this lead when the email is sent. Draft saved automatically.
          </Text>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 4 }}>
          <Popconfirm title="Discard this draft?" okText="Discard" disabled={empty} onConfirm={() => { writeDraft(leadId, null); setSubject(''); setHtml(''); }}>
            <Button type="text" danger icon={<DeleteOutlined />} disabled={empty}>Discard</Button>
          </Popconfirm>
          <Space.Compact>
            <Button type="primary" size="large" icon={<SendOutlined />} loading={send.isPending} disabled={!canSend} onClick={() => send.mutate()}>
              Send now
            </Button>
            <Popover trigger="click" placement="topRight" open={menuOpen} onOpenChange={setMenuOpen} content={schedulePanel} title="Schedule send">
              <Button type="primary" size="large" icon={<DownOutlined />} disabled={!canSend} aria-label="Schedule send" />
            </Popover>
          </Space.Compact>
        </div>
      </Col>
      <Col xs={24} lg={9}>
        <Text type="secondary" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.5 }}>Preview: how {lead?.full_name?.split(' ')[0] || 'the lead'} sees it</Text>
        <div style={{ marginTop: 8, border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 10, background: token.colorBgContainer, overflow: 'hidden' }}>
          <div style={{ padding: '10px 14px', background: token.colorFillQuaternary, borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
            <Text strong style={{ display: 'block' }}>{previewSubject}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>{counselor || 'You'} · to {lead?.email || '—'}</Text>
          </div>
          <div style={{ padding: 14, fontSize: 14, lineHeight: 1.6, minHeight: 200, maxHeight: 420, overflow: 'auto', overflowWrap: 'anywhere' }}>
            <style>{`.email-preview p { margin: 0 0 10px; } .email-preview ul, .email-preview ol { margin: 0 0 10px 22px; padding: 0; } .email-preview a { color: ${token.colorLink}; }`}</style>
            {previewHtml ? <div className="email-preview" dangerouslySetInnerHTML={{ __html: previewHtml }} /> : <Text type="secondary">Your message appears here as you type.</Text>}
            {a?.configured && a.signature && <div style={{ marginTop: 12, color: token.colorTextTertiary, whiteSpace: 'pre-wrap' }}>{`--\n${a.signature}`}</div>}
          </div>
        </div>
      </Col>
    </Row>
  );
}

function ScheduledTab({ leadId }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ['email-scheduled', leadId], queryFn: () => emailAPI.scheduled(leadId).then((r) => r.data.scheduled), refetchInterval: 30000 });
  const cancel = useMutation({
    mutationFn: (id) => emailAPI.cancelScheduled(id),
    onSuccess: () => { message.success('Cancelled'); qc.invalidateQueries({ queryKey: ['email-scheduled', leadId] }); },
    onError: (e) => message.error(errorText(e, 'Could not cancel')),
  });
  return (
    <Table size="small" rowKey="id" loading={isLoading} dataSource={data || []} pagination={{ pageSize: 6, hideOnSinglePage: true }}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Nothing scheduled for this lead" /> }}
      columns={[
        { title: 'Subject', dataIndex: 'subject', ellipsis: true },
        { title: 'Send time', dataIndex: 'send_at', width: 170, render: (v) => dayjs(v).format('ddd D MMM, h:mm A') },
        { title: 'Status', dataIndex: 'status', width: 230, render: (v, r) => (
          <div><Tag color={(STATUS[v] || [])[0]}>{(STATUS[v] || [])[1] || v}</Tag>{r.error && <Text type="danger" style={{ fontSize: 12, display: 'block' }}>{r.error}</Text>}</div>) },
        { title: '', width: 80, render: (_, r) => r.status === 'pending' && (
          <Popconfirm title="Cancel this scheduled email?" onConfirm={() => cancel.mutate(r.id)}><Button size="small" danger>Cancel</Button></Popconfirm>) },
      ]} />
  );
}

function SentTab({ leadId }) {
  const { data, isLoading } = useQuery({ queryKey: ['email-sent', leadId], queryFn: () => emailAPI.forLead(leadId).then((r) => r.data.emails) });
  return (
    <Table size="small" rowKey="id" loading={isLoading} dataSource={data || []} pagination={{ pageSize: 6, hideOnSinglePage: true }}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No emails sent to this lead yet" /> }}
      columns={[
        { title: 'Subject', dataIndex: 'subject', ellipsis: true },
        { title: 'From', dataIndex: 'user_email', width: 170, ellipsis: true },
        { title: 'Sent', dataIndex: 'created_at', width: 160, render: (v) => dayjs(v).format('D MMM YYYY, h:mm A') },
        { title: 'Status', dataIndex: 'status', width: 90, render: (v, r) => (
          <Tag color={v === 'sent' ? 'green' : 'red'} title={r.error || ''}>{v === 'sent' ? 'Sent' : 'Failed'}</Tag>) },
      ]} />
  );
}

/** Compose, send or schedule an email to a lead from the user's own mailbox, with history. */
export default function EmailComposeModal({ open, onClose, lead, leadId }) {
  const scheduled = useQuery({ queryKey: ['email-scheduled', leadId], queryFn: () => emailAPI.scheduled(leadId).then((r) => r.data.scheduled), enabled: !!open && !!leadId, staleTime: 30000 });
  const pending = (scheduled.data || []).filter((s) => s.status === 'pending').length;
  return (
    <Modal title={<span><MailOutlined /> New email</span>} open={open} onCancel={onClose} footer={null} width={1040} destroyOnClose style={{ top: 32 }}>
      {open && (
        <Tabs items={[
          { key: 'compose', label: 'Compose', children: <Compose lead={lead} leadId={leadId} onClose={onClose} /> },
          { key: 'scheduled', label: <span>Scheduled{pending ? <Tag color="blue" style={{ marginLeft: 6 }}>{pending}</Tag> : null}</span>, children: <ScheduledTab leadId={leadId} /> },
          { key: 'sent', label: 'Sent', children: <SentTab leadId={leadId} /> },
        ]} />
      )}
    </Modal>
  );
}
