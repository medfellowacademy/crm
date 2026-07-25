import React, { useState } from 'react';
import {
  Table, Card, Button, Tag, Statistic, Row, Col, Space, Typography,
  Select, message, Modal, Tooltip, DatePicker,
} from 'antd';
import {
  GlobalOutlined, ClockCircleOutlined, TeamOutlined,
  DollarCircleOutlined, UserAddOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { leadsAPI, counselorsAPI } from '../api/api';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
dayjs.extend(relativeTime);

const { Title, Text } = Typography;
const { Option } = Select;

const STATUS_COLORS = {
  Fresh: 'blue',
  'Follow Up': 'orange',
  Warm: 'gold',
  Hot: 'red',
  Enrolled: 'green',
  'Not Interested': 'default',
  Junk: 'default',
  'Not Answering': 'default',
};

const WebsiteLeadsPage = () => {
  const queryClient = useQueryClient();
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [assignTarget, setAssignTarget] = useState(null); // { leadIds: [...] } when modal open
  const [assignCounselor, setAssignCounselor] = useState(null);
  const [dateRange, setDateRange]         = useState([null, null]);
  const [assignedFilter, setAssignedFilter] = useState('all');  // 'all' | 'assigned' | 'unassigned'
  const [counselorFilter, setCounselorFilter] = useState('');

  const { data: leads = [], isLoading } = useQuery({
    queryKey: ['website-leads', dateRange[0]?.toISOString(), dateRange[1]?.toISOString()],
    queryFn: () =>
      leadsAPI.getAll({
        source: 'Website', limit: 2000,
        ...(dateRange[0] && dateRange[1] ? {
          created_from: dateRange[0].startOf('day').toISOString(),
          created_to: dateRange[1].endOf('day').toISOString(),
        } : {}),
      }).then(r => r.data?.leads || []),
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });

  const { data: counselors = [] } = useQuery({
    queryKey: ['counselors'],
    queryFn: () => counselorsAPI.getAll().then(res => Array.isArray(res.data) ? res.data : []),
  });

  const assignMutation = useMutation({
    mutationFn: async ({ leadIds, counselorName }) => {
      for (const leadId of leadIds) {
        await leadsAPI.reassign(leadId, counselorName, 'Assigned from Website Leads page');
      }
    },
    onSuccess: (_data, variables) => {
      message.success(
        `${variables.leadIds.length} lead${variables.leadIds.length > 1 ? 's' : ''} assigned to ${variables.counselorName}`
      );
      queryClient.invalidateQueries({ queryKey: ['website-leads'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      setSelectedRowKeys([]);
      setAssignTarget(null);
      setAssignCounselor(null);
    },
    onError: (e) => message.error(`Assign failed: ${e?.response?.data?.detail || e.message}`),
  });

  const total      = leads.length;
  const unassigned = leads.filter(l => !l.assigned_to).length;
  const assigned   = total - unassigned;
  const enrolled   = leads.filter(l => l.status === 'Enrolled').length;

  // Client-side filtered data
  const filteredLeads = leads.filter(l => {
    if (assignedFilter === 'assigned'   && !l.assigned_to) return false;
    if (assignedFilter === 'unassigned' &&  l.assigned_to) return false;
    if (counselorFilter && l.assigned_to !== counselorFilter) return false;
    return true;
  });

  // All unique counselors who appear in this lead set
  const activeCounselors = [...new Set(leads.map(l => l.assigned_to).filter(Boolean))].sort();

  const openAssignModal = (leadIds) => {
    setAssignTarget({ leadIds });
    setAssignCounselor(null);
  };

  const confirmAssign = () => {
    if (!assignCounselor || !assignTarget) return;
    assignMutation.mutate({ leadIds: assignTarget.leadIds, counselorName: assignCounselor });
  };

  const columns = [
    { title: 'Name', dataIndex: 'full_name', key: 'name', width: 170,
      render: v => <Text strong>{v}</Text> },
    { title: 'Phone', dataIndex: 'phone', key: 'phone', width: 150 },
    { title: 'Email', dataIndex: 'email', key: 'email', ellipsis: true },
    { title: 'Course', dataIndex: 'course_interested', key: 'course', ellipsis: true, width: 220 },
    { title: 'Status', dataIndex: 'status', key: 'status', width: 110,
      render: s => <Tag color={STATUS_COLORS[s] || 'default'}>{s}</Tag> },
    { title: 'Assigned To', dataIndex: 'assigned_to', key: 'assigned_to', width: 150,
      render: v => v ? <Tag color="cyan">{v}</Tag> : <Tag>Unassigned</Tag> },
    { title: 'Received', dataIndex: 'created_at', key: 'received', width: 130,
      sorter: (a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0),
      defaultSortOrder: 'descend',
      render: v => v ? (
        <Tooltip title={dayjs(v).format('DD MMM YYYY HH:mm')}>
          <Text type="secondary">{dayjs(v).fromNow()}</Text>
        </Tooltip>
      ) : '—' },
    {
      title: '', key: 'action', width: 100,
      render: (_, row) => (
        <Button size="small" icon={<UserAddOutlined />} onClick={() => openAssignModal([row.lead_id])}>
          {row.assigned_to ? 'Reassign' : 'Assign'}
        </Button>
      ),
    },
  ];

  const rowSelection = {
    selectedRowKeys,
    onChange: setSelectedRowKeys,
  };

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>Website Leads</Title>
          <Text type="secondary">
            Enquiries submitted on medfellowacademy.com, landing here before assignment to counselors
          </Text>
        </div>
        <Space>
          <DatePicker.RangePicker
            value={dateRange}
            onChange={v => setDateRange(v || [null, null])}
            allowClear
            placeholder={['Received from', 'to']}
          />
          <Button
            type="primary"
            disabled={selectedRowKeys.length === 0}
            icon={<UserAddOutlined />}
            onClick={() => openAssignModal(selectedRowKeys)}
          >
            Assign Selected ({selectedRowKeys.length})
          </Button>
        </Space>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        {[
          { title: 'Total Website Leads', value: total,      icon: <GlobalOutlined />,      color: '#1677ff', filter: 'all'        },
          { title: 'Unassigned',           value: unassigned, icon: <ClockCircleOutlined />, color: '#f59e0b', filter: 'unassigned' },
          { title: 'Assigned',             value: assigned,   icon: <TeamOutlined />,        color: '#8b5cf6', filter: 'assigned'   },
          { title: 'Enrolled',             value: enrolled,   icon: <DollarCircleOutlined />, color: '#10b981', filter: null        },
        ].map(({ title, value, icon, color, filter }) => {
          const active = filter && assignedFilter === filter;
          return (
            <Col xs={12} sm={6} key={title}>
              <Card
                onClick={() => {
                  if (!filter) return;
                  setAssignedFilter(assignedFilter === filter ? 'all' : filter);
                  setCounselorFilter('');
                }}
                style={{
                  cursor: filter ? 'pointer' : 'default',
                  border: active ? `2px solid ${color}` : '1px solid #f0f0f0',
                  borderRadius: 8,
                  transition: 'border 0.2s',
                }}
              >
                <Statistic
                  title={<Space size={4}>{icon}<span>{title}</span></Space>}
                  value={value}
                  valueStyle={{ color, fontWeight: 700 }}
                />
                {active && <div style={{ fontSize: 11, color, marginTop: 4 }}>● Filtering active — click to clear</div>}
              </Card>
            </Col>
          );
        })}
      </Row>

      <Card
        style={{ marginBottom: 16 }}
        bodyStyle={{ padding: '12px 16px' }}
      >
        <Space wrap>
          <Text strong style={{ color: '#64748b' }}>Filter by counselor:</Text>
          <Select
            value={counselorFilter || 'all'}
            onChange={v => { setCounselorFilter(v === 'all' ? '' : v); setAssignedFilter(v === 'all' ? 'all' : 'assigned'); }}
            style={{ width: 220 }}
            showSearch
            optionFilterProp="children"
          >
            <Option value="all">All counselors</Option>
            {activeCounselors.map(c => <Option key={c} value={c}>{c}</Option>)}
          </Select>
          {(assignedFilter !== 'all' || counselorFilter) && (
            <Button size="small" onClick={() => { setAssignedFilter('all'); setCounselorFilter(''); }}>
              Clear filters
            </Button>
          )}
          <Text type="secondary" style={{ fontSize: 12 }}>
            Showing {filteredLeads.length} of {total} leads
          </Text>
        </Space>
      </Card>

      <Card>
        <Table
          dataSource={filteredLeads}
          columns={columns}
          rowKey="lead_id"
          rowSelection={rowSelection}
          loading={isLoading}
          size="middle"
          pagination={{ pageSize: 50, showSizeChanger: true }}
          scroll={{ x: 1100 }}
          locale={{ emptyText: 'No website leads yet.' }}
        />
      </Card>

      <Modal
        title="Assign to Counselor"
        open={!!assignTarget}
        onCancel={() => setAssignTarget(null)}
        onOk={confirmAssign}
        okButtonProps={{ disabled: !assignCounselor, loading: assignMutation.isPending }}
      >
        <Text type="secondary">
          {assignTarget?.leadIds.length} lead{assignTarget?.leadIds.length > 1 ? 's' : ''} selected
        </Text>
        <Select
          style={{ width: '100%', marginTop: 12 }}
          placeholder="Select counselor"
          value={assignCounselor}
          onChange={setAssignCounselor}
          loading={!counselors || counselors.length === 0}
        >
          {(counselors || []).map(c => (
            <Option key={c.id} value={c.name}>{c.name}</Option>
          ))}
        </Select>
      </Modal>
    </div>
  );
};

export default WebsiteLeadsPage;
