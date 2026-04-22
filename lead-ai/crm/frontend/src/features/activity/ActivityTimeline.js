import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MessageCircle,
  Phone,
  FileText,
  TrendingUp,
  CreditCard,
  Sparkles,
  ChevronDown,
  Clock,
  User,
  Calendar,
  ExternalLink,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { isFeatureEnabled } from '../../config/featureFlags';
import { CardSkeleton } from '../../components/ui/Skeletons';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const ActivityTimeline = ({ leadId }) => {
  const [filter, setFilter] = useState('all');
  const [showAISummary, setShowAISummary] = useState(true);

  // Fetch activity data
  const { data: activities = [], isLoading } = useQuery({
    queryKey: ['activities', leadId, filter],
    queryFn: async () => {
      const params = filter !== 'all' ? `?type=${filter}` : '';
      const response = await fetch(`${API_BASE_URL}/api/leads/${leadId}/activities${params}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });
      if (!response.ok) throw new Error('Failed to fetch activities');
      return response.json();
    },
    staleTime: 2 * 60 * 1000, // 2 minutes
  });

  // Fetch AI summary
  const { data: aiSummary } = useQuery({
    queryKey: ['ai-summary', leadId],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/leads/${leadId}/ai-summary`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });
      if (!response.ok) throw new Error('Failed to fetch AI summary');
      return response.json();
    },
    enabled: isFeatureEnabled('AI_ACTIVITY_SUMMARY'),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const getActivityIcon = (type) => {
    const icons = {
      whatsapp: MessageCircle,
      call: Phone,
      note: FileText,
      status: TrendingUp,
      payment: CreditCard,
      ai_recommendation: Sparkles,
    };
    const Icon = icons[type] || FileText;
    return <Icon size={16} />;
  };

  const getActivityColor = (type) => {
    const colors = {
      whatsapp: '#25D366',
      call: '#3b82f6',
      note: '#f59e0b',
      status: '#8b5cf6',
      payment: '#10b981',
      ai_recommendation: '#ec4899',
    };
    return colors[type] || '#6b7280';
  };

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const filters = [
    { id: 'all', label: 'All Activity' },
    { id: 'whatsapp', label: 'WhatsApp' },
    { id: 'call', label: 'Calls' },
    { id: 'note', label: 'Notes' },
    { id: 'status', label: 'Status' },
    { id: 'payment', label: 'Payments' },
  ];

  if (isLoading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <CardSkeleton />
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* AI Summary Card */}
      {isFeatureEnabled('AI_ACTIVITY_SUMMARY') && aiSummary && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          style={{
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            borderRadius: '12px',
            padding: 'var(--space-4)',
            color: 'white',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <Sparkles size={20} />
              <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: '600', margin: 0 }}>AI Summary (Last 7 Days)</h3>
            </div>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setShowAISummary(!showAISummary)}
              style={{
                background: 'rgba(255, 255, 255, 0.2)',
                border: 'none',
                borderRadius: '6px',
                padding: '6px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <ChevronDown
                size={16}
                style={{
                  transform: showAISummary ? 'rotate(180deg)' : 'rotate(0deg)',
                  transition: 'transform 0.2s',
                }}
              />
            </motion.button>
          </div>

          <AnimatePresence>
            {showAISummary && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                style={{ overflow: 'hidden' }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', opacity: 0.9, marginBottom: 'var(--space-1)' }}>
                      Engagement Level
                    </div>
                    <div style={{ fontSize: 'var(--text-base)', fontWeight: '600' }}>
                      {aiSummary.engagement_level || 'Moderate - 3 interactions this week'}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', opacity: 0.9, marginBottom: 'var(--space-1)' }}>
                      Next Best Action
                    </div>
                    <div style={{ fontSize: 'var(--text-base)', fontWeight: '600' }}>
                      {aiSummary.next_action || 'Follow up with course brochure - High interest detected'}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', opacity: 0.9, marginBottom: 'var(--space-1)' }}>
                      Key Insights
                    </div>
                    <ul style={{ margin: '0', paddingLeft: 'var(--space-4)', fontSize: 'var(--text-sm)' }}>
                      {(aiSummary.insights || [
                        'Opened payment link 2x but no conversion',
                        'Most active during 10 AM - 12 PM window',
                        'Asked about scholarships - price sensitivity detected',
                      ]).map((insight, idx) => (
                        <li key={idx} style={{ marginBottom: 'var(--space-1)' }}>{insight}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      )}

      {/* Filter Tabs */}
      <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        {filters.map((f) => (
          <motion.button
            key={f.id}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setFilter(f.id)}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: filter === f.id ? 'var(--color-primary)' : 'var(--bg-secondary)',
              color: filter === f.id ? 'white' : 'var(--text-secondary)',
              fontSize: 'var(--text-sm)',
              fontWeight: '500',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
          >
            {f.label}
          </motion.button>
        ))}
      </div>

      {/* Timeline */}
      <div style={{ position: 'relative' }}>
        {/* Vertical line */}
        <div
          style={{
            position: 'absolute',
            left: '15px',
            top: '0',
            bottom: '0',
            width: '2px',
            background: 'var(--border-color)',
          }}
        />

        {/* Activity items */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {activities.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 'var(--space-6)', color: 'var(--text-tertiary)' }}>
              No activities found
            </div>
          ) : (
            activities.map((activity, index) => (
              <motion.div
                key={activity.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
                style={{
                  position: 'relative',
                  paddingLeft: 'var(--space-6)',
                  display: 'flex',
                  gap: 'var(--space-3)',
                }}
              >
                {/* Icon dot */}
                <div
                  style={{
                    position: 'absolute',
                    left: '7px',
                    top: '4px',
                    width: '16px',
                    height: '16px',
                    borderRadius: '50%',
                    background: getActivityColor(activity.type),
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'white',
                    zIndex: 1,
                    border: '2px solid var(--bg-primary)',
                  }}
                >
                  {getActivityIcon(activity.type)}
                </div>

                {/* Content */}
                <div
                  style={{
                    flex: 1,
                    background: 'var(--bg-secondary)',
                    borderRadius: '12px',
                    padding: 'var(--space-3)',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 'var(--space-2)' }}>
                    <div>
                      <div style={{ fontSize: 'var(--text-sm)', fontWeight: '600', color: 'var(--text-primary)' }}>
                        {activity.title || activity.type.charAt(0).toUpperCase() + activity.type.slice(1)}
                      </div>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginTop: '4px' }}>
                        <Clock size={12} />
                        {formatTime(activity.createdAt || activity.created_at)}
                        {activity.createdBy && (
                          <>
                            <span>•</span>
                            <User size={12} />
                            {activity.createdBy}
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
                    {activity.content}
                  </div>

                  {/* Action buttons for specific types */}
                  {(activity.type === 'payment' || activity.actionUrl) && (
                    <motion.a
                      whileHover={{ scale: 1.02 }}
                      href={activity.actionUrl || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 'var(--space-1)',
                        fontSize: 'var(--text-xs)',
                        color: 'var(--color-primary)',
                        textDecoration: 'none',
                        fontWeight: '500',
                      }}
                    >
                      View Details
                      <ExternalLink size={12} />
                    </motion.a>
                  )}
                </div>
              </motion.div>
            ))
          )}
        </div>
      </div>

      {/* Load more */}
      {activities.length >= 20 && (
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          style={{
            padding: 'var(--space-3)',
            borderRadius: '8px',
            border: '1px solid var(--border-color)',
            background: 'transparent',
            color: 'var(--text-secondary)',
            fontSize: 'var(--text-sm)',
            fontWeight: '500',
            cursor: 'pointer',
          }}
        >
          Load More Activities
        </motion.button>
      )}
    </div>
  );
};

export default ActivityTimeline;
