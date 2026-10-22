import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Tabs, Button, InputNumber, Input, Popconfirm, Spin, Empty, Result, Tooltip, Dropdown, message } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, CheckOutlined, SaveOutlined, UndoOutlined, DownloadOutlined } from '@ant-design/icons';
import { vacancyAPI } from '../api/api';
import { downloadBoardPng, downloadBoardPdf } from '../utils/vacancyExport';

const GREEN = '#16a34a';
const YELLOW = '#facc15';
const NAVY = '#0b3d91';

const errText = (e, fallback) => e?.response?.data?.detail || fallback;

// ── Drafts: edits stay local until "Save changes" ───────────────────────────
const FIELDS = ['course_name', 'doctor_name', 'total_seats', 'enrolled_seats'];
const withStats = (b) => {
  const total = b.total_seats;
  const seats = [...new Set(b.enrolled_seats)].filter((n) => n >= 1 && n <= total).sort((x, y) => x - y);
  return { ...b, enrolled_seats: seats, enrolled: seats.length, available: Math.max(0, total - seats.length),
    percent: total ? Math.round((seats.length / total) * 100) : 0 };
};
const sameBoard = (a, b) => a.course_name === b.course_name && (a.doctor_name || '') === (b.doctor_name || '')
  && a.total_seats === b.total_seats && a.enrolled_seats.length === b.enrolled_seats.length
  && a.enrolled_seats.every((n, i) => n === b.enrolled_seats[i]);

function EditableTitle({ value, onSave, placeholder = 'Click to edit', className = 'vb-title', allowEmpty = false, fontSize = 24 }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef(null);

  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  useEffect(() => { if (editing) inputRef.current?.focus({ cursor: 'all' }); }, [editing]);

  const commit = () => {
    const v = draft.trim();
    setEditing(false);
    if ((v || allowEmpty) && v !== value) onSave(v);
    else setDraft(value);
  };

  if (editing) {
    return (
      <Input
        ref={inputRef} value={draft} maxLength={200} size="large" placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)} onPressEnter={commit} onBlur={commit}
        onKeyDown={(e) => { if (e.key === 'Escape') { setDraft(value); setEditing(false); } }}
        suffix={<CheckOutlined onMouseDown={(e) => e.preventDefault()} onClick={commit} style={{ cursor: 'pointer', color: GREEN }} />}
        style={{ fontSize, fontWeight: 700, maxWidth: 640 }}
      />
    );
  }
  return (
    <Tooltip title={placeholder}>
      <div onClick={() => setEditing(true)} style={{ cursor: 'text', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
        <span className={value ? className : `${className} vb-placeholder`}>{value || placeholder}</span>
        <EditOutlined style={{ color: '#64748b', fontSize: 14 }} />
      </div>
    </Tooltip>
  );
}

function Board({ board, dirty, saving, onRename, onDoctor, onResize, onToggle, onDelete, onSave, onDiscard }) {
  const seats = useMemo(() => new Set(board.enrolled_seats), [board.enrolled_seats]);
  const numbers = useMemo(() => Array.from({ length: board.total_seats }, (_, i) => i + 1), [board.total_seats]);
  const [exporting, setExporting] = useState(false);

  const exportAs = async ({ key }) => {
    setExporting(true);
    try {
      if (key === 'png') await downloadBoardPng(board); else await downloadBoardPdf(board);
    } catch (e) {
      message.error('Could not create the download');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      <div className={`vb-actions ${dirty ? 'is-dirty' : ''}`}>
        {dirty ? (
          <>
            <span className="vb-unsaved"><i /> You have unsaved changes</span>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={onSave}>Save changes</Button>
            <Button icon={<UndoOutlined />} disabled={saving} onClick={onDiscard}>Discard</Button>
          </>
        ) : (
          <span className="vb-saved"><CheckOutlined /> All changes saved</span>
        )}
        <Dropdown
          menu={{ onClick: exportAs, items: [
            { key: 'png', label: 'Download as image (PNG)' },
            { key: 'pdf', label: 'Download as PDF' },
          ] }}
          trigger={['click']}
        >
          <Button icon={<DownloadOutlined />} loading={exporting} style={{ marginLeft: 'auto' }}>Download</Button>
        </Dropdown>
      </div>

      <div className="vb-top">
        <img className="vb-logo" src="/medfellow-logo.png" alt="MedFellow Academy" />
        <div className="vb-banner">
          <div className="vb-big">ENROLLMENT</div>
          <div className="vb-big vb-yellow">VACANCY LIST</div>
        </div>
      </div>

      <div className="vb-tagline">
        <span>Limited Seats</span><i /><span>High Demand</span><i /><span>Be a Part of MedFellow</span>
      </div>

      <div className="vb-stats">
        <div className="vb-course">
          <EditableTitle value={board.course_name} onSave={onRename} placeholder="Click to edit the course name" />
          <div>
            <EditableTitle value={board.doctor_name} onSave={onDoctor} placeholder="Add doctor name" className="vb-doctor" allowEmpty fontSize={18} />
          </div>
        </div>
        <div className="vb-stat" style={{ borderColor: GREEN }}>
          <div className="vb-stat-num" style={{ color: GREEN }}>{board.enrolled}</div>
          <div className="vb-stat-label" style={{ color: GREEN }}>ENROLLED</div>
        </div>
        <div className="vb-stat" style={{ borderColor: '#eab308' }}>
          <div className="vb-stat-num" style={{ color: '#ca8a04' }}>{board.available}</div>
          <div className="vb-stat-label" style={{ color: '#ca8a04' }}>AVAILABLE</div>
        </div>
      </div>

      <div className="vb-capacity">
        <div className="vb-capacity-head"><span>Capacity filled</span><b>{board.percent}%</b></div>
        <div className="vb-bar"><div className="vb-bar-fill" style={{ width: `${board.percent}%` }} /></div>
        <div className="vb-legend">
          <span><i style={{ background: YELLOW }} /> Available</span>
          <span><i style={{ background: GREEN }} /> Enrolled</span>
          <span className="vb-hint">Click a seat to change it, then Save</span>
        </div>
      </div>

      <div className="vb-grid-wrap">
        <div className="vb-grid">
          {numbers.map((n) => {
            const enrolled = seats.has(n);
            return (
              <button
                key={n} type="button"
                className={`vb-seat ${enrolled ? 'is-enrolled' : 'is-available'}`}
                aria-pressed={enrolled}
                aria-label={`Seat ${n}: ${enrolled ? 'enrolled' : 'available'}`}
                onClick={() => onToggle(n)}
              >
                {n}
              </button>
            );
          })}
        </div>
      </div>

      <div className="vb-toolbar">
        <span>Total seats</span>
        <InputNumber key={`${board.id}-${board.total_seats}`} min={1} max={500} defaultValue={board.total_seats} disabled={saving}
          onBlur={(e) => {
            const v = Number(String(e.target.value).replace(/[^0-9]/g, ''));
            if (v >= 1 && v <= 500 && v !== board.total_seats) onResize(v);
          }}
          onPressEnter={(e) => e.target.blur()} />
        {board.updated_by && <span className="vb-meta">Last changed by {board.updated_by}</span>}
        {!board.is_mine && <span className="vb-meta" style={{ marginLeft: 0 }}>Owner: {board.owner_name || 'unassigned'}</span>}
        <Popconfirm title="Delete this board?" description="This can't be undone." okText="Delete" okButtonProps={{ danger: true }} onConfirm={onDelete}>
          <Button danger icon={<DeleteOutlined />} size="small">Delete board</Button>
        </Popconfirm>
      </div>
    </div>
  );
}

const VacancyBoardPage = () => {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState(null);
  const [drafts, setDrafts] = useState({});          // { [boardId]: edited copy of the board }

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['vacancy-boards'],
    queryFn: () => vacancyAPI.list().then((r) => r.data.boards),
    refetchInterval: 30000, // pick up other people's saved changes (never overwrites your draft)
  });
  const boards = useMemo(() => data || [], [data]);
  const active = boards.find((b) => b.id === activeId) || boards[0];

  const dirtyIds = useMemo(
    () => boards.filter((b) => drafts[b.id] && !sameBoard(withStats(drafts[b.id]), withStats(b))).map((b) => b.id),
    [boards, drafts]
  );
  const viewOf = (b) => (drafts[b.id] ? withStats({ ...b, ...drafts[b.id] }) : b);

  // warn before closing/reloading the tab with unsaved edits
  useEffect(() => {
    if (!dirtyIds.length) return undefined;
    const warn = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirtyIds.length]);

  const edit = (board, patch) => setDrafts((d) => {
    const current = d[board.id] ? { ...board, ...d[board.id] } : { ...board };
    let next = { ...current, ...patch };
    if (patch.total_seats != null) next.enrolled_seats = next.enrolled_seats.filter((n) => n <= patch.total_seats);
    next = withStats(next);
    const picked = Object.fromEntries(FIELDS.map((k) => [k, next[k]]));
    const copy = { ...d };
    if (sameBoard(withStats({ ...board, ...picked }), withStats(board))) delete copy[board.id]; else copy[board.id] = picked;
    return copy;
  });
  const toggleSeat = (board, n) => {
    const cur = viewOf(board);
    const set = new Set(cur.enrolled_seats);
    if (set.has(n)) set.delete(n); else set.add(n);
    edit(board, { enrolled_seats: [...set] });
  };
  const dropDraft = (id) => setDrafts((d) => { const c = { ...d }; delete c[id]; return c; });

  const replaceBoard = (updated) => queryClient.setQueryData(['vacancy-boards'], (old) =>
    (old || []).map((b) => (b.id === updated.id ? updated : b)));

  const save = useMutation({
    mutationFn: ({ id, draft }) => vacancyAPI.update(id, {
      course_name: draft.course_name, doctor_name: draft.doctor_name || '',
      total_seats: draft.total_seats, enrolled_seats: draft.enrolled_seats,
    }).then((r) => r.data),
    onSuccess: (updated) => { replaceBoard(updated); dropDraft(updated.id); message.success('Saved'); },
    onError: (e) => message.error(errText(e, 'Could not save — your changes are still here, try again')),
  });

  const create = useMutation({
    mutationFn: () => vacancyAPI.create({ course_name: 'New Course', total_seats: 30 }).then((r) => r.data),
    onSuccess: (b) => { queryClient.setQueryData(['vacancy-boards'], (old) => [...(old || []), b]); setActiveId(b.id); },
    onError: (e) => message.error(errText(e, 'Could not create the board')),
  });

  const remove = useMutation({
    mutationFn: (id) => vacancyAPI.remove(id),
    onSuccess: (_r, id) => {
      queryClient.setQueryData(['vacancy-boards'], (old) => (old || []).filter((b) => b.id !== id));
      dropDraft(id);
      setActiveId(null);
      message.success('Board deleted');
    },
    onError: (e) => message.error(errText(e, 'Could not delete the board')),
  });

  if (isError) {
    return <Result status="warning" title="Couldn't load the vacancy boards" extra={<Button type="primary" onClick={() => refetch()}>Retry</Button>} />;
  }
  if (isLoading) return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>;

  return (
    <div className="vb-page">
      <style>{CSS}</style>
      {boards.length === 0 ? (
        <Empty description="You don't have a vacancy board yet">
          <Button type="primary" icon={<PlusOutlined />} loading={create.isPending} onClick={() => create.mutate()}>Create my board</Button>
        </Empty>
      ) : (
        <>
          <Tabs
            type="card"
            activeKey={String(active.id)}
            onChange={(k) => setActiveId(Number(k))}
            items={boards.map((b) => {
              const name = b.course_name.length > 32 ? `${b.course_name.slice(0, 30)}…` : b.course_name;
              const label = b.is_mine ? name : `${name} · ${b.owner_name || 'unassigned'}`;
              return { key: String(b.id), label: dirtyIds.includes(b.id) ? <span>{label} <span className="vb-dot" title="Unsaved changes" /></span> : label };
            })}
            tabBarExtraContent={<Button size="small" icon={<PlusOutlined />} loading={create.isPending} onClick={() => create.mutate()}>New board</Button>}
          />
          <Board
            board={viewOf(active)} dirty={dirtyIds.includes(active.id)} saving={save.isPending}
            onRename={(name) => edit(active, { course_name: name })}
            onDoctor={(name) => edit(active, { doctor_name: name })}
            onResize={(n) => edit(active, { total_seats: n })}
            onToggle={(seat) => toggleSeat(active, seat)}
            onSave={() => save.mutate({ id: active.id, draft: viewOf(active) })}
            onDiscard={() => dropDraft(active.id)}
            onDelete={() => remove.mutate(active.id)}
          />
        </>
      )}
    </div>
  );
};

const CSS = `
.vb-page { max-width: 1100px; margin: 0 auto; }
.vb-top { display:flex; align-items:center; gap:20px; flex-wrap:wrap; }
.vb-logo { height: 84px; width:auto; mix-blend-mode: multiply; flex: 0 0 auto; }
.vb-banner { flex: 1 1 360px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center;
  background: linear-gradient(135deg, ${NAVY}, #1d5fc4); border-radius: 18px 18px 18px 44px; padding: 16px 32px; color:#fff; }
.vb-title { font-size: clamp(20px, 2.6vw, 30px); font-weight: 800; line-height: 1.2; color:${NAVY}; }
.vb-big { font-size: clamp(24px, 3.4vw, 38px); font-weight: 800; letter-spacing: .5px; line-height: 1.1; }
.vb-yellow { color: ${YELLOW}; }
.vb-doctor { font-size: clamp(15px, 1.8vw, 19px); font-weight: 600; color:#475569; }
.vb-placeholder { color:#94a3b8; font-weight:500; font-style:italic; }
.vb-tagline { display:flex; justify-content:center; align-items:center; gap:16px; flex-wrap:wrap; margin: 16px 0 20px; color:${NAVY}; font-weight:600; }
.vb-tagline i { width:1px; height:18px; background:#94a3b8; }
.vb-stats { display:flex; justify-content:center; align-items:center; gap:24px; margin-bottom: 18px; flex-wrap:wrap; }
.vb-course { flex: 1 1 280px; max-width: 520px; text-align:right; }
@media (max-width: 760px) { .vb-course { text-align:center; max-width:none; } }
.vb-stat { min-width: 150px; text-align:center; border:2px solid; border-radius:14px; padding: 10px 24px; background:#fff; box-shadow: 0 4px 14px rgba(0,0,0,.06); }
.vb-stat-num { font-size: 52px; font-weight: 800; line-height: 1; }
.vb-stat-label { font-size: 18px; font-weight: 800; letter-spacing:.5px; }
.vb-capacity { max-width: 900px; margin: 0 auto 18px; }
.vb-capacity-head { display:flex; justify-content:space-between; font-weight:700; color:${NAVY}; margin-bottom:6px; }
.vb-bar { height: 12px; border-radius: 999px; background:#e5e7eb; overflow:hidden; }
.vb-bar-fill { height:100%; border-radius:999px; background: linear-gradient(90deg, #22c55e, ${GREEN}); transition: width .35s ease; }
.vb-legend { display:flex; gap:22px; align-items:center; margin-top:10px; font-weight:600; color:${NAVY}; flex-wrap:wrap; }
.vb-legend i { display:inline-block; width:18px; height:18px; border-radius:5px; vertical-align:-3px; margin-right:6px; }
.vb-hint { margin-left:auto; font-weight:500; color:#64748b; font-size:13px; }
.vb-grid-wrap { background:#fff; border-radius:18px; padding:18px; box-shadow:0 6px 22px rgba(15,23,42,.08); }
.vb-grid { display:grid; grid-template-columns: repeat(10, 1fr); gap: 12px; }
@media (max-width: 760px) { .vb-grid { grid-template-columns: repeat(5, 1fr); } }
.vb-seat { appearance:none; border:0; cursor:pointer; height: 62px; border-radius:12px; font-size:20px; font-weight:700;
  transition: background .2s ease, color .2s ease, transform .12s ease, box-shadow .2s ease; box-shadow: 0 3px 8px rgba(0,0,0,.14); }
.vb-seat:hover { transform: translateY(-2px); }
.vb-seat:active { transform: scale(.92); }
.vb-seat:focus-visible { outline: 3px solid ${NAVY}; outline-offset: 2px; }
.vb-seat.is-enrolled { background: linear-gradient(180deg, #22c55e, ${GREEN}); color:#fff; }
.vb-seat.is-available { background: linear-gradient(180deg, #fde047, ${YELLOW}); color:#713f12; }
.vb-actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:10px 14px; margin-bottom:14px; border-radius:12px;
  background:#f1f5f9; border:1px solid transparent; position:sticky; top:0; z-index:5; }
.vb-actions.is-dirty { background:#fffbeb; border-color:#fcd34d; }
.vb-unsaved { font-weight:700; color:#92400e; display:inline-flex; align-items:center; gap:8px; margin-right:6px; }
.vb-unsaved i { width:10px; height:10px; border-radius:50%; background:#f59e0b; display:inline-block; }
.vb-saved { color:#15803d; font-weight:600; }
.vb-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:#f59e0b; vertical-align:middle; }
.vb-toolbar { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-top:16px; color:#475569; }
.vb-meta { margin-left:auto; font-size:13px; color:#94a3b8; }
`;

export default VacancyBoardPage;
