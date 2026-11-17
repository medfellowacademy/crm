import React from 'react';
import { Avatar, Button, Dropdown, Tag, Tooltip } from 'antd';
import { ArrowRightOutlined, PhoneOutlined, WhatsAppOutlined, SwapOutlined } from '@ant-design/icons';
import { useDraggable } from '@dnd-kit/core';
import { followUpInfo, initials, inrShort, scoreColor, whatsappLink } from './pipelineUtils';

const stop = (e) => e.stopPropagation();

// The card itself. Used in the column (draggable) and in the drag overlay (static copy).
export function CardBody({ card, stages, onOpen, onMove, dragging = false }) {
  const fu = followUpInfo(card);
  const wa = whatsappLink(card.phone, card.country);
  const moveItems = (stages || []).filter((s) => s.id !== card.stage).map((s) => ({
    key: s.id,
    label: (<span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 4, background: s.color, marginRight: 8 }} />{s.name}</span>),
  }));
  return (
    <div style={{
      background: 'var(--bg-primary, #fff)',
      borderTop: `1px solid ${card.overdue ? '#fecaca' : 'var(--border, #e5e7eb)'}`, borderRight: `1px solid ${card.overdue ? '#fecaca' : 'var(--border, #e5e7eb)'}`,
      borderBottom: `1px solid ${card.overdue ? '#fecaca' : 'var(--border, #e5e7eb)'}`,
      borderLeft: `3px solid ${card.overdue ? '#ef4444' : 'var(--border, #e5e7eb)'}`, borderRadius: 8, padding: '10px 12px',
      boxShadow: dragging ? '0 12px 28px rgba(0,0,0,.18)' : '0 1px 2px rgba(0,0,0,.04)', cursor: dragging ? 'grabbing' : 'grab',
    }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <button
            type="button" onPointerDown={stop} onClick={() => onOpen?.(card)}
            style={{ all: 'unset', cursor: 'pointer', fontWeight: 600, fontSize: 13, color: 'var(--text-primary, #111827)', display: 'block', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            title="Open lead"
          >
            {card.name || 'Unknown lead'}
          </button>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary, #6b7280)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {[card.course, card.country].filter(Boolean).join(' · ') || card.email || card.phone || 'No details'}
          </div>
        </div>
        <Tooltip title={`AI score ${card.score}`}>
          <span style={{ fontSize: 11, fontWeight: 700, color: scoreColor(card.score), border: `1px solid ${scoreColor(card.score)}`, borderRadius: 10, padding: '0 7px', lineHeight: '18px' }}>
            {Math.round(card.score)}
          </span>
        </Tooltip>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8, alignItems: 'center' }}>
        {fu && <Tooltip title={fu.title}><Tag color={fu.color} style={{ margin: 0 }}>{fu.text}</Tag></Tooltip>}
        {card.idle_days != null && card.idle_days >= 7 && card.stage !== 'Enrolled' && card.stage !== 'Lost' && (
          <Tooltip title="Days since this lead was last contacted">
            <Tag color={card.idle_days >= 14 ? 'volcano' : 'default'} style={{ margin: 0 }}>Idle {card.idle_days}d</Tag>
          </Tooltip>
        )}
        {card.value > 0 && <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 600, color: '#047857' }}>{inrShort(card.value)}</span>}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
        <Tooltip title={card.owner || 'Unassigned'}>
          <Avatar size={20} style={{ background: card.owner ? '#e0ecff' : '#f3f4f6', color: card.owner ? '#1d4ed8' : '#9ca3af', fontSize: 10, fontWeight: 700 }}>
            {card.owner ? initials(card.owner) : '–'}
          </Avatar>
        </Tooltip>
        <span style={{ fontSize: 12, color: 'var(--text-secondary, #6b7280)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {card.owner || 'Unassigned'}
        </span>
        <span onPointerDown={stop} style={{ display: 'inline-flex', gap: 2 }}>
          {card.phone && <Tooltip title="Call"><Button size="small" type="text" icon={<PhoneOutlined />} href={`tel:${card.phone}`} aria-label="Call" /></Tooltip>}
          {wa && <Tooltip title="WhatsApp"><Button size="small" type="text" icon={<WhatsAppOutlined style={{ color: '#16a34a' }} />} href={wa} target="_blank" rel="noopener noreferrer" aria-label="WhatsApp" /></Tooltip>}
          <Dropdown trigger={['click']} menu={{ items: moveItems, onClick: ({ key }) => onMove?.(card, key) }}>
            <Tooltip title="Move to…"><Button size="small" type="text" icon={<SwapOutlined />} aria-label="Move to another stage" /></Tooltip>
          </Dropdown>
          <Tooltip title="Open lead"><Button size="small" type="text" icon={<ArrowRightOutlined />} onClick={() => onOpen?.(card)} aria-label="Open lead" /></Tooltip>
        </span>
      </div>
    </div>
  );
}

export default function PipelineCard({ card, stages, onOpen, onMove, dragDisabled }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: card.lead_id, data: { card }, disabled: dragDisabled });
  return (
    <div ref={setNodeRef} {...attributes} {...listeners} style={{ opacity: isDragging ? 0.35 : 1, touchAction: 'manipulation', marginBottom: 8 }}>
      <CardBody card={card} stages={stages} onOpen={onOpen} onMove={onMove} />
    </div>
  );
}
