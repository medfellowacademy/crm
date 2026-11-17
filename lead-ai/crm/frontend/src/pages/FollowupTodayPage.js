import React, { useState, useMemo, useEffect } from 'react';
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Card, Row, Col, Tag, Button, Avatar, Tooltip, Select, Space, Typography, Modal, Input, DatePicker,
  Checkbox, Dropdown, Segmented, Skeleton, Result, Empty, Progress, Alert, message,
} from 'antd';
import {
  PhoneOutlined, EyeOutlined, CalendarOutlined, WarningOutlined, CheckCircleOutlined, ClockCircleOutlined,
  GlobalOutlined, BookOutlined, ReloadOutlined, MessageOutlined, SearchOutlined, FieldTimeOutlined, ScheduleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { followupsAPI, leadsAPI } from '../api/api';
import { useAuth } from '../context/AuthContext';
import ChatDrawer from '../components/ChatDrawer';
import { parseUtc } from '../features/pipeline/pipelineUtils';

const { Text, Title } = Typography;
const { TextArea } = Input;

const segmentColor = { Hot: '#f5222d', Warm: '#fa8c16', Cold: '#1890ff', Junk: '#8c8c8c' };
const statusColor = {
  Fresh: 'blue', 'Follow Up': 'orange', Warm: 'volcano', Hot: 'red', Enrolled: 'green', 'Will Enroll Later': 'gold',
  'Not Interested': 'default', Dropped: 'volcano', Junk: 'default', 'Not Answering': 'warning',
  'TMT No Response': 'gold', 'Re-assigned Lead': 'geekblue', 'Test Lead': 'default',
};
// Enrolling needs the fee and payment plan, so it is never a one-click status here: open the lead for that.
const QUICK_STATUSES = ['Fresh', 'Follow Up', 'Warm', 'Hot', 'Will Enroll Later', 'Not Answering', 'Not Interested', 'Dropped', 'Junk', 'TMT No Response', 'Re-assigned Lead'];
const LOSS_STATUSES = new Set(['Not Interested', 'Junk', 'Dropped', 'TMT No Response']);   // same rule as the lead page
const LOSS_REASONS = [
  'Price too high', 'Went with competitor', 'Not the right course', 'Cannot take time off work', 'No response / Unreachable',
  'Not eligible', 'Needs more time', 'Financial constraints', 'Already enrolled elsewhere', 'Other',
];
const SORTS = [{ value: 'priority', label: 'Best to call first' }, { value: 'due', label: 'Soonest due' }, { value: 'oldest', label: 'Longest overdue' }];
const PAGE = 25;

const tomorrowAt = (h = 10) => dayjs().add(1, 'day').hour(h).minute(0).second(0);
const quickDates = [
  { label: 'Tomorrow', get: () => tomorrowAt(10) },
  { label: 'In 3 days', get: () => dayjs().add(3, 'day').hour(10).minute(0).second(0) },
  { label: 'Next week', get: () => dayjs().add(7, 'day').hour(10).minute(0).second(0) },
];
const errText = (e, fallback) => e?.response?.data?.detail || e?.message || fallback;

// ── Log a call ────────────────────────────────────────────────────────────────
// Mounted fresh for every lead (key = lead_id) so nothing from the previous lead carries over.
function QuickActionModal({ lead, onClose, onDone }) {
  const [status, setStatus] = useState(lead.status || 'Follow Up');
  const [nextDate, setNextDate] = useState(null);
  const [noNext, setNoNext] = useState(false);
  const [reason, setReason] = useState(undefined);
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();

  const isLoss = LOSS_STATUSES.has(status);
  // A call needs a next step. Without one the lead stays "overdue" and the same row is back tomorrow.
  const needsDate = !isLoss && !noNext;
  const problem = needsDate && !nextDate ? 'Pick the next follow-up date (or tick "No further follow-up")'
    : isLoss && !reason && status !== 'Not Answering' ? 'Pick a reason' : null;

  const save = async () => {
    if (problem) { message.warning(problem); return; }
    setSaving(true);
    const data = {};
    if (status !== lead.status) data.status = status;
    if (isLoss) { data.loss_reason = reason; data.follow_up_date = null; }
    else if (noNext) data.follow_up_date = null;
    else data.follow_up_date = nextDate.toISOString();
    try {
      await leadsAPI.update(lead.lead_id, data);
    } catch (e) {
      setSaving(false);
      message.error(errText(e, 'Could not update the lead - nothing was changed'));
      return;
    }
    if (note.trim()) {
      try {
        await leadsAPI.addNote(lead.lead_id, { content: note.trim(), channel: 'call' });
      } catch (e) {
        message.warning('The lead was updated, but the call note could not be saved - please add it again from the lead.');
      }
    }
    setSaving(false);
    message.success(`${lead.full_name} updated`);
    onDone(lead);
    onClose();
  };

  return (
    <Modal
      open onCancel={onClose} onOk={save} okText="Save & close" confirmLoading={saving} width={540} destroyOnHidden
      okButtonProps={{ disabled: !!problem }}
      title={
        <Space>
          <Avatar style={{ background: segmentColor[lead.ai_segment] || '#1890ff' }}>{lead.full_name?.charAt(0)}</Avatar>
          <span>{lead.full_name}</span>
          {lead.ai_segment && <Tag color={segmentColor[lead.ai_segment]}>{lead.ai_segment}</Tag>}
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size={14}>
        <Row gutter={8}>
          <Col span={12}><Text type="secondary">Phone</Text><div><Text strong>{lead.phone || '—'}</Text></div></Col>
          <Col span={12}><Text type="secondary">Course</Text><div><Text strong style={{ fontSize: 12 }}>{lead.course_interested || '—'}</Text></div></Col>
        </Row>
        {lead.ai_score > 0 && (
          <div>
            <Text type="secondary">AI score</Text>
            <Progress percent={Math.round(lead.ai_score)} size="small" strokeColor={lead.ai_score >= 70 ? '#52c41a' : lead.ai_score >= 40 ? '#fa8c16' : '#f5222d'} />
          </div>
        )}
        {lead.primary_objection && (
          <div style={{ background: '#fff7e6', padding: '8px 12px', borderRadius: 6, borderLeft: '3px solid #fa8c16' }}>
            <Text type="secondary" style={{ fontSize: 11 }}>Known objection</Text><div><Text strong>{lead.primary_objection}</Text></div>
          </div>
        )}
        {lead.next_action && (
          <div style={{ background: '#f6ffed', padding: '8px 12px', borderRadius: 6, borderLeft: '3px solid #52c41a' }}>
            <Text type="secondary" style={{ fontSize: 11 }}>Recommended action</Text><div><Text>{lead.next_action}</Text></div>
          </div>
        )}

        <div>
          <Text type="secondary">Status after this call</Text>
          <Select value={status} onChange={setStatus} style={{ width: '100%', marginTop: 4 }} options={QUICK_STATUSES.map((s) => ({ value: s, label: s }))} />
          <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 4 }}>
            To mark someone <b>Enrolled</b>, <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate(`/leads/${lead.lead_id}`)}>open the lead</Button> so the fee and payment plan are recorded.
          </div>
        </div>

        {isLoss ? (
          <div>
            <Text type="secondary">Reason</Text>
            <Select value={reason} onChange={setReason} placeholder="Why is this lead being closed?" style={{ width: '100%', marginTop: 4 }} options={LOSS_REASONS.map((r) => ({ value: r, label: r }))} />
          </div>
        ) : (
          <div>
            <Text type="secondary">Next follow-up</Text>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '4px 0 8px' }}>
              {quickDates.map((q) => (
                <Button key={q.label} size="small" disabled={noNext} type={nextDate && nextDate.isSame(q.get(), 'day') ? 'primary' : 'default'} onClick={() => setNextDate(q.get())}>{q.label}</Button>
              ))}
            </div>
            <DatePicker
              showTime={{ format: 'hh:mm A', use12Hours: true }} format="DD MMM YYYY, hh:mm A" style={{ width: '100%' }} value={nextDate} disabled={noNext}
              onChange={setNextDate} disabledDate={(d) => d && d < dayjs().startOf('day')} placeholder="Pick the next follow-up date and time"
            />
            <Checkbox checked={noNext} onChange={(e) => setNoNext(e.target.checked)} style={{ marginTop: 8 }}>No further follow-up needed</Checkbox>
          </div>
        )}

        <div>
          <Text type="secondary">Call note (optional)</Text>
          <TextArea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What happened on this call?" style={{ marginTop: 4 }} />
        </div>
        {problem && <Text type="warning" style={{ fontSize: 12 }}>{problem}</Text>}
      </Space>
    </Modal>
  );
}

// ── one lead ──────────────────────────────────────────────────────────────────
function LeadRow({ lead, tab, rank, onLog, onChat, onSnooze }) {
  const navigate = useNavigate();
  const overdue = tab === 'overdue';
  const due = parseUtc(lead.follow_up_date);
  const topPriority = rank != null && rank < 3;
  const dueText = !due ? 'No follow-up date'
    : overdue ? `${lead.days_overdue} day${lead.days_overdue === 1 ? '' : 's'} overdue · was ${due.format('DD MMM, hh:mm A')}`
      : tab === 'today' ? `Due ${due.format('hh:mm A')}${lead.due_passed ? ' · time passed' : ''}`
        : `Due ${due.format('ddd DD MMM, hh:mm A')}`;
  const accent = overdue ? '#f5222d' : lead.due_passed ? '#fa8c16' : segmentColor[lead.ai_segment] || '#1890ff';
  const snoozeItems = quickDates.map((q, i) => ({ key: String(i), label: q.label }));

  return (
    <Card size="small" styles={{ body: { padding: '10px 14px' } }}
      style={{ marginBottom: 8, borderLeft: `4px solid ${accent}`, background: overdue ? '#fff2f0' : '#fff' }}>
      <Row align="middle" gutter={8} wrap={false}>
        <Col flex="none" style={{ position: 'relative' }}>
          {topPriority && (
            <Tooltip title={`Call priority #${rank + 1}: ranked by conversion likelihood, churn risk and how late it is`}>
              <div style={{ position: 'absolute', top: -6, left: -6, zIndex: 1, width: 18, height: 18, borderRadius: '50%', background: '#faad14', color: '#fff', fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #fff' }}>
                {rank + 1}
              </div>
            </Tooltip>
          )}
          <Avatar size={38} style={{ background: segmentColor[lead.ai_segment] || '#1890ff', flexShrink: 0 }}>{lead.full_name?.charAt(0)}</Avatar>
        </Col>

        <Col flex="auto" style={{ minWidth: 0 }}>
          <Space size={6} wrap>
            <Text strong style={{ fontSize: 14 }}>{lead.full_name}</Text>
            {lead.ai_segment && <Tag color={segmentColor[lead.ai_segment]} style={{ margin: 0 }}>{lead.ai_segment}</Tag>}
            <Tag color={statusColor[lead.status] || 'default'} style={{ margin: 0 }}>{lead.status}</Tag>
            {topPriority && <Tag color="gold" style={{ margin: 0 }}>Call first</Tag>}
          </Space>
          <div style={{ marginTop: 3, fontSize: 12, color: overdue ? '#cf1322' : lead.due_passed ? '#d46b08' : '#595959', fontWeight: 500 }}>
            {overdue ? <WarningOutlined /> : <ClockCircleOutlined />} {dueText}
          </div>
          <div style={{ marginTop: 3, fontSize: 12, color: '#666' }}>
            <Space size={12} wrap>
              {lead.phone && <span><PhoneOutlined /> {lead.phone}</span>}
              {lead.country && <span><GlobalOutlined /> {lead.country}</span>}
              {lead.course_interested && <span><BookOutlined /> <Text style={{ fontSize: 12 }} ellipsis>{lead.course_interested}</Text></span>}
              {lead.assigned_to && <span>👤 {lead.assigned_to}</span>}
              {lead.idle_days != null && lead.idle_days >= 7 && <span style={{ color: lead.idle_days >= 14 ? '#cf1322' : '#8c8c8c' }}>Last contact {lead.idle_days}d ago</span>}
            </Space>
          </div>
          {lead.next_action && <div style={{ marginTop: 3, fontSize: 11, color: '#389e0d', fontStyle: 'italic' }}>→ {lead.next_action}</div>}
          {lead.primary_objection && <div style={{ marginTop: 2, fontSize: 11, color: '#d46b08' }}>⚠ {lead.primary_objection}</div>}
        </Col>

        <Col flex="none" style={{ textAlign: 'center', minWidth: 44 }}>
          <div style={{
            width: 38, height: 38, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700,
            background: lead.ai_score >= 70 ? '#f6ffed' : lead.ai_score >= 40 ? '#fff7e6' : '#fff2f0',
            color: lead.ai_score >= 70 ? '#52c41a' : lead.ai_score >= 40 ? '#fa8c16' : '#f5222d',
            border: `2px solid ${lead.ai_score >= 70 ? '#52c41a' : lead.ai_score >= 40 ? '#fa8c16' : '#f5222d'}`,
          }}>{Math.round(lead.ai_score || 0)}</div>
          <div style={{ fontSize: 9, color: '#999', marginTop: 2 }}>AI</div>
        </Col>

        <Col flex="none">
          <Space direction="vertical" size={4}>
            <Space size={4}>
              <Tooltip title="Call"><Button size="small" icon={<PhoneOutlined />} href={`tel:${lead.phone}`} disabled={!lead.phone} /></Tooltip>
              <Tooltip title="WhatsApp chat"><Button size="small" icon={<MessageOutlined />} style={{ background: '#25d366', borderColor: '#25d366', color: '#fff' }} onClick={() => onChat(lead)} /></Tooltip>
              <Tooltip title="View lead"><Button size="small" type="primary" icon={<EyeOutlined />} onClick={() => navigate(`/leads/${lead.lead_id}`)} /></Tooltip>
            </Space>
            <Space size={4}>
              <Button size="small" icon={<CheckCircleOutlined />} style={{ fontSize: 11 }} onClick={() => onLog(lead)}>Log call</Button>
              <Dropdown trigger={['click']} menu={{ items: snoozeItems, onClick: ({ key }) => onSnooze(lead, quickDates[Number(key)]) }}>
                <Tooltip title="Reschedule"><Button size="small" icon={<ScheduleOutlined />} aria-label="Reschedule" /></Tooltip>
              </Dropdown>
            </Space>
          </Space>
        </Col>
      </Row>
    </Card>
  );
}

// ── summary tile (click to open that tab) ─────────────────────────────────────
function Tile({ label, value, color, icon, active, onClick, hint }) {
  return (
    <button type="button" onClick={onClick} style={{
      all: 'unset', boxSizing: 'border-box', width: '100%', cursor: 'pointer', background: '#fff', borderRadius: 8,
      border: `1px solid ${active ? color : '#f0f0f0'}`, borderTop: `3px solid ${color}`, padding: '10px 14px', boxShadow: active ? `0 0 0 2px ${color}33` : 'none',
    }}>
      <div style={{ fontSize: 13, color: '#8c8c8c' }}>{icon} {label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color, lineHeight: 1.2 }}>{value == null ? '–' : value.toLocaleString('en-IN')}</div>
      {hint && <div style={{ fontSize: 11, color: '#bfbfbf' }}>{hint}</div>}
    </button>
  );
}

const EMPTY = {
  overdue: 'No overdue follow-ups 🎉',
  today: 'Nothing scheduled for today',
  upcoming: 'Nothing scheduled in the next 7 days',
  unscheduled: 'Every active lead has a follow-up date 🎉',
};

// ── page ──────────────────────────────────────────────────────────────────────
export default function FollowupTodayPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isAdmin = ['Super Admin', 'Manager', 'Team Leader'].includes(user?.role);

  const [tab, setTab] = useState('overdue');
  const [tabChosen, setTabChosen] = useState(false);
  const [assignedTo, setAssignedTo] = useState(undefined);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('priority');
  const [bucket, setBucket] = useState(null);
  const [status, setStatus] = useState(undefined);
  const [segment, setSegment] = useState(undefined);
  const [logLead, setLogLead] = useState(null);
  const [chatLead, setChatLead] = useState(null);

  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  const params = useMemo(() => {
    const p = { tab, sort };
    if (assignedTo) p.assigned_to = assignedTo;
    if (search) p.search = search;
    if (status) p.status = status;
    if (segment) p.segment = segment;
    if (bucket && tab === 'overdue') p.bucket = bucket;
    return p;
  }, [tab, sort, assignedTo, search, status, segment, bucket]);

  const { data, isLoading, isError, error, isFetching, refetch, fetchNextPage, hasNextPage, isFetchingNextPage, dataUpdatedAt } = useInfiniteQuery({
    queryKey: ['followups', params],
    queryFn: ({ pageParam = 0 }) => followupsAPI.list({ ...params, skip: pageParam, limit: PAGE }).then((r) => r.data),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.skip + PAGE < last.total ? last.skip + PAGE : undefined),
    staleTime: 20 * 1000,
    refetchInterval: 90 * 1000,    // picks up changes by others; the server answers from a 30 s cache
    placeholderData: (prev) => prev,
  });

  const items = useMemo(() => (data?.pages || []).flatMap((p) => p.items), [data]);
  const counts = data?.pages?.[0]?.counts;
  const buckets = data?.pages?.[0]?.buckets;
  const total = data?.pages?.[0]?.total ?? 0;

  // Open on the first tab that has something, unless the person already picked one.
  useEffect(() => {
    if (!tabChosen && counts && counts.overdue === 0 && counts.today > 0) setTab('today');
  }, [counts, tabChosen]);

  const { data: opts } = useQuery({
    queryKey: ['followup-counselors'],
    queryFn: () => leadsAPI.getFilterOptions().then((r) => r.data),
    staleTime: 10 * 60 * 1000,
    enabled: isAdmin,
  });

  const pickTab = (k) => { setTab(k); setTabChosen(true); setBucket(null); };

  // Take a lead off the visible list at once; the refetch afterwards brings the exact numbers.
  const dropFromList = (lead) => {
    queryClient.setQueriesData({ queryKey: ['followups'] }, (old) => {
      if (!old?.pages) return old;
      return {
        ...old,
        pages: old.pages.map((pg) => ({
          ...pg,
          items: pg.items.filter((x) => x.lead_id !== lead.lead_id),
          total: Math.max(0, pg.total - 1),
          counts: pg.counts ? { ...pg.counts, [tab]: Math.max(0, (pg.counts[tab] || 0) - 1) } : pg.counts,
        })),
      };
    });
    queryClient.invalidateQueries({ queryKey: ['followups'] });
    queryClient.invalidateQueries({ queryKey: ['leads'] });
  };

  const snooze = async (lead, q) => {
    try {
      await leadsAPI.update(lead.lead_id, { follow_up_date: q.get().toISOString() });
      message.success(`${lead.full_name}: follow-up moved to ${q.get().format('ddd DD MMM, hh:mm A')}`);
      dropFromList(lead);
    } catch (e) {
      message.error(errText(e, 'Could not reschedule - nothing was changed'));
    }
  };

  const clearFilters = () => { setSearchInput(''); setSearch(''); setStatus(undefined); setSegment(undefined); setBucket(null); };
  const hasFilters = !!(search || status || segment || bucket);
  const tabName = { overdue: 'Overdue', today: 'Due today', upcoming: 'Next 7 days', unscheduled: 'No follow-up set' }[tab];

  if (isError && !data) {
    return (
      <div style={{ padding: 24 }}>
        <Result status="warning" title="Couldn't load follow-ups" subTitle={errText(error, 'Please try again.')} extra={<Button type="primary" onClick={() => refetch()}>Retry</Button>} />
      </div>
    );
  }

  return (
    <div style={{ padding: 24, background: '#f0f2f5', minHeight: '100vh' }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}><CalendarOutlined style={{ color: '#1890ff', marginRight: 8 }} />Follow-ups</Title>
          <Text type="secondary">{dayjs().format('dddd, D MMMM YYYY')}{dataUpdatedAt ? ` · updated ${dayjs(dataUpdatedAt).format('hh:mm:ss A')}` : ''}</Text>
        </div>
        <Space wrap>
          {isAdmin && (
            <Select allowClear showSearch placeholder="All counselors" style={{ width: 200 }} value={assignedTo} onChange={(v) => setAssignedTo(v || undefined)}
              options={(opts?.assigned_to || []).map((n) => ({ value: n, label: n }))} optionFilterProp="label" />
          )}
          <Button icon={<ReloadOutlined spin={isFetching} />} onClick={() => refetch()}>Refresh</Button>
        </Space>
      </div>

      {isError && (
        <Alert type="warning" showIcon style={{ marginBottom: 12 }} message="Couldn't refresh - the list below may be out of date."
          action={<Button size="small" onClick={() => refetch()}>Retry</Button>} />
      )}

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}><Tile label="Overdue" value={counts?.overdue} color="#f5222d" icon={<WarningOutlined />} active={tab === 'overdue'} onClick={() => pickTab('overdue')} hint="date already passed" /></Col>
        <Col xs={12} md={6}><Tile label="Due today" value={counts?.today} color="#1890ff" icon={<CalendarOutlined />} active={tab === 'today'} onClick={() => pickTab('today')} /></Col>
        <Col xs={12} md={6}><Tile label="Next 7 days" value={counts?.upcoming} color="#722ed1" icon={<FieldTimeOutlined />} active={tab === 'upcoming'} onClick={() => pickTab('upcoming')} /></Col>
        <Col xs={12} md={6}><Tile label="No follow-up set" value={counts?.unscheduled} color="#fa8c16" icon={<ClockCircleOutlined />} active={tab === 'unscheduled'} onClick={() => pickTab('unscheduled')} hint="working leads with no next step" /></Col>
      </Row>

      <Card styles={{ body: { padding: 16 } }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
          <Title level={5} style={{ margin: 0, marginRight: 8 }}>{tabName}{counts ? ` (${(counts[tab] ?? 0).toLocaleString('en-IN')})` : ''}</Title>
          <Input allowClear prefix={<SearchOutlined />} placeholder="Search name, phone, email, course" style={{ width: 250 }} value={searchInput} onChange={(e) => setSearchInput(e.target.value)} />
          <Select value={sort} onChange={setSort} style={{ width: 170 }} options={SORTS.filter((s) => tab !== 'unscheduled' || s.value === 'priority')} />
          <Select allowClear placeholder="Status" style={{ width: 150 }} value={status} onChange={setStatus} options={QUICK_STATUSES.concat('Enrolled').map((s) => ({ value: s, label: s }))} />
          <Select allowClear placeholder="Segment" style={{ width: 120 }} value={segment} onChange={setSegment} options={['Hot', 'Warm', 'Cold'].map((s) => ({ value: s, label: s }))} />
          {hasFilters && <Button type="link" onClick={clearFilters}>Clear filters</Button>}
        </div>

        {tab === 'overdue' && buckets && (
          <div style={{ marginBottom: 12 }}>
            <Segmented
              value={bucket || 'all'} onChange={(v) => setBucket(v === 'all' ? null : v)}
              options={[{ value: 'all', label: 'All late' }, { value: '1-3', label: `1–3 days (${buckets['1-3']})` }, { value: '4-7', label: `4–7 days (${buckets['4-7']})` },
                { value: '8-30', label: `8–30 days (${buckets['8-30']})` }, { value: '30+', label: `30+ days (${buckets['30+']})` }]}
            />
            {(bucket === '30+' || (!bucket && buckets['30+'] > 0)) && (
              <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 6 }}>
                {buckets['30+']} lead{buckets['30+'] === 1 ? ' has' : 's have'} been waiting over a month. Reschedule them or close them so this list stays honest.
              </div>
            )}
          </div>
        )}

        {isLoading ? (
          <Skeleton active paragraph={{ rows: 8 }} />
        ) : items.length === 0 ? (
          <Empty description={hasFilters ? 'No leads match these filters' : EMPTY[tab]} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div style={{ opacity: isFetching && !isFetchingNextPage ? 0.8 : 1 }}>
            {items.map((l, i) => (
              <LeadRow key={l.id} lead={l} tab={tab} rank={sort === 'priority' && (tab === 'overdue' || tab === 'today') ? i : null}
                onLog={setLogLead} onChat={setChatLead} onSnooze={snooze} />
            ))}
            <div style={{ textAlign: 'center', marginTop: 12, color: '#8c8c8c', fontSize: 12 }}>
              Showing {items.length.toLocaleString('en-IN')} of {total.toLocaleString('en-IN')}
              {hasNextPage && (
                <div style={{ marginTop: 8 }}>
                  <Button loading={isFetchingNextPage} onClick={() => fetchNextPage()}>Show {Math.min(PAGE, total - items.length)} more</Button>
                </div>
              )}
            </div>
          </div>
        )}
      </Card>

      {logLead && <QuickActionModal key={logLead.lead_id} lead={logLead} onClose={() => setLogLead(null)} onDone={dropFromList} />}
      <ChatDrawer lead={chatLead} onClose={() => setChatLead(null)} />
    </div>
  );
}
