import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, List, Tag, Typography, Space, Empty } from 'antd';
import { PhoneOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { callsAPI } from '../../api/api';

const { Text } = Typography;

const LABEL = { outgoing: 'Outgoing', incoming: 'Incoming', missed: 'Missed', rejected: 'Rejected' };
const secs = (s) => {
  const n = Number(s || 0);
  return n >= 60 ? `${Math.floor(n / 60)}m ${n % 60}s` : `${n}s`;
};

/** Calls made to / received from this lead, as seen by the counselors' phone apps. */
export default function CallHistory({ leadId }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['lead-calls', leadId],
    queryFn: () => callsAPI.forLead(leadId).then((r) => r.data),
    enabled: !!leadId,
    staleTime: 60 * 1000,
    retry: 1,
  });
  if (isError) return null;                       // call data is optional here; never block the lead page

  const t = data?.totals || {};
  return (
    <Card size="small" style={{ marginBottom: 16 }} loading={isLoading}
      title={<span><PhoneOutlined /> Call history</span>}
      extra={data?.calls?.length ? (
        <Space size={4} wrap>
          <Tag>{t.made || 0} made</Tag>
          <Tag color="green">{t.connected || 0} connected</Tag>
          <Tag color="red">{t.not_connected || 0} not connected</Tag>
        </Space>) : null}>
      {data?.calls?.length ? (
        <List size="small" dataSource={data.calls}
          renderItem={(c) => (
            <List.Item>
              <Space wrap>
                <Tag color={c.connected ? 'green' : (c.direction === 'outgoing' ? 'red' : 'orange')}>
                  {LABEL[c.direction] || c.direction}{c.direction === 'outgoing' ? (c.connected ? ' · connected' : ' · not connected') : ''}
                </Tag>
                <Text>{dayjs(c.started_at).format('DD MMM YYYY, h:mm A')}</Text>
                {c.connected && <Text type="secondary">{secs(c.duration_sec)}</Text>}
                <Text type="secondary">{c.user_email}</Text>
              </Space>
            </List.Item>)} />
      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No calls logged for this number yet" />}
    </Card>
  );
}
