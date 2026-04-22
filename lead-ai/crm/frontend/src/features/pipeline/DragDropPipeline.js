import React, { useState } from 'react';
import { DndContext, closestCorners, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { motion } from 'framer-motion';
import { GripVertical, TrendingUp, DollarSign } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { leadsAPI } from '../../api/api';
import { AIScoreTooltip } from '../../components/ai/AIInsightCard';
import { TableSkeleton } from '../../components/ui/Skeletons';
import { isFeatureEnabled } from '../../config/featureFlags';

const PIPELINE_STAGES = [
  { id: 'new', name: 'New Leads', color: '#6b7280', probability: 10 },
  { id: 'contacted', name: 'Contacted', color: '#3b82f6', probability: 30 },
  { id: 'qualified', name: 'Qualified', color: '#f59e0b', probability: 50 },
  { id: 'proposal', name: 'Proposal Sent', color: '#8b5cf6', probability: 70 },
  { id: 'negotiation', name: 'Negotiation', color: '#ec4899', probability: 85 },
  { id: 'closed', name: 'Closed Won', color: '#10b981', probability: 100 },
];

// Draggable Lead Card Component
const DraggableLeadCard = ({ lead, stage }) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: lead.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const expectedRevenue = (lead.potential_revenue || 5000) * (stage.probability / 100);

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
            style={{
              color: 'var(--text-tertiary)',
              cursor: 'grab',
              padding: 4,
            }}
          >
            <GripVertical size={16} />
          </div>

          {/* Lead Info */}
          <div style={{ flex: 1 }}>
            <div style={{
              fontSize: 'var(--text-sm)',
              fontWeight: 600,
              color: 'var(--text-primary)',
              marginBottom: 4,
            }}>
              {lead.full_name || 'Unknown Lead'}
            </div>
            <div style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--text-tertiary)',
              marginBottom: 8,
            }}>
              {lead.email || 'No email'}
            </div>

            {/* Metrics */}
            <div style={{ display: 'flex', gap: 16, fontSize: 'var(--text-xs)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <TrendingUp size={12} style={{ color: 'var(--accent)' }} />
                <AIScoreTooltip score={lead.score || 0} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <DollarSign size={12} style={{ color: 'var(--success)' }} />
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                  ${expectedRevenue.toLocaleString()}
                </span>
              </div>
            </div>
          </div>

          {/* Segment Badge */}
          <div style={{
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: 10,
            fontWeight: 600,
            background: lead.segment === 'hot' ? '#fef2f2' : lead.segment === 'warm' ? '#fef3c7' : '#f0fdf4',
            color: lead.segment === 'hot' ? '#ef4444' : lead.segment === 'warm' ? '#f59e0b' : '#10b981',
          }}>
            {lead.segment?.toUpperCase() || 'COLD'}
          </div>
        </div>
      </motion.div>
    </div>
  );
};

// Pipeline Stage Column
const StageColumn = ({ stage, leads }) => {
  const totalValue = leads.reduce((sum, lead) => 
    sum + ((lead.potential_revenue || 5000) * (stage.probability / 100)), 0
  );

  return (
    <div style={{
      background: 'var(--bg-secondary)',
      borderRadius: 12,
      padding: 16,
      minHeight: 600,
      width: 300,
      flexShrink: 0,
    }}>
      {/* Stage Header */}
      <div style={{
        marginBottom: 16,
        paddingBottom: 12,
        borderBottom: '2px solid var(--border)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <div style={{
            width: 12,
            height: 12,
            borderRadius: '50%',
            background: stage.color,
          }} />
          <h3 style={{
            fontSize: 'var(--text-base)',
            fontWeight: 600,
            color: 'var(--text-primary)',
          }}>
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
        
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 'var(--text-xs)',
          color: 'var(--text-tertiary)',
        }}>
          <span>Win Probability: {stage.probability}%</span>
          <span style={{ fontWeight: 600, color: 'var(--success)' }}>
            ${totalValue.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Lead Cards */}
      <SortableContext items={leads.map(l => l.id)} strategy={verticalListSortingStrategy}>
        <div style={{ minHeight: 400 }}>
          {leads.length === 0 ? (
            <div style={{
              padding: 32,
              textAlign: 'center',
              color: 'var(--text-tertiary)',
              fontSize: 'var(--text-sm)',
            }}>
              No leads in this stage
            </div>
          ) : (
            leads.map(lead => (
              <DraggableLeadCard key={lead.id} lead={lead} stage={stage} />
            ))
          )}
        </div>
      </SortableContext>
    </div>
  );
};

// Main Pipeline Component
const DragDropPipeline = () => {
  const queryClient = useQueryClient();
  const [pipelineData, setPipelineData] = useState({});

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

  // Fetch leads
  const { data: leads, isLoading } = useQuery({
    queryKey: ['leads'],
    queryFn: () => leadsAPI.getAll().then(res => res.data),
    onSuccess: (data) => {
      // Group leads by stage
      const grouped = PIPELINE_STAGES.reduce((acc, stage) => {
        acc[stage.id] = data.filter(lead => lead.stage === stage.id || (!lead.stage && stage.id === 'new'));
        return acc;
      }, {});
      setPipelineData(grouped);
    },
  });

  // Update lead stage mutation
  const updateStageMutation = useMutation({
    mutationFn: ({ leadId, newStage }) => 
      leadsAPI.update(leadId, { stage: newStage }),
    onSuccess: () => {
      queryClient.invalidateQueries(['leads']);
    },
  });

  const handleDragEnd = (event) => {
    const { active, over } = event;

    if (!over) return;

    const activeId = active.id;
    const overId = over.id;

    // Find which stage the lead was moved to
    const activeStage = Object.keys(pipelineData).find(stageId =>
      pipelineData[stageId].some(lead => lead.id === activeId)
    );

    const overStage = Object.keys(pipelineData).find(stageId =>
      pipelineData[stageId].some(lead => lead.id === overId) || stageId === overId
    );

    if (activeStage !== overStage && overStage) {
      // Update state optimistically
      setPipelineData(prev => {
        const newData = { ...prev };
        const leadToMove = newData[activeStage].find(lead => lead.id === activeId);
        
        newData[activeStage] = newData[activeStage].filter(lead => lead.id !== activeId);
        newData[overStage] = [...(newData[overStage] || []), { ...leadToMove, stage: overStage }];
        
        return newData;
      });

      // Update backend
      updateStageMutation.mutate({
        leadId: activeId,
        newStage: overStage,
      });
    }
  };

  if (isLoading) {
    return <TableSkeleton rows={8} />;
  }

  const isDragDropEnabled = isFeatureEnabled('DRAG_DROP_PIPELINE');

  if (!isDragDropEnabled) {
    return (
      <div style={{
        padding: 48,
        textAlign: 'center',
        background: 'var(--bg-primary)',
        borderRadius: 12,
        border: '1px solid var(--border)',
      }}>
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
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
          Drag leads between stages to update their status
        </p>
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragEnd={handleDragEnd}
      >
        <div style={{
          display: 'flex',
          gap: 16,
          overflowX: 'auto',
          paddingBottom: 16,
        }}>
          {PIPELINE_STAGES.map(stage => (
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
