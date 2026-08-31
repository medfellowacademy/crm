import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Timeline, Tag, Empty, Spin, Alert, Tooltip, Typography } from 'antd';
import {
  RetweetOutlined, GlobalOutlined, FormOutlined, CloudUploadOutlined,
  ApiOutlined, WhatsAppOutlined, FileSearchOutlined, FlagOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { duplicatesAPI } from '../../api/api';

const { Text } = Typography;

const CHANNEL_META = {
  meta_ads:     { label: 'Meta Ad',       color: '#1877F2', icon: <RetweetOutlined /> },
  google_sheet: { label: 'Meta / Sheet',  color: '#0F9D58', icon: <RetweetOutlined /> },
  website:      { label: 'Website',       color: '#7C3AED', icon: <GlobalOutlined /> },
  manual:       { label: 'Manual entry',  color: '#2563EB', icon: <FormOutlined /> },
  bulk_import:  { label: 'Bulk import',   color: '#D97706', icon: <CloudUploadOutlined /> },
  api:          { label: 'API',           color: '#0891B2', icon: <ApiOutlined /> },
  whatsapp:     { label: 'WhatsApp',      color: '#25D366', icon: <WhatsAppOutlined /> },
  unknown:      { label: 'Unknown',       color: '#6B7280', icon: <FileSearchOutlined /> },
};

const MATCH_LABEL = {
  new: 'first submission',
  phone: 'matched on phone',
  email: 'matched on email',
  'email,phone': 'matched on phone + email',
  'phone,email': 'matched on phone + email',
  meta_id: 'matched on Meta submission id',
};

const fmt = (d) => (d ? dayjs(d).format('D MMM YYYY, h:mm A') : '—');

export default function SubmissionTimeline({ leadId }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['lead-submissions', leadId],
    queryFn: () => duplicatesAPI.submissions(leadId).then((r) => r.data),
    enabled: !!leadId,
    staleTime: 30_000,
  });

  if (isLoading) return <Spin />;
  if (isError) return <Alert type="error" showIcon message="Could not load submission history" />;

  const subs = data?.submissions || [];
  if (!subs.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No submission history" />;

  const count = data?.submission_count || subs.length;
  const channels = data?.repeat_channels || [];

  const items = [...subs]
    .sort((a, b) => (b.sequence_no || 0) - (a.sequence_no || 0)) // newest first
    .map((s) => {
      const cm = CHANNEL_META[s.channel] || CHANNEL_META.unknown;
      return {
        color: s.is_first ? 'green' : cm.color,
        dot: s.is_first ? <FlagOutlined style={{ fontSize: 15 }} /> : cm.icon,
        children: (
          <div style={{ paddingBottom: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <Text strong>#{s.sequence_no}</Text>
              {s.is_first
                ? <Tag color="green">Original</Tag>
                : <Tag color="volcano">Repeat</Tag>}
              <Tag color={cm.color} style={{ color: '#fff', border: 'none' }}>{cm.label}</Tag>
              {s.needs_review && (
                <Tooltip title="This contact also matched a different lead — an admin should review / merge.">
                  <Tag color="red">Needs review</Tag>
                </Tooltip>
              )}
            </div>
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
              {fmt(s.occurred_at)} · {MATCH_LABEL[s.matched_on] || s.matched_on || ''}
            </div>
            <div style={{ fontSize: 12, marginTop: 4, lineHeight: 1.7 }}>
              {s.source && <span style={{ marginRight: 10 }}>Source: <Text strong>{s.source}</Text></span>}
              {s.adset_name && <span style={{ marginRight: 10 }}>Ad set: <Text strong>{s.adset_name}</Text></span>}
              {s.campaign_name && <span style={{ marginRight: 10 }}>Campaign: {s.campaign_name}</span>}
              {s.utm_source && <span style={{ marginRight: 10 }}>utm_source: {s.utm_source}</span>}
              {s.assigned_to_snapshot && (
                <span style={{ marginRight: 10 }}>Owner then: <Text strong>{s.assigned_to_snapshot}</Text></span>
              )}
            </div>
            {s.note && <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>{s.note}</div>}
          </div>
        ),
      };
    });

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
        <Tag color={count > 1 ? 'volcano' : 'default'} style={{ fontSize: 13, padding: '2px 10px' }}>
          <RetweetOutlined /> {count} submission{count === 1 ? '' : 's'}
        </Tag>
        {data?.needs_review && <Tag color="red">Needs admin review</Tag>}
        <Text type="secondary" style={{ fontSize: 12 }}>
          First: {fmt(data?.first_submission_at)} · Last: {fmt(data?.last_submission_at)}
        </Text>
        {channels.length > 0 && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            Channels: {channels.map((c) => (CHANNEL_META[c] || CHANNEL_META.unknown).label).join(', ')}
          </Text>
        )}
      </div>
      <Timeline items={items} />
    </div>
  );
}
