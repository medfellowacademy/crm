import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Tabs, Button, InputNumber, Input, Popconfirm, Spin, Empty, Result, Tooltip, message } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, CheckOutlined } from '@ant-design/icons';
import { vacancyAPI } from '../api/api';

const GREEN = '#16a34a';
const YELLOW = '#facc15';
const NAVY = '#0b3d91';

const errText = (e, fallback) => e?.response?.data?.detail || fallback;

function EditableTitle({ value, onSave }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef(null);

  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  useEffect(() => { if (editing) inputRef.current?.focus({ cursor: 'all' }); }, [editing]);

  const commit = () => {
    const v = draft.trim();
    setEditing(false);
    if (v && v !== value) onSave(v);
    else setDraft(value);
  };

  if (editing) {
    return (
      <Input
        ref={inputRef} value={draft} maxLength={200} size="large"
        onChange={(e) => setDraft(e.target.value)} onPressEnter={commit} onBlur={commit}
        onKeyDown={(e) => { if (e.key === 'Escape') { setDraft(value); setEditing(false); } }}
        suffix={<CheckOutlined onMouseDown={(e) => e.preventDefault()} onClick={commit} style={{ cursor: 'pointer', color: GREEN }} />}
        style={{ fontSize: 24, fontWeight: 700, maxWidth: 640 }}
      />
    );
  }
  return (
    <Tooltip title="Click to edit the course name">
      <div onClick={() => setEditing(true)} style={{ cursor: 'text', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
        <span className="vb-title">{value}</span>
        <EditOutlined style={{ color: '#64748b', fontSize: 16 }} />
      </div>
    </Tooltip>
  );
}

function Board({ board, canManage, onRename, onResize, onToggle, onDelete, saving }) {
  const seats = useMemo(() => new Set(board.enrolled_seats), [board.enrolled_seats]);
  const numbers = useMemo(() => Array.from({ length: board.total_seats }, (_, i) => i + 1), [board.total_seats]);

  return (
    <div>
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
        <div className="vb-course"><EditableTitle value={board.course_name} onSave={onRename} /></div>
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
          <span className="vb-hint">Click a seat to change it</span>
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
        {canManage && (
          <Popconfirm title="Delete this board?" description="This can't be undone." okText="Delete" okButtonProps={{ danger: true }} onConfirm={onDelete}>
            <Button danger icon={<DeleteOutlined />} size="small">Delete board</Button>
          </Popconfirm>
        )}
      </div>
    </div>
  );
}

const VacancyBoardPage = () => {
  const queryClient = useQueryClient();
  const role = useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}')?.role; } catch { return undefined; }
  }, []);
  const canManage = ['Super Admin', 'Manager'].includes(role);

  const [activeId, setActiveId] = useState(null);
  const [saving, setSaving] = useState(false);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['vacancy-boards'],
    queryFn: () => vacancyAPI.list().then((r) => r.data.boards),
    refetchInterval: 30000, // pick up other people's clicks
  });
  const boards = useMemo(() => data || [], [data]);
  const active = boards.find((b) => b.id === activeId) || boards[0];

  const replaceBoard = (updated) => queryClient.setQueryData(['vacancy-boards'], (old) =>
    (old || []).map((b) => (b.id === updated.id ? updated : b)));

  const toggle = useMutation({
    mutationFn: ({ id, seat }) => vacancyAPI.toggleSeat(id, seat).then((r) => r.data),
    onMutate: async ({ id, seat }) => {
      await queryClient.cancelQueries({ queryKey: ['vacancy-boards'] });
      const prev = queryClient.getQueryData(['vacancy-boards']);
      queryClient.setQueryData(['vacancy-boards'], (old) => (old || []).map((b) => {
        if (b.id !== id) return b;
        const set = new Set(b.enrolled_seats);
        if (set.has(seat)) set.delete(seat); else set.add(seat);
        const enrolled = set.size;
        return { ...b, enrolled_seats: [...set].sort((x, y) => x - y), enrolled, available: b.total_seats - enrolled,
          percent: Math.round((enrolled / b.total_seats) * 100) };
      }));
      return { prev };
    },
    onError: (e, _v, ctx) => { queryClient.setQueryData(['vacancy-boards'], ctx?.prev); message.error(errText(e, 'Could not update the seat')); },
    onSuccess: replaceBoard,
  });

  const patch = useMutation({
    mutationFn: ({ id, body }) => vacancyAPI.update(id, body).then((r) => r.data),
    onMutate: () => setSaving(true),
    onSettled: () => setSaving(false),
    onSuccess: replaceBoard,
    onError: (e) => message.error(errText(e, 'Could not save')),
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
        <Empty description="No vacancy boards yet">
          {canManage && <Button type="primary" icon={<PlusOutlined />} onClick={() => create.mutate()}>Create a board</Button>}
        </Empty>
      ) : (
        <>
          <Tabs
            type="card"
            activeKey={String(active.id)}
            onChange={(k) => setActiveId(Number(k))}
            items={boards.map((b) => ({ key: String(b.id), label: b.course_name.length > 32 ? `${b.course_name.slice(0, 30)}…` : b.course_name }))}
            tabBarExtraContent={canManage ? <Button size="small" icon={<PlusOutlined />} loading={create.isPending} onClick={() => create.mutate()}>New board</Button> : null}
          />
          <Board
            board={active} canManage={canManage} saving={saving}
            onRename={(name) => patch.mutate({ id: active.id, body: { course_name: name } })}
            onResize={(n) => patch.mutate({ id: active.id, body: { total_seats: n } })}
            onToggle={(seat) => toggle.mutate({ id: active.id, seat })}
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
.vb-toolbar { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-top:16px; color:#475569; }
.vb-meta { margin-left:auto; font-size:13px; color:#94a3b8; }
`;

export default VacancyBoardPage;
