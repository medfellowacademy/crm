import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, Table, Tag, Button, Space, Typography, Popconfirm, Row, Col, Statistic, Empty, Result, Tooltip, message } from 'antd';
import { UndoOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { paymentsAPI } from '../../api/api';
import { fmt } from '../../utils/finance';

const { Text } = Typography;

// Students who paid something and then dropped: what was collected, refunded and
// kept, why they dropped, and a way to undo a drop made by mistake.
export default function DroppedTab({ onChanged }) {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['payments-dropped'],
    queryFn: () => paymentsAPI.dropped().then((r) => r.data),
  });

  const restore = useMutation({
    mutationFn: (leadId) => paymentsAPI.restore(leadId),
    onSuccess: () => {
      message.success('Student restored to Enrolled');
      queryClient.invalidateQueries({ queryKey: ['payments-dropped'] });
      onChanged?.();
    },
    onError: (e) => message.error(e?.response?.data?.detail || 'Could not restore the student'),
  });

  if (isError) {
    return <Result status="warning" title="Couldn't load dropped students" extra={<Button type="primary" onClick={() => refetch()}>Retry</Button>} />;
  }

  const t = data?.totals || {};
  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}><Card loading={isLoading}><Statistic title="Dropped students" value={t.count || 0} /></Card></Col>
        <Col xs={12} md={6}><Card loading={isLoading}><Statistic title="Collected before dropping" value={t.collected || 0} formatter={fmt} /></Card></Col>
        <Col xs={12} md={6}><Card loading={isLoading}><Statistic title="Refunded" value={t.refunded || 0} formatter={fmt} valueStyle={{ color: t.refunded ? '#cf1322' : undefined }} /></Card></Col>
        <Col xs={12} md={6}><Card loading={isLoading}><Statistic title="Kept" value={t.retained || 0} formatter={fmt} valueStyle={{ color: '#389e0d' }} /></Card></Col>
      </Row>
      <Card styles={{ body: { padding: 0 } }}>
        <Table
          loading={isLoading} rowKey="lead_id" dataSource={data?.items || []} scroll={{ x: 'max-content' }}
          pagination={{ pageSize: 15, hideOnSinglePage: true }}
          locale={{ emptyText: <Empty description="No dropped students with payments" /> }}
          columns={[
            { title: 'Student', key: 'name', render: (_, r) => (
              <div><div style={{ fontWeight: 600 }}>{r.name}</div><Text type="secondary" style={{ fontSize: 12 }}>{r.phone}</Text></div>
            ) },
            { title: 'Counselor', dataIndex: 'counselor' },
            { title: 'Course', dataIndex: 'course', ellipsis: true, width: 200 },
            { title: 'Dropped on', dataIndex: 'dropped_on', render: (d) => (d ? dayjs(d).format('DD MMM YYYY') : <Text type="secondary">—</Text>) },
            { title: 'Reason', key: 'reason', width: 220, render: (_, r) => (r.recorded ? (
              <div>
                <Tag color="volcano">{r.reason}</Tag>
                {r.note && <div style={{ fontSize: 12, color: '#6b7280' }}>{r.note}</div>}
              </div>
            ) : (
              <Tooltip title="Marked as dropped outside this screen, so no reason or refund was recorded">
                <Text type="secondary">Not recorded</Text>
              </Tooltip>
            )) },
            { title: 'Total fee', dataIndex: 'total_fee', align: 'right', render: fmt },
            { title: 'Collected', dataIndex: 'collected', align: 'right', render: (v) => <Text strong>{fmt(v)}</Text> },
            { title: 'Refunded', dataIndex: 'refund', align: 'right', render: (v) => (v ? <Text type="danger">{fmt(v)}</Text> : '—') },
            { title: 'Kept', dataIndex: 'retained', align: 'right', render: (v) => <Text strong style={{ color: '#389e0d' }}>{fmt(v)}</Text> },
            { title: 'Cancelled EMIs', key: 'cancelled', align: 'center', render: (_, r) => (r.cancelled_emis ? `${r.cancelled_emis} (${fmt(r.cancelled_amount)})` : '—') },
            { title: '', key: 'actions', render: (_, r) => (
              <Popconfirm
                title={`Restore ${r.name} to Enrolled?`}
                description="Their cancelled EMIs become pending again."
                okText="Restore" onConfirm={() => restore.mutate(r.lead_id)}
              >
                <Button size="small" icon={<UndoOutlined />} loading={restore.isPending && restore.variables === r.lead_id}>Undo drop</Button>
              </Popconfirm>
            ) },
          ]}
        />
      </Card>
    </div>
  );
}
