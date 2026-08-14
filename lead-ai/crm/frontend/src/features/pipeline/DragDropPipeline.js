import React, { useState, useMemo } from 'react';
import { DndContext, closestCorners, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { motion } from 'framer-motion';
import { GripVertical, TrendingUp, DollarSign, AlertCircle } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { leadsAPI } from '../../api/api';
import { AIScoreTooltip } from '../../components/ai/AIInsightCard';
import { TableSkeleton } from '../../components/ui/Skeletons';
import { isFeatureEnabled } from '../../config/featureFlags';

// ── CRM Status ↔ Pipeline Stage mapping ─────────────────────────────────────
// The DB stores `status` (LeadStatus enum in the backend: Fresh, Follow Up,
// Warm, Hot, Not Interested, Junk, Not Answering, Enrolled, Will Enroll
// Later, Dropped). These stage ids MUST match those exactly — any status not
// listed here used to silently fall back to "Fresh", which meant Warm/Hot
// leads and every terminal status (Not Interested/Junk/Not Answering/
// Dropped — ~75% of all leads) were miscounted into the Fresh column while
// dragging a card into a stage without a matching backend status silently
// failed (pydantic rejects unknown enum values).
const PIPELINE_STAGES = [
  { id: 'Fresh',              name: 'Fresh Leads',       color: '#6b7280', probability: 5   },
  { id: 'Follow Up',          name: 'Follow Up',         color: '#3b82f6', probability: 25  },
  { id: 'Warm',               name: 'Warm',               color: '#f59e0b', probability: 45  },
  { id: 'Hot',                name: 'Hot',                color: '#ef4444', probability: 70  },
  { id: 'Will Enroll Later',  name: 'Will Enroll Later',  color: '#8b5cf6', probability: 85  },
  { id: 'Enrolled',           name: 'Enrolled / Won',     color: '#10b981', probability: 100 },
];

// Terminal/negative statuses collapse into one "Lost" column so every lead
// has a definite, correct home instead of being dumped into Fresh.
const LOST_STAGE = { id: 'Lost', name: 'Lost / Inactive', color: '#9ca3af', probability: 0 };
const LOST_STATUSES = new Set(['Not Interested', 'Not Answering', 'Junk', 'Dropped']);

const FALLBACK_STAGE = 'Fresh';

function resolveStage(lead) {
  // Normalise case so data-entry inconsistencies (e.g. "junk" vs "Junk")
  // still land in the right column instead of falling back to Fresh.
  const raw = (lead.status || FALLBACK_STAGE).trim();
  const st = PIPELINE_STAGES.find(s => s.id.toLowerCase() === raw.toLowerCase())?.id
    || [...LOST_STATUSES].find(s => s.toLowerCase() === raw.toLowerCase());
  if (st && LOST_STATUSES.has(st)) return LOST_STAGE.id;
  return st || FALLBACK_STAGE;
}

// ── Draggable Lead Card ──────────────────────────────────────────────────────
const DraggableLeadCard = ({ lead, stage }) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: lead.lead_id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  // Won deals show the real closed amount (actual_revenue, set at enrollment)
  // rather than the pre-sale estimate — expected_revenue is often stale/zero
  // by the time a lead is actually enrolled.
  const expectedRevenue = stage.id === 'Enrolled'
    ? (lead.actual_revenue || 0)
    : (lead.expected_revenue || 0) * (stage.probability / 100);
  const segment = lead.ai_segment || 'Cold';

  return (
    <div ref={setNodeRef} style={style}>
      <motion.div
        whileHover={{ y: -2, boxShadow: '0 8px 16px var(--shadow)' }}
        style={{
          background: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: 16,
          marginBottom: 12,
          cursor: 'grab',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'start', gap: 12 }}>
          {/* Drag Handle */}
          <div
            {...attributes}
            {...listeners}
            style={{ color: 'var(--text-tertiary)', cursor: 'grab', padding: 4 }}
          >
            <GripVertical size={16} />
          </div>

          {/* Lead Info */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {lead.full_name || 'Unknown Lead'}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginBottom: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {lead.email || lead.phone || 'No contact'}
            </div>

            <div style={{ display: 'flex', gap: 16, fontSize: 'var(--text-xs)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <TrendingUp size={12} style={{ color: 'var(--accent)' }} />
                <AIScoreTooltip score={lead.ai_score || 0} />
              </div>
              {expectedRevenue > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <DollarSign size={12} style={{ color: 'var(--success)' }} />
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                    ₹{expectedRevenue.toLocaleString('en-IN')}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Segment Badge */}
          <div style={{
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: 10,
            fontWeight: 600,
            flexShrink: 0,
            background: segment === 'Hot' ? '#fef2f2' : segment === 'Warm' ? '#fef3c7' : '#f0fdf4',
            color:      segment === 'Hot' ? '#ef4444' : segment === 'Warm' ? '#f59e0b' : '#10b981',
          }}>
            {segment.toUpperCase()}
          </div>
        </div>
      </motion.div>
    </div>
  );
};

// ── Pipeline Stage Column ────────────────────────────────────────────────────
const StageColumn = ({ stage, leads }) => {
  const totalValue = leads.reduce(
    (sum, lead) => sum + (
      stage.id === 'Enrolled'
        ? (lead.actual_revenue || 0)
        : (lead.expected_revenue || 0) * (stage.probability / 100)
    ),
    0
  );

  return (
    <div style={{
      background: 'var(--bg-secondary)',
      borderRadius: 12,
      padding: 16,
      minHeight: 600,
      width: 280,
      flexShrink: 0,
    }}>
      {/* Stage Header */}
      <div style={{ marginBottom: 16, paddingBottom: 12, borderBottom: '2px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <div style={{ width: 12, height: 12, borderRadius: '50%', background: stage.color }} />
          <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
            {stage.name}
          </h3>
          <span style={{
            marginLeft: 'auto',
            background: 'var(--bg-primary)',
            padding: '2px 8px',
            borderRadius: 12,
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            color: 'var(--text-secondary)',
          }}>
            {leads.length}
          </span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
          <span>Win Probability: {stage.probability}%</span>
          {totalValue > 0 && (
            <span style={{ fontWeight: 600, color: 'var(--success)' }}>
              ₹{totalValue.toLocaleString('en-IN')}
            </span>
          )}
        </div>
      </div>

      {/* Lead Cards */}
      <SortableContext items={leads.map(l => l.lead_id)} strategy={verticalListSortingStrategy}>
        <div style={{ minHeight: 400 }}>
          {leads.length === 0 ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
              No leads in this stage
            </div>
          ) : (
            leads.map(lead => (
              <DraggableLeadCard key={lead.lead_id} lead={lead} stage={stage} />
            ))
          )}
        </div>
      </SortableContext>
    </div>
  );
};

// ── Main Pipeline Component ──────────────────────────────────────────────────
const DragDropPipeline = () => {
  const queryClient = useQueryClient();
  // optimistic overrides: lead_id → new status
  const [overrides, setOverrides] = useState({});

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  // Fetch all leads for the pipeline view. 10000 is the backend's hard cap
  // per request (supabase_data_layer.get_leads effective_limit); `total`
  // from the response tells us honestly if the DB has grown past that so
  // the UI can say so instead of silently under-counting.
  const { data: pipelineResponse, isLoading, isError } = useQuery({
    queryKey: ['pipeline-leads'],
    queryFn: () => leadsAPI.getAll({ limit: 10000, skip: 0 }).then(res => res.data || { leads: [], total: 0 }),
    staleTime: 2 * 60 * 1000,
  });
  const leadsData = pipelineResponse?.leads || [];
  const totalLeads = pipelineResponse?.total || 0;

  // Update lead status mutation — sends `status` (the real DB field)
  const updateStatusMutation = useMutation({
    mutationFn: ({ leadId, newStatus }) => leadsAPI.update(leadId, { status: newStatus }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipeline-leads'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (_err, { leadId }) => {
      // Roll back the optimistic override on failure
      setOverrides(prev => {
        const next = { ...prev };
        delete next[leadId];
        return next;
      });
    },
  });

  const ALL_STAGES = useMemo(() => [...PIPELINE_STAGES, LOST_STAGE], []);

  // Group leads into stage columns (with optimistic overrides applied)
  const pipelineData = useMemo(() => {
    const grouped = Object.fromEntries(ALL_STAGES.map(s => [s.id, []]));
    (leadsData || []).forEach(lead => {
      const effectiveStatus = overrides[lead.lead_id] ?? resolveStage(lead);
      if (grouped[effectiveStatus]) {
        grouped[effectiveStatus].push(lead);
      }
    });
    return grouped;
  }, [leadsData, overrides, ALL_STAGES]);

  const handleDragEnd = (event) => {
    const { active, over } = event;
    if (!over) return;

    const activeLeadId = active.id;          // lead_id string
    const targetStageId = over.id;           // stage id OR lead_id of another card

    // Resolve the stage the card was dropped onto
    const overStage =
      ALL_STAGES.find(s => s.id === targetStageId)?.id ||
      Object.keys(pipelineData).find(stageId =>
        pipelineData[stageId].some(l => l.lead_id === targetStageId)
      );

    const currentStage = Object.keys(pipelineData).find(stageId =>
      pipelineData[stageId].some(l => l.lead_id === activeLeadId)
    );

    if (overStage && overStage !== currentStage) {
      // "Lost" is a UI-only bucket (4 real statuses collapsed into one column) —
      // not a valid backend LeadStatus, so dropping here needs a concrete status.
      // "Not Interested" is the most common lost reason and matches what the
      // Leads page itself defaults to for this kind of bulk disposition.
      const newStatus = overStage === LOST_STAGE.id ? 'Not Interested' : overStage;
      // Optimistic update — UI responds instantly, API call happens in background
      setOverrides(prev => ({ ...prev, [activeLeadId]: overStage }));
      updateStatusMutation.mutate({ leadId: activeLeadId, newStatus });
    }
  };

  if (isLoading) return <TableSkeleton rows={8} />;

  if (isError) {
    return (
      <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-secondary)' }}>
        <AlertCircle size={40} style={{ marginBottom: 12, color: '#ef4444' }} />
        <p>Failed to load pipeline data. Please refresh the page.</p>
      </div>
    );
  }

  const isDragDropEnabled = isFeatureEnabled('DRAG_DROP_PIPELINE');

  if (!isDragDropEnabled) {
    return (
      <div style={{ padding: 48, textAlign: 'center', background: 'var(--bg-primary)', borderRadius: 12, border: '1px solid var(--border)' }}>
        <p style={{ color: 'var(--text-secondary)' }}>
          Drag & Drop Pipeline feature is disabled. Enable it in feature flags.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
          Sales Pipeline
        </h2>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginBottom: 4 }}>
          Drag leads between stages to update their status instantly.
        </p>
        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', margin: 0 }}>
          {leadsData.length} of {totalLeads} leads loaded
          {totalLeads > leadsData.length && (
            <span style={{ color: '#ef4444', fontWeight: 600 }}>
              {' '}— {totalLeads - leadsData.length} more not shown, counts below are incomplete
            </span>
          )}
        </p>
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragEnd={handleDragEnd}
      >
        <div style={{ display: 'flex', gap: 16, overflowX: 'auto', paddingBottom: 16 }}>
          {ALL_STAGES.map(stage => (
            <StageColumn
              key={stage.id}
              stage={stage}
              leads={pipelineData[stage.id] || []}
            />
          ))}
        </div>
      </DndContext>
    </div>
  );
};

export default DragDropPipeline;
