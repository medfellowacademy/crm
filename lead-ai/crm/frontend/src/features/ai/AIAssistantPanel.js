import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Card,
  Tabs,
  Button,
  Select,
  Typography,
  Tag,
  Alert,
  Empty,
  Space,
  message,
} from 'antd';
import {
  ThunderboltOutlined,
  MailOutlined,
  FileTextOutlined,
  AimOutlined,
  StopOutlined,
  BookOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { aiAPI } from '../../api/api';

const { Paragraph, Text } = Typography;

const REPLY_CONTEXTS = [
  { value: 'follow-up', label: 'Follow-up' },
  { value: 'welcome', label: 'Welcome' },
  { value: 'reminder', label: 'Reminder' },
  { value: 'thank-you', label: 'Thank you' },
];

const PRIORITY_COLOR = { high: 'red', medium: 'orange', low: 'green' };

// Shared handling for the 503 "AI not configured" response every AI endpoint returns.
const isAiUnavailable = (error) => error?.response?.status === 503;

const AiUnavailableAlert = () => (
  <Alert
    type="warning"
    showIcon
    message="AI features are not configured"
    description="Set ANTHROPIC_API_KEY in the backend .env to enable Claude-powered features."
    style={{ marginBottom: 16 }}
  />
);

function SmartReplyTab({ leadId }) {
  const [context, setContext] = useState('follow-up');
  const mutation = useMutation({
    mutationFn: () => aiAPI.smartReply(leadId, context).then(res => res.data),
    onError: (error) => {
      if (!isAiUnavailable(error)) message.error('Failed to generate reply');
    },
  });

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Select value={context} onChange={setContext} options={REPLY_CONTEXTS} style={{ width: 160 }} />
        <Button type="primary" icon={<MailOutlined />} loading={mutation.isPending} onClick={() => mutation.mutate()}>
          Generate Reply
        </Button>
      </Space>

      {mutation.isError && isAiUnavailable(mutation.error) && <AiUnavailableAlert />}

      {mutation.data && (
        <Card size="small" style={{ background: '#fafafa' }}>
          <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 8 }}>{mutation.data.message}</Paragraph>
          <Button
            size="small"
            icon={<CopyOutlined />}
            onClick={() => {
              navigator.clipboard.writeText(mutation.data.message);
              message.success('Copied to clipboard');
            }}
          >
            Copy
          </Button>
        </Card>
      )}
    </div>
  );
}

function SummarizeNotesTab({ leadId }) {
  const mutation = useMutation({
    mutationFn: () => aiAPI.summarizeNotes(leadId).then(res => res.data),
    onError: (error) => {
      if (!isAiUnavailable(error)) message.error('Failed to summarize notes');
    },
  });

  return (
    <div>
      <Button
        type="primary"
        icon={<FileTextOutlined />}
        loading={mutation.isPending}
        onClick={() => mutation.mutate()}
        style={{ marginBottom: 16 }}
      >
        Summarize Notes
      </Button>

      {mutation.isError && isAiUnavailable(mutation.error) && <AiUnavailableAlert />}

      {mutation.data && (
        <Card size="small" style={{ background: '#fafafa' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>{mutation.data.notes_count} note(s) analyzed</Text>
          <Paragraph style={{ whiteSpace: 'pre-wrap', marginTop: 8, marginBottom: 0 }}>
            {mutation.data.summary}
          </Paragraph>
        </Card>
      )}
    </div>
  );
}

function NextActionTab({ leadId }) {
  const mutation = useMutation({
    mutationFn: () => aiAPI.nextAction(leadId).then(res => res.data),
    onError: (error) => {
      if (!isAiUnavailable(error)) message.error('Failed to predict next action');
    },
  });
  const prediction = mutation.data?.prediction;

  return (
    <div>
      <Button
        type="primary"
        icon={<AimOutlined />}
        loading={mutation.isPending}
        onClick={() => mutation.mutate()}
        style={{ marginBottom: 16 }}
      >
        Predict Next Action
      </Button>

      {mutation.isError && isAiUnavailable(mutation.error) && <AiUnavailableAlert />}

      {prediction && (
        <Card size="small" style={{ background: '#fafafa' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Text strong style={{ fontSize: 15, textTransform: 'capitalize' }}>
              {(prediction.action || '').replace(/_/g, ' ')}
            </Text>
            {prediction.priority && (
              <Tag color={PRIORITY_COLOR[prediction.priority] || 'default'}>{prediction.priority}</Tag>
            )}
          </div>
          <Paragraph style={{ marginBottom: 4 }}>{prediction.reason}</Paragraph>
          {prediction.timing && (
            <Text type="secondary" style={{ fontSize: 12 }}>⏱ {prediction.timing}</Text>
          )}
        </Card>
      )}
    </div>
  );
}

function ConversionBarriersTab({ leadId }) {
  const mutation = useMutation({
    mutationFn: () => aiAPI.conversionBarriers(leadId).then(res => res.data),
    onError: (error) => {
      if (!isAiUnavailable(error)) message.error('Failed to analyze conversion barriers');
    },
  });

  return (
    <div>
      <Button
        type="primary"
        icon={<StopOutlined />}
        loading={mutation.isPending}
        onClick={() => mutation.mutate()}
        style={{ marginBottom: 16 }}
      >
        Analyze Barriers
      </Button>

      {mutation.isError && isAiUnavailable(mutation.error) && <AiUnavailableAlert />}

      {mutation.data && (
        mutation.data.barriers?.length > 0 ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            {mutation.data.barriers.map((barrier, i) => (
              <Card key={i} size="small" style={{ background: '#fafafa' }}>
                <Text>{barrier}</Text>
              </Card>
            ))}
          </Space>
        ) : (
          <Empty description="No barriers identified" />
        )
      )}
    </div>
  );
}

function CourseRecommendationTab({ leadId }) {
  const mutation = useMutation({
    mutationFn: () => aiAPI.recommendCourse(leadId).then(res => res.data),
    onError: (error) => {
      if (!isAiUnavailable(error)) message.error('Failed to recommend a course');
    },
  });
  const rec = mutation.data?.recommendation;

  return (
    <div>
      <Button
        type="primary"
        icon={<BookOutlined />}
        loading={mutation.isPending}
        onClick={() => mutation.mutate()}
        style={{ marginBottom: 16 }}
      >
        Recommend Course
      </Button>

      {mutation.isError && isAiUnavailable(mutation.error) && <AiUnavailableAlert />}

      {rec && (
        <Card size="small" style={{ background: '#fafafa' }}>
          <Text strong style={{ fontSize: 15 }}>{rec.course_name}</Text>
          {mutation.data.current_interest && mutation.data.current_interest !== rec.course_name && (
            <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 2 }}>
              Currently interested in: {mutation.data.current_interest}
            </div>
          )}
          {rec.ai_recommendation_reason && (
            <Paragraph style={{ marginTop: 8, marginBottom: 0 }}>{rec.ai_recommendation_reason}</Paragraph>
          )}
        </Card>
      )}
    </div>
  );
}

const AIAssistantPanel = ({ leadId }) => {
  const items = [
    { key: 'smart-reply', label: 'Smart Reply', children: <SmartReplyTab leadId={leadId} /> },
    { key: 'summary', label: 'Summarize Notes', children: <SummarizeNotesTab leadId={leadId} /> },
    { key: 'next-action', label: 'Next Action', children: <NextActionTab leadId={leadId} /> },
    { key: 'barriers', label: 'Conversion Barriers', children: <ConversionBarriersTab leadId={leadId} /> },
    { key: 'course', label: 'Course Fit', children: <CourseRecommendationTab leadId={leadId} /> },
  ];

  return (
    <Card
      title={<span><ThunderboltOutlined style={{ marginRight: 8 }} />AI Assistant</span>}
      style={{ marginBottom: '24px' }}
    >
      <Tabs items={items} size="small" />
    </Card>
  );
};

export default AIAssistantPanel;
