import React, { useState, useMemo, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  DndContext, DragOverlay, PointerSensor, TouchSensor, KeyboardSensor, useSensor, useSensors,
  useDroppable, pointerWithin, rectIntersection,
} from '@dnd-kit/core';
import { Button, Empty, Form, Input, Modal, Result, Select, Skeleton, Space, Switch, Tag, Tooltip, message } from 'antd';
import { ReloadOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons';
import { leadsAPI, pipelineAPI } from '../../api/api';
import { useAuth } from '../../context/AuthContext';
import { isFeatureEnabled } from '../../config/featureFlags';
import EnrollmentModal from '../../components/leads/EnrollmentModal';
import PipelineCard, { CardBody } from './PipelineCard';
import { applyMove, inrShort } from './pipelineUtils';

const { TextArea } = Input;

const LOSS_STATUSES = ['Not Interested', 'Not Answering', 'Junk', 'Dropped', 'TMT No Response'];
const NEEDS_REASON = new Set(['Not Interested', 'Junk', 'Dropped', 'TMT No Response']);   // same rule as the lead page
const LOSS_REASONS = [
  'Price too high', 'Went with competitor', 'Not the right course', 'Cannot take time off work', 'No response / Unreachable',
  'Not eligible', 'Needs more time', 'Financial constraints', 'Already enrolled elsewhere', 'Other',
];

const collision = (args) => {
  const hits = pointerWithin(args);
  return hits.length ? hits : rectIntersection(args);
};

const errText = (e, fallback) => e?.response?.data?.detail || e?.message || fallback;

// ── one column ───────────────────────────────────────────────────────────────
function StageColumn({ stage, cards, hasMore, loadingMore, onMore, stages, onOpen, onMove, dragDisabled }) {
  const { setNodeRef, isOver } = useDroppable({ id: stage.id });
  return (
    <div style={{ width: 300, flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ background: 'var(--bg-primary, #fff)', borderLeft: '1px solid var(--border, #e5e7eb)', borderRight: '1px solid var(--border, #e5e7eb)', borderBottom: '1px solid var(--border, #e5e7eb)', borderTop: `3px solid ${stage.color}`, borderRadius: '10px 10px 0 0', padding: '10px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 14 }}>{stage.name}</span>
          <span style={{ marginLeft: 'auto', background: 'var(--bg-secondary, #f3f4f6)', borderRadius: 12, padding: '0 9px', fontWeight: 700, fontSize: 12 }}>
            {stage.count.toLocaleString('en-IN')}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4, fontSize: 12, color: 'var(--text-tertiary, #6b7280)' }}>
          {stage.id !== 'Lost' && <span>{stage.probability}% odds</span>}
          {stage.value > 0 && <span style={{ fontWeight: 600, color: '#047857' }}>{inrShort(stage.value)}{stage.id === 'Enrolled' ? ' won' : ' weighted'}</span>}
          {stage.overdue > 0 && <Tag color="red" style={{ margin: 0, marginLeft: 'auto' }}>{stage.overdue} overdue</Tag>}
        </div>
      </div>
      <div
        ref={setNodeRef}
        style={{
          flex: 1, minHeight: 360, maxHeight: 'calc(100vh - 360px)', overflowY: 'auto', padding: 8,
          background: isOver ? 'rgba(59,130,246,.10)' : 'var(--bg-secondary, #f3f4f6)',
          borderLeft: `1px ${isOver ? 'dashed #3b82f6' : 'solid var(--border, #e5e7eb)'}`, borderRight: `1px ${isOver ? 'dashed #3b82f6' : 'solid var(--border, #e5e7eb)'}`, borderBottom: `1px ${isOver ? 'dashed #3b82f6' : 'solid var(--border, #e5e7eb)'}`, borderRadius: '0 0 10px 10px',
          transition: 'background .12s',
        }}
      >
        {cards.length === 0 ? (
          <div style={{ padding: '36px 8px', textAlign: 'center', color: 'var(--text-tertiary, #9ca3af)', fontSize: 13 }}>
            {isOver ? 'Drop here' : 'No leads in this stage'}
          </div>
        ) : cards.map((c) => (
          <PipelineCard key={c.lead_id} card={c} stages={stages} onOpen={onOpen} onMove={onMove} dragDisabled={dragDisabled} />
        ))}
        {hasMore && (
          <Button block size="small" loading={loadingMore} onClick={onMore} style={{ marginTop: 4 }}>
            Show more ({(stage.count - cards.length).toLocaleString('en-IN')} left)
          </Button>
        )}
      </div>
    </div>
  );
}

// ── summary tiles ────────────────────────────────────────────────────────────
function Tile({ label, value, sub, color, onClick, active }) {
  return (
    <button
      type="button" onClick={onClick} disabled={!onClick}
      style={{
        all: 'unset', boxSizing: 'border-box', cursor: onClick ? 'pointer' : 'default', flex: '1 1 150px', minWidth: 140,
        background: 'var(--bg-primary, #fff)', border: `1px solid ${active ? color : 'var(--border, #e5e7eb)'}`, borderRadius: 10, padding: '10px 14px',
        boxShadow: active ? `0 0 0 2px ${color}33` : 'none',
      }}
    >
      <div style={{ fontSize: 12, color: 'var(--text-tertiary, #6b7280)' }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: color || 'inherit' }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-tertiary, #9ca3af)' }}>{sub}</div>}
    </button>
  );
}

// ── "why is this lead being closed" dialog ────────────────────────────────────
function LossModal({ open, card, saving, onSave, onCancel }) {
  const [form] = Form.useForm();
  const submit = async () => {
    const v = await form.validateFields().catch(() => null);
    if (v) onSave(v);
  };
  return (
    <Modal
      open={open} okText="Confirm & save" okButtonProps={{ danger: true }} confirmLoading={saving}
      onOk={submit} onCancel={onCancel} destroyOnHidden width={460} forceRender
      title={<span><WarningOutlined style={{ color: '#f5222d', marginRight: 8 }} />Why is {card?.name || 'this lead'} being closed?</span>}
      afterClose={() => form.resetFields()}
    >
      <Form form={form} layout="vertical" initialValues={{ status: 'Not Interested' }}>
        <Form.Item name="status" label="Outcome" rules={[{ required: true }]}>
          <Select options={LOSS_STATUSES.map((s) => ({ value: s, label: s }))} />
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(a, b) => a.status !== b.status}>
          {({ getFieldValue }) => (
            <Form.Item name="loss_reason" label="Reason" rules={[{ required: NEEDS_REASON.has(getFieldValue('status')), message: 'Please pick a reason' }]}>
              <Select allowClear placeholder="Select the main reason" options={LOSS_REASONS.map((r) => ({ value: r, label: r }))} />
            </Form.Item>
          )}
        </Form.Item>
        <Form.Item name="loss_note" label="Notes (optional)"><TextArea rows={3} /></Form.Item>
      </Form>
    </Modal>
  );
}

// ── the board ────────────────────────────────────────────────────────────────
const DragDropPipeline = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isCounselor = user?.role === 'Counselor';
  const dragEnabled = isFeatureEnabled('DRAG_DROP_PIPELINE');

  const [searchInput, setSearchInput] = useState('');
  const [filters, setFilters] = useState({ search: '', assigned_to: undefined, course: undefined, country: undefined, source: undefined, overdue_only: false });
  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => (f.search === searchInput.trim() ? f : { ...f, search: searchInput.trim() })), 350);
    return () => clearTimeout(t);
  }, [searchInput]);
  const setFilter = (k, v) => setFilters((f) => ({ ...f, [k]: v || undefined }));

  const params = useMemo(() => {
    const p = {};
    Object.entries(filters).forEach(([k, v]) => { if (v) p[k] = v; });
    return p;
  }, [filters]);
  const boardKey = useMemo(() => ['pipeline-board', params], [params]);
  const activeFilterCount = Object.keys(params).length;

  const { data: board, isLoading, isError, error, isFetching, refetch } = useQuery({
    queryKey: boardKey,
    queryFn: () => pipelineAPI.board(params).then((r) => r.data),
    staleTime: 30 * 1000,
    placeholderData: (prev) => prev,
  });
  const { data: opts } = useQuery({
    queryKey: ['pipeline-filter-options'],
    queryFn: () => leadsAPI.getFilterOptions().then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  // Cards fetched with "Show more", per stage. Cleared whenever the board is reloaded or re-filtered.
  const [more, setMore] = useState({});
  const [loadingMore, setLoadingMore] = useState({});
  useEffect(() => { setMore({}); }, [board?.generated_at, boardKey]);

  const stages = board?.stages || [];
  const columnCards = (stage) => {
    const seen = new Set();
    return [...stage.cards, ...(more[stage.id] || [])].filter((c) => (seen.has(c.lead_id) ? false : (seen.add(c.lead_id), true)));
  };

  const loadMore = async (stage) => {
    const have = columnCards(stage).length;
    setLoadingMore((m) => ({ ...m, [stage.id]: true }));
    try {
      const res = await pipelineAPI.stage(stage.id, { ...params, skip: have, limit: 30 });
      setMore((m) => ({ ...m, [stage.id]: [...(m[stage.id] || []), ...res.data.cards] }));
    } catch (e) {
      message.error(errText(e, 'Could not load more leads'));
    } finally {
      setLoadingMore((m) => ({ ...m, [stage.id]: false }));
    }
  };

  // ── moving a lead ──────────────────────────────────────────────────────────
  const refreshBoards = () => {
    queryClient.invalidateQueries({ queryKey: ['pipeline-board'] });
    queryClient.invalidateQueries({ queryKey: ['leads'] });
  };

  const showSaved = (card, toStage, onUndo) => {
    const name = stages.find((s) => s.id === toStage)?.name || toStage;
    message.success({
      duration: 6,
      content: (
        <span>
          {card.name} → {name}
          {onUndo && <Button type="link" size="small" onClick={onUndo} style={{ paddingLeft: 8 }}>Undo</Button>}
        </span>
      ),
    });
  };

  // toStage = the column it lands in; status = what is saved (the same, unless undoing a move out of
  // "Lost", where the lead goes back to its exact old status such as "Junk").
  const plainMove = async (card, toStage, { undo = true, status = toStage } = {}) => {
    const snapshot = queryClient.getQueryData(boardKey);
    queryClient.setQueryData(boardKey, (b) => applyMove(b, card, toStage));
    setMore((m) => ({ ...m, [card.stage]: (m[card.stage] || []).filter((c) => c.lead_id !== card.lead_id) }));
    try {
      await leadsAPI.update(card.lead_id, { status });
      const back = () => plainMove({ ...card, stage: toStage, status }, card.stage, { undo: false, status: card.status || card.stage });
      showSaved(card, toStage, undo ? back : null);
      refreshBoards();
    } catch (e) {
      queryClient.setQueryData(boardKey, snapshot);
      message.error(errText(e, 'Could not move the lead - nothing was changed'));
    }
  };

  const [enroll, setEnroll] = useState({ open: false, lead: null, card: null, saving: false });
  const [loss, setLoss] = useState({ open: false, card: null, saving: false });

  const openEnrollment = async (card) => {
    const hide = message.loading('Opening enrollment…', 0);
    try {
      const res = await leadsAPI.getById(card.lead_id);
      setEnroll({ open: true, lead: res.data, card, saving: false });
    } catch (e) {
      message.error(errText(e, 'Could not open this lead'));
    } finally {
      hide();
    }
  };

  const saveEnrollment = async (data) => {
    setEnroll((s) => ({ ...s, saving: true }));
    try {
      await leadsAPI.update(enroll.card.lead_id, data);
      showSaved(enroll.card, 'Enrolled');
      setEnroll({ open: false, lead: null, card: null, saving: false });
      refreshBoards();
    } catch (e) {
      setEnroll((s) => ({ ...s, saving: false }));
      message.error(errText(e, 'Could not save the enrollment - nothing was changed'));
    }
  };

  const openLoss = (card) => setLoss({ open: true, card, saving: false });

  const saveLoss = async (v) => {
    setLoss((st) => ({ ...st, saving: true }));
    try {
      await leadsAPI.update(loss.card.lead_id, { status: v.status, loss_reason: v.loss_reason || undefined, loss_note: v.loss_note || '' });
      showSaved(loss.card, 'Lost');
      setLoss({ open: false, card: null, saving: false });
      refreshBoards();
    } catch (e) {
      setLoss((st) => ({ ...st, saving: false }));
      message.error(errText(e, 'Could not save - nothing was changed'));
    }
  };

  const requestMove = (card, toStage) => {
    if (!toStage || toStage === card.stage) return;
    if (toStage === 'Enrolled') { openEnrollment(card); return; }
    if (toStage === 'Lost') { openLoss(card); return; }
    if (card.stage === 'Enrolled') {
      Modal.confirm({
        title: `Move ${card.name} out of Enrolled?`,
        content: 'Their payment plan and fees stay on the lead, but they will no longer count as a sale until they are enrolled again.',
        okText: 'Move anyway', okButtonProps: { danger: true },
        onOk: () => plainMove(card, toStage, { undo: false }),
      });
      return;
    }
    plainMove(card, toStage);
  };

  // ── drag and drop ──────────────────────────────────────────────────────────
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 220, tolerance: 8 } }),
    useSensor(KeyboardSensor),
  );
  const [dragging, setDragging] = useState(null);
  const onDragEnd = ({ active, over }) => {
    setDragging(null);
    const card = active?.data?.current?.card;
    if (card && over?.id) requestMove(card, String(over.id));
  };

  // ── render ─────────────────────────────────────────────────────────────────
  if (isError && !board) {
    return (
      <Result
        status="warning" title="Couldn't load the pipeline" subTitle={errText(error, 'Please try again.')}
        extra={<Button type="primary" onClick={() => refetch()}>Retry</Button>}
      />
    );
  }

  const t = board?.totals;
  const opt = (k) => (opts?.[k] || []).map((v) => ({ value: v, label: v }));

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Sales Pipeline</h2>
        <span style={{ color: 'var(--text-tertiary, #6b7280)', fontSize: 13 }}>
          Drag a card to change its stage, or use the ⇄ button on a card.
          {!dragEnabled && ' (Drag and drop is switched off - use the ⇄ button.)'}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <Tile label="Open leads" value={t ? t.open_count.toLocaleString('en-IN') : '–'} sub="in active stages" color="#2563eb" />
        <Tile label="Pipeline (weighted)" value={t ? inrShort(t.weighted_value) : '–'} sub={t ? `${inrShort(t.open_value)} unweighted` : ''} color="#7c3aed" />
        <Tile
          label="Overdue follow-ups" value={t ? t.overdue.toLocaleString('en-IN') : '–'} sub={filters.overdue_only ? 'showing only these · click to clear' : 'click to show only these'}
          color="#dc2626" active={filters.overdue_only} onClick={() => setFilter('overdue_only', !filters.overdue_only)}
        />
        <Tile label="Won (all time)" value={t ? t.won_count.toLocaleString('en-IN') : '–'} sub={t ? inrShort(t.won_value) : ''} color="#047857" />
        <Tile label="Lost / inactive" value={t ? t.lost_count.toLocaleString('en-IN') : '–'} color="#6b7280" />
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
        <Input
          allowClear prefix={<SearchOutlined />} placeholder="Search name, phone, email or lead ID" style={{ width: 280 }}
          value={searchInput} onChange={(e) => setSearchInput(e.target.value)}
        />
        {!isCounselor && (
          <Select allowClear showSearch placeholder="Counselor" style={{ width: 170 }} options={opt('assigned_to')} value={filters.assigned_to} onChange={(v) => setFilter('assigned_to', v)} optionFilterProp="label" />
        )}
        <Select allowClear showSearch placeholder="Course" style={{ width: 210 }} options={opt('courses')} value={filters.course} onChange={(v) => setFilter('course', v)} optionFilterProp="label" />
        <Select allowClear showSearch placeholder="Country" style={{ width: 150 }} options={opt('countries')} value={filters.country} onChange={(v) => setFilter('country', v)} optionFilterProp="label" />
        <Select allowClear showSearch placeholder="Source" style={{ width: 150 }} options={opt('sources')} value={filters.source} onChange={(v) => setFilter('source', v)} optionFilterProp="label" />
        <Tooltip title="Only leads whose follow-up date has passed">
          <Space size={6}><Switch size="small" checked={filters.overdue_only} onChange={(v) => setFilter('overdue_only', v)} /><span style={{ fontSize: 13 }}>Overdue only</span></Space>
        </Tooltip>
        {activeFilterCount > 0 && (
          <Button type="link" onClick={() => { setSearchInput(''); setFilters({ search: '', overdue_only: false }); }}>Clear filters ({activeFilterCount})</Button>
        )}
        <Button style={{ marginLeft: 'auto' }} icon={<ReloadOutlined spin={isFetching} />} onClick={() => refetch()}>Refresh</Button>
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', gap: 12, overflow: 'hidden' }}>
          {[0, 1, 2, 3].map((i) => <div key={i} style={{ width: 300, flexShrink: 0 }}><Skeleton active paragraph={{ rows: 8 }} /></div>)}
        </div>
      ) : stages.every((s) => s.count === 0) ? (
        <Empty description={activeFilterCount ? 'No leads match these filters.' : 'No leads yet.'} />
      ) : (
        <DndContext sensors={sensors} collisionDetection={collision} onDragStart={(e) => setDragging(e.active?.data?.current?.card || null)} onDragCancel={() => setDragging(null)} onDragEnd={onDragEnd}>
          <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 12, opacity: isFetching && !isLoading ? 0.85 : 1 }}>
            {stages.map((stage) => {
              const cards = columnCards(stage);
              return (
                <StageColumn
                  key={stage.id} stage={stage} cards={cards} stages={stages}
                  hasMore={cards.length < stage.count} loadingMore={!!loadingMore[stage.id]} onMore={() => loadMore(stage)}
                  onOpen={(c) => navigate(`/leads/${c.lead_id}`)} onMove={requestMove} dragDisabled={!dragEnabled}
                />
              );
            })}
          </div>
          <DragOverlay dropAnimation={null}>
            {dragging ? <div style={{ width: 284 }}><CardBody card={dragging} stages={stages} dragging /></div> : null}
          </DragOverlay>
        </DndContext>
      )}

      {/* Enrolling needs the fee and payment plan, exactly as on the lead page */}
      <EnrollmentModal
        open={enroll.open} lead={enroll.lead} loading={enroll.saving}
        onCancel={() => setEnroll({ open: false, lead: null, card: null, saving: false })} onSave={saveEnrollment}
      />

      <LossModal
        open={loss.open} card={loss.card} saving={loss.saving}
        onSave={saveLoss} onCancel={() => setLoss({ open: false, card: null, saving: false })}
      />
    </div>
  );
};

export default DragDropPipeline;
