import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Modal, Tabs, Input, Select, Button, Alert, Space, Typography, Tag, Avatar, Popover, DatePicker, Table, Popconfirm,
  Row, Col, Empty, Switch, Tooltip, Progress, Statistic, message, theme,
} from 'antd';
import {
  MailOutlined, SendOutlined, ClockCircleOutlined, DownOutlined, UserOutlined, DeleteOutlined, PaperClipOutlined,
  EyeOutlined, LinkOutlined, TeamOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { emailAPI, leadsAPI } from '../../api/api';
import RichTextEditor from './RichTextEditor';
import AttachmentPicker, { prettySize } from './AttachmentPicker';
import { sanitizeEmailHtml, htmlToText, textToHtml, fillVariables, escapeHtml } from './emailHtml';

const { Text } = Typography;
const errorText = (e, fallback) => e?.response?.data?.detail || fallback;
const STATUS = { pending: ['blue', 'Scheduled'], sending: ['processing', 'Sending'], sent: ['green', 'Sent'], failed: ['red', 'Failed'], cancelled: ['default', 'Cancelled'] };
const SKIP_TEXT = { not_found: 'not found', no_access: 'outside your team', no_email: 'no email address', invalid_email: 'invalid email', unsubscribed: 'unsubscribed', duplicate_email: 'duplicate email' };

const draftKey = (id) => `emaildraft:${id}`;
const readDraft = (id) => { try { return JSON.parse(localStorage.getItem(draftKey(id)) || 'null'); } catch (e) { return null; } };
const writeDraft = (id, d) => { try { if (d) localStorage.setItem(draftKey(id), JSON.stringify(d)); else localStorage.removeItem(draftKey(id)); } catch (e) { /* storage may be unavailable */ } };

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

/** Live progress of a bulk send: sent / failed / waiting, plus opens and clicks as they come in. */
function BatchProgress({ batchId, queued, skipped, onClose }) {
  const { data } = useQuery({
    queryKey: ['email-batch', batchId],
    queryFn: () => emailAPI.batch(batchId).then((r) => r.data),
    refetchInterval: (q) => (q.state.data?.done ? false : 2500),
  });
  const total = data?.total || queued;
  const finished = (data?.sent || 0) + (data?.failed || 0);
  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: '8px 0' }}>
      <Alert type={data?.done ? (data.failed ? 'warning' : 'success') : 'info'} showIcon
        message={data?.done ? `Finished: ${data.sent} of ${total} sent` : `Sending ${total} emails…`}
        description={data?.done ? undefined : 'You can close this window. The emails keep sending in the background.'} />
      <Progress percent={total ? Math.round((finished / total) * 100) : 0} status={data?.done ? (data.failed ? 'exception' : 'success') : 'active'} />
      <Row gutter={12}>
        <Col span={6}><Statistic title="Sent" value={data?.sent || 0} valueStyle={{ color: '#389e0d' }} /></Col>
        <Col span={6}><Statistic title="Failed" value={data?.failed || 0} valueStyle={{ color: data?.failed ? '#cf1322' : undefined }} /></Col>
        <Col span={6}><Statistic title="Waiting" value={data?.waiting ?? total} /></Col>
        <Col span={6}><Statistic title="Opened · clicked" value={`${data?.opened || 0} · ${data?.clicked || 0}`} /></Col>
      </Row>
      {Object.keys(skipped || {}).length > 0 && (
        <Text type="secondary">Skipped: {Object.entries(skipped).map(([k, n]) => `${n} ${SKIP_TEXT[k] || k}`).join(', ')}</Text>
      )}
      {(data?.errors || []).map((e) => <Alert key={e.error} type="error" message={`${e.count} failed: ${e.error}`} />)}
      <div style={{ textAlign: 'right' }}><Button type="primary" onClick={onClose}>{data?.done ? 'Done' : 'Close'}</Button></div>
    </Space>
  );
}

function Compose({ lead, leadId, leadIds, onClose }) {
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const bulk = Array.isArray(leadIds);
  const draftId = bulk ? 'bulk' : leadId;
  const draft = useMemo(() => readDraft(draftId), [draftId]);
  const [subject, setSubject] = useState(draft?.subject || '');
  const [html, setHtml] = useState(draft?.html || '');
  const [files, setFiles] = useState([]);
  const [track, setTrack] = useState(true);
  const [custom, setCustom] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [batch, setBatch] = useState(null);

  const account = useQuery({ queryKey: ['email-account'], queryFn: () => emailAPI.account().then((r) => r.data), staleTime: 60 * 1000 });
  const templates = useQuery({ queryKey: ['email-templates'], queryFn: () => emailAPI.templates().then((r) => r.data), staleTime: 10 * 60 * 1000 });
  const preview = useQuery({ queryKey: ['email-bulk-preview', leadIds], queryFn: () => emailAPI.bulkPreview(leadIds).then((r) => r.data), enabled: bulk, staleTime: 30 * 1000 });
  const history = useQuery({ queryKey: ['email-sent', leadId], queryFn: () => emailAPI.forLead(leadId).then((r) => r.data), enabled: !bulk && !!leadId, staleTime: 30 * 1000 });

  const a = account.data;
  const p = preview.data;
  const sample = bulk ? { full_name: p?.sample?.full_name, course_interested: p?.sample?.course_interested, email: p?.sample?.email } : lead;
  const me = (() => { try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch (e) { return {}; } })();
  const counselor = a?.from_name || me.full_name || '';
  const noSender = a && !a.configured && !a.shared_sender;
  const empty = !subject.trim() || !htmlToText(html).trim();
  const optedOut = !bulk && history.data?.opted_out;
  const canSend = !empty && !noSender && !optedOut && (bulk ? (p?.eligible || 0) > 0 : !!lead?.email);
  const recipients = bulk ? (p?.eligible || 0) : 1;

  // Keep a draft so closing the window by accident loses nothing.
  useEffect(() => { writeDraft(draftId, subject || html ? { subject, html } : null); }, [draftId, subject, html]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['email-account'] });
    qc.invalidateQueries({ queryKey: ['email-sent', leadId] });
    qc.invalidateQueries({ queryKey: ['email-scheduled', leadId] });
    qc.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes(String(leadId)) });
  };
  const payload = () => ({
    subject, body: htmlToText(html), body_html: html, track,
    attachments: files.map((f) => ({ id: f.id, source: f.source })),
  });

  const send = useMutation({
    mutationFn: () => {
      const x = payload();
      return leadsAPI.sendEmail(leadId, x.subject, x.body, x.body_html, { attachments: x.attachments, track: x.track }).then((r) => r.data);
    },
    onSuccess: (d) => { message.success(`Email sent to ${d.to}`); writeDraft(draftId, null); refresh(); onClose(); },
    onError: (e) => message.error(errorText(e, 'The email could not be sent')),
  });
  const schedule = useMutation({
    mutationFn: (when) => emailAPI.schedule({ lead_id: leadId, ...payload(), send_at: when.toISOString() }).then((r) => r.data),
    onSuccess: (d) => {
      message.success(`Scheduled for ${dayjs(d.send_at).format('ddd, DD MMM, h:mm A')}`);
      writeDraft(draftId, null); setMenuOpen(false); refresh(); onClose();
    },
    onError: (e) => message.error(errorText(e, 'The email could not be scheduled')),
  });
  const bulkSend = useMutation({
    mutationFn: (when) => emailAPI.bulk({ lead_ids: leadIds, ...payload(), ...(when ? { send_at: when.toISOString() } : {}) }).then((r) => r.data),
    onSuccess: (d, when) => {
      writeDraft(draftId, null);
      setMenuOpen(false);
      if (when) {
        message.success(`${d.queued} emails scheduled for ${dayjs(when).format('ddd, DD MMM, h:mm A')}`);
        onClose();
      } else {
        setBatch(d);
      }
    },
    onError: (e) => message.error(errorText(e, 'The emails could not be queued')),
  });

  const sendNow = () => {
    if (!bulk) { send.mutate(); return; }
    Modal.confirm({
      title: `Send to ${recipients} lead${recipients === 1 ? '' : 's'} now?`,
      content: 'Each lead gets their own personalised email from your mailbox, with an unsubscribe link.',
      okText: `Send ${recipients} emails`,
      onOk: () => bulkSend.mutateAsync(null),
    });
  };
  const scheduleAt = (when) => (bulk ? bulkSend.mutate(when) : schedule.mutate(when));
  const scheduling = schedule.isPending || bulkSend.isPending;

  const pickTemplate = (id) => {
    const t = (templates.data || []).find((x) => x.id === id);
    if (!t) return;
    setSubject(t.subject);
    setHtml(textToHtml(t.body));
  };
  const insertLink = ({ name, url }) => setHtml((h) => `${h || ''}<p><a href="${escapeHtml(url)}">${escapeHtml(name)}</a></p>`);

  if (batch) return <BatchProgress batchId={batch.batch_id} queued={batch.queued} skipped={batch.skipped} onClose={onClose} />;

  const schedulePanel = (
    <div style={{ width: 280 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>Send later from your mailbox</Text>
      <div style={{ display: 'grid', gap: 6, margin: '8px 0' }}>
        {quickTimes().map((q) => (
          <Button key={q.label} block style={{ textAlign: 'left', display: 'flex', justifyContent: 'space-between' }}
            disabled={!canSend} loading={scheduling} onClick={() => scheduleAt(q.when)}>
            <span>{q.label}</span><Text type="secondary">{q.when.format('ddd D MMM, h:mm A')}</Text>
          </Button>
        ))}
      </div>
      <Text type="secondary" style={{ fontSize: 12 }}>Pick a date and time</Text>
      <DatePicker showTime={{ format: 'h:mm A', use12Hours: true }} format="DD MMM YYYY, h:mm A" style={{ width: '100%', margin: '6px 0 8px' }}
        value={custom} onChange={setCustom} disabledDate={(d) => d && d.isBefore(dayjs().startOf('day'))} getPopupContainer={(n) => n.parentNode} />
      <Button type="primary" block icon={<ClockCircleOutlined />} loading={scheduling}
        disabled={!canSend || !custom || custom.isBefore(dayjs().add(1, 'minute'))} onClick={() => scheduleAt(custom)}>
        Schedule{custom ? ` for ${custom.format('D MMM, h:mm A')}` : ''}
      </Button>
    </div>
  );

  const previewSubject = fillVariables(subject, sample, counselor) || 'Subject';
  const previewHtml = sanitizeEmailHtml(fillVariables(html, sample, counselor, { html: true }));
  const field = { display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: `1px solid ${token.colorBorderSecondary}` };
  const label = { width: 56, color: token.colorTextSecondary, fontSize: 13 };
  const skipped = Object.entries(p?.skipped || {}).map(([k, n]) => `${n} ${SKIP_TEXT[k] || k}`).join(', ');

  return (
    <Row gutter={20}>
      <Col xs={24} lg={15}>
        {!bulk && !lead?.email && <Alert type="warning" showIcon style={{ marginBottom: 12 }} message="This lead has no email address. Add one first." />}
        {optedOut && <Alert type="error" showIcon style={{ marginBottom: 12 }} message="This lead unsubscribed from emails" description="The CRM will not email them." />}
        {bulk && p && p.eligible === 0 && <Alert type="error" showIcon style={{ marginBottom: 12 }} message="None of the selected leads can be emailed" description={skipped} />}
        {bulk && p && p.eligible > p.remaining_today && p.sender_ready && (
          <Alert type="warning" showIcon style={{ marginBottom: 12 }} message={`You can send ${p.remaining_today} more emails today (limit ${p.daily_limit})`}
            description="Select fewer leads, or schedule this for tomorrow." />
        )}
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
          {bulk ? (
            <Space wrap>
              <Tag icon={<TeamOutlined />} color="blue" style={{ margin: 0, padding: '2px 10px', borderRadius: 14 }}>
                {preview.isLoading ? 'Checking leads…' : `${p?.eligible ?? 0} of ${leadIds.length} leads will receive this`}
              </Tag>
              {skipped && <Text type="secondary" style={{ fontSize: 12 }}>Skipped: {skipped}</Text>}
            </Space>
          ) : (
            <>
              <Tag style={{ margin: 0, padding: '2px 10px', borderRadius: 14 }} color={lead?.email ? 'blue' : 'red'}>
                {lead?.full_name || 'Lead'} &lt;{lead?.email || 'no email'}&gt;
              </Tag>
              {lead?.course_interested && <Text type="secondary" style={{ fontSize: 12 }}>{lead.course_interested}</Text>}
            </>
          )}
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
          <div style={{ marginTop: 10 }}>
            <AttachmentPicker value={files} onChange={setFiles} onInsertLink={insertLink} />
          </div>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 6 }}>
            {'{name}'}, {'{course}'} and {'{counselor}'} are filled in for each lead when the email is sent. Draft saved automatically.
          </Text>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 4, flexWrap: 'wrap', gap: 8 }}>
          <Space size={16} wrap>
            <Popconfirm title="Discard this draft?" okText="Discard" disabled={empty && !files.length}
              onConfirm={() => { writeDraft(draftId, null); setSubject(''); setHtml(''); setFiles([]); }}>
              <Button type="text" danger icon={<DeleteOutlined />} disabled={empty && !files.length}>Discard</Button>
            </Popconfirm>
            <Tooltip title="Adds an invisible image and redirects your links so you can see who opened or clicked. Open counts are approximate: some mail apps load images automatically.">
              <span><Switch size="small" checked={track} onChange={setTrack} /> <Text type="secondary" style={{ fontSize: 13 }}>Track opens &amp; clicks</Text></span>
            </Tooltip>
          </Space>
          <Space.Compact>
            <Button type="primary" size="large" icon={<SendOutlined />} loading={send.isPending} disabled={!canSend} onClick={sendNow}>
              {bulk ? `Send to ${recipients}` : 'Send now'}
            </Button>
            <Popover trigger="click" placement="topRight" open={menuOpen} onOpenChange={setMenuOpen} content={schedulePanel} title="Schedule send">
              <Button type="primary" size="large" icon={<DownOutlined />} disabled={!canSend} aria-label="Schedule send" />
            </Popover>
          </Space.Compact>
        </div>
      </Col>
      <Col xs={24} lg={9}>
        <Text type="secondary" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.5 }}>
          Preview: how {bulk ? `a lead (e.g. ${sample?.full_name?.split(' ')[0] || 'Aarav'})` : (lead?.full_name?.split(' ')[0] || 'the lead')} sees it
        </Text>
        <div style={{ marginTop: 8, border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 10, background: token.colorBgContainer, overflow: 'hidden' }}>
          <div style={{ padding: '10px 14px', background: token.colorFillQuaternary, borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
            <Text strong style={{ display: 'block' }}>{previewSubject}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>{counselor || 'You'} · to {sample?.email || '—'}</Text>
          </div>
          <div style={{ padding: 14, fontSize: 14, lineHeight: 1.6, minHeight: 180, maxHeight: 380, overflow: 'auto', overflowWrap: 'anywhere' }}>
            <style>{`.email-preview p { margin: 0 0 10px; } .email-preview ul, .email-preview ol { margin: 0 0 10px 22px; padding: 0; } .email-preview a { color: ${token.colorLink}; }`}</style>
            {previewHtml ? <div className="email-preview" dangerouslySetInnerHTML={{ __html: previewHtml }} /> : <Text type="secondary">Your message appears here as you type.</Text>}
            {a?.configured && a.signature && <div style={{ marginTop: 12, color: token.colorTextTertiary, whiteSpace: 'pre-wrap' }}>{`--\n${a.signature}`}</div>}
            {bulk && <div style={{ marginTop: 12, fontSize: 12, color: token.colorTextTertiary }}>Do not want these emails? <u>Unsubscribe</u></div>}
          </div>
          {files.length > 0 && (
            <div style={{ padding: '8px 14px', borderTop: `1px solid ${token.colorBorderSecondary}`, background: token.colorFillQuaternary }}>
              <Space wrap size={6}>
                {files.map((f) => <Tag key={`${f.source}:${f.id}`} icon={<PaperClipOutlined />} style={{ margin: 0 }}>{f.name} · {prettySize(f.size || 0)}</Tag>)}
              </Space>
            </div>
          )}
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
  const { data, isLoading } = useQuery({ queryKey: ['email-sent', leadId], queryFn: () => emailAPI.forLead(leadId).then((r) => r.data), refetchInterval: 60000 });
  return (
    <Table size="small" rowKey="id" loading={isLoading} dataSource={data?.emails || []} pagination={{ pageSize: 6, hideOnSinglePage: true }}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No emails sent to this lead yet" /> }}
      columns={[
        { title: 'Subject', dataIndex: 'subject', ellipsis: true, render: (v, r) => (
          <Space size={6}>{v}{r.attachments?.length > 0 && (
            <Tooltip title={r.attachments.map((x) => x.name).join(', ')}><PaperClipOutlined /></Tooltip>)}</Space>) },
        { title: 'From', dataIndex: 'user_email', width: 160, ellipsis: true },
        { title: 'Sent', dataIndex: 'created_at', width: 150, render: (v) => dayjs(v).format('D MMM YYYY, h:mm A') },
        { title: 'Engagement', width: 170, render: (_, r) => (
          r.status !== 'sent' ? '—' : (
            <Space size={4} wrap>
              <Tooltip title={r.last_open_at ? `Last opened ${dayjs(r.last_open_at).format('D MMM, h:mm A')}. Open counts are approximate.` : 'Not opened yet (or opens are not tracked)'}>
                <Tag icon={<EyeOutlined />} color={r.opens ? 'green' : 'default'} style={{ margin: 0 }}>{r.opens || 0}</Tag>
              </Tooltip>
              <Tooltip title="Link clicks"><Tag icon={<LinkOutlined />} color={r.clicks ? 'blue' : 'default'} style={{ margin: 0 }}>{r.clicks || 0}</Tag></Tooltip>
            </Space>)) },
        { title: 'Status', dataIndex: 'status', width: 90, render: (v, r) => (
          <Tag color={v === 'sent' ? 'green' : 'red'} title={r.error || ''}>{v === 'sent' ? 'Sent' : 'Failed'}</Tag>) },
      ]} />
  );
}

/** Compose, send or schedule an email to one lead, or (with `leadIds`) to many leads at once. */
export default function EmailComposeModal({ open, onClose, lead, leadId, leadIds }) {
  const bulk = Array.isArray(leadIds);
  const scheduled = useQuery({ queryKey: ['email-scheduled', leadId], queryFn: () => emailAPI.scheduled(leadId).then((r) => r.data.scheduled), enabled: !!open && !bulk && !!leadId, staleTime: 30000 });
  const pending = (scheduled.data || []).filter((s) => s.status === 'pending').length;
  return (
    <Modal title={<span><MailOutlined /> {bulk ? `Email ${leadIds.length} lead${leadIds.length === 1 ? '' : 's'}` : 'New email'}</span>}
      open={open} onCancel={onClose} footer={null} width={1040} destroyOnClose style={{ top: 32 }}>
      {open && (bulk ? <Compose leadIds={leadIds} onClose={onClose} /> : (
        <Tabs items={[
          { key: 'compose', label: 'Compose', children: <Compose lead={lead} leadId={leadId} onClose={onClose} /> },
          { key: 'scheduled', label: <span>Scheduled{pending ? <Tag color="blue" style={{ marginLeft: 6 }}>{pending}</Tag> : null}</span>, children: <ScheduledTab leadId={leadId} /> },
          { key: 'sent', label: 'Sent', children: <SentTab leadId={leadId} /> },
        ]} />
      ))}
    </Modal>
  );
}
