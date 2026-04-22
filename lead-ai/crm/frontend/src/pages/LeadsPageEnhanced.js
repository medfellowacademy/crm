import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Table,
  Button,
  Tag,
  Progress,
  Space,
  Input,
  Select,
  DatePicker,
  Drawer,
  Form,
  message,
  Popconfirm,
  Row,
  Col,
  Card,
  Badge,
  Statistic,
  Avatar,
  Tooltip,
  Dropdown,
  Menu,
  Segmented,
  Timeline,
  Empty,
  Typography,
  Divider,
  Checkbox,
  Radio,
  InputNumber,
  Alert,
  Tabs,
} from 'antd';
import {
  PlusOutlined,
  SearchOutlined,
  FilterOutlined,
  WhatsAppOutlined,
  MailOutlined,
  EyeOutlined,
  DeleteOutlined,
  ReloadOutlined,
  DownloadOutlined,
  UserOutlined,
  PhoneOutlined,
  GlobalOutlined,
  BookOutlined,
  CalendarOutlined,
  DollarOutlined,
  EditOutlined,
  MoreOutlined,
  StarOutlined,
  FireOutlined,
  ThunderboltOutlined,
  RiseOutlined,
  FallOutlined,
  TeamOutlined,
  ClockCircleOutlined,
  SyncOutlined,
  ExportOutlined,
  ImportOutlined,
  SettingOutlined,
  LineChartOutlined,
} from '@ant-design/icons';
import { leadsAPI, coursesAPI, counselorsAPI, usersAPI } from '../api/api';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);

const { RangePicker } = DatePicker;
const { Option } = Select;
const { Text, Title } = Typography;
const { TabPane } = Tabs;

const LeadsPageEnhanced = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  
  // State management
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [bulkDrawerVisible, setBulkDrawerVisible] = useState(false);
  const [filterDrawerVisible, setFilterDrawerVisible] = useState(false);
  const [filters, setFilters] = useState({});
  const [searchText, setSearchText] = useState('');
  const [viewMode, setViewMode] = useState('table'); // table | kanban | grid
  const [selectedRows, setSelectedRows] = useState([]);
  const [quickFilters, setQuickFilters] = useState('all'); // all | hot | warm | today | overdue
  const [customCreatedRange, setCustomCreatedRange] = useState(null);
  const [customUpdatedRange, setCustomUpdatedRange] = useState(null);
  const [showCreatedPicker, setShowCreatedPicker] = useState(false);
  const [showUpdatedPicker, setShowUpdatedPicker] = useState(false);
  const [form] = Form.useForm();
  const [bulkForm] = Form.useForm();

  // Fetch data
  const { data: leads = [], isLoading, error, refetch } = useQuery({
    queryKey: ['leads', filters, searchText, quickFilters],
    queryFn: async () => {
      let params = { ...filters };
      
      // Apply quick filters
      if (quickFilters === 'hot') params.ai_segment = 'Hot';
      if (quickFilters === 'warm') params.ai_segment = 'Warm';
      if (quickFilters === 'today') params.created_today = true;
      if (quickFilters === 'overdue') params.overdue = true;
      
      // Apply search
      if (searchText) params.search = searchText;
      
      try {
        const response = await leadsAPI.getAll(params);
        return response.data || [];
      } catch (err) {
        console.error('Failed to fetch leads:', err);
        return [];
      }
    },
    keepPreviousData: true,
    refetchInterval: 30000, // Refresh every 30 seconds
    retry: 1,
    onError: (err) => {
      console.error('Leads query error:', err);
    }
  });

  const { data: courses = [] } = useQuery({
    queryKey: ['courses'],
    queryFn: async () => {
      try {
        const res = await coursesAPI.getAll();
        return res.data || [];
      } catch (err) {
        console.error('Failed to fetch courses:', err);
        return [];
      }
    }
  });

  const { data: counselors = [] } = useQuery({
    queryKey: ['counselors'],
    queryFn: async () => {
      try {
        const res = await counselorsAPI.getAll();
        return res.data || [];
      } catch (err) {
        console.error('Failed to fetch counselors:', err);
        return [];
      }
    }
  });

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      try {
        const res = await usersAPI.getAll();
        return res.data || [];
      } catch (err) {
        console.error('Failed to fetch users:', err);
        return [];
      }
    }
  });

  // Extract unique values for filters
  const uniqueStatuses = [...new Set(leads.map(l => l.status))].filter(Boolean).sort();
  const uniqueCourses = [...new Set(leads.map(l => l.course_interested))].filter(Boolean).sort();
  const uniqueCountries = [...new Set(leads.map(l => l.country))].filter(Boolean).sort();
  const uniqueAssignedUsers = [...new Set(leads.map(l => l.assigned_to))].filter(Boolean).sort();

  // Handle course selection to auto-populate price
  const handleCourseChange = (courseName) => {
    const selectedCourse = courses.find(c => c.course_name === courseName);
    if (selectedCourse) {
      form.setFieldsValue({
        expected_revenue: selectedCourse.price,
      });
      message.info(`Course price ₹${(selectedCourse.price / 1000).toFixed(0)}K auto-filled!`);
    }
  };

  // Mutations
  const createLeadMutation = useMutation({
    mutationFn: (data) => leadsAPI.create(data),
    onSuccess: () => {
      message.success('Lead created successfully! 🎉');
      setDrawerVisible(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (error) => {
      message.error(`Failed to create lead: ${error.message}`);
    },
  });

  const deleteLeadMutation = useMutation({
    mutationFn: (leadId) => leadsAPI.delete(leadId),
    onSuccess: () => {
      message.success('Lead deleted successfully!');
      queryClient.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (error) => {
      message.error(`Failed to delete lead: ${error.message}`);
    },
  });

  const bulkUpdateMutation = useMutation({
    mutationFn: ({ leadIds, updates }) => leadsAPI.bulkUpdate(leadIds, updates),
    onSuccess: () => {
      message.success(`${selectedRows.length} leads updated successfully!`);
      setSelectedRows([]);
      setBulkDrawerVisible(false);
      bulkForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (error) => {
      message.error(`Failed to update leads: ${error.message}`);
    },
  });

  // Calculate stats
  const stats = {
    total: leads.length,
    hot: leads.filter(l => l.ai_segment === 'Hot').length,
    warm: leads.filter(l => l.ai_segment === 'Warm').length,
    cold: leads.filter(l => l.ai_segment === 'Cold').length,
    enrolled: leads.filter(l => l.status === 'Enrolled').length,
    followUpToday: leads.filter(l => 
      l.follow_up_date && dayjs(l.follow_up_date).isSame(dayjs(), 'day')
    ).length,
    overdue: leads.filter(l => 
      l.follow_up_date && dayjs(l.follow_up_date).isBefore(dayjs(), 'day')
    ).length,
    avgScore: leads.length ? (leads.reduce((sum, l) => sum + (l.ai_score || 0), 0) / leads.length).toFixed(1) : 0,
    totalRevenue: leads.filter(l => l.status === 'Enrolled').reduce((sum, l) => sum + (l.actual_revenue || 0), 0),
    expectedRevenue: leads.filter(l => l.status !== 'Enrolled').reduce((sum, l) => sum + (l.expected_revenue || 0), 0),
  };

  // Handlers
  const handleCreateLead = (values) => {
    createLeadMutation.mutate({
      ...values,
      follow_up_date: values.follow_up_date ? values.follow_up_date.format('YYYY-MM-DD') : null,
    });
  };

  const handleBulkUpdate = (values) => {
    bulkUpdateMutation.mutate({
      leadIds: selectedRows,
      updates: values,
    });
  };

  const handleExport = () => {
    const csv = leads.map(lead => ({
      'Lead ID': lead.lead_id,
      'Name': lead.full_name,
      'Email': lead.email,
      'Phone': lead.phone,
      'Country': lead.country,
      'Course': lead.course_interested,
      'Status': lead.status,
      'AI Score': lead.ai_score,
      'Segment': lead.ai_segment,
      'Revenue': lead.status === 'Enrolled' ? lead.actual_revenue : lead.expected_revenue,
      'Follow Up': lead.follow_up_date,
      'Created': lead.created_at,
    }));
    
    const csvContent = [
      Object.keys(csv[0]).join(','),
      ...csv.map(row => Object.values(row).join(','))
    ].join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `leads_export_${dayjs().format('YYYY-MM-DD')}.csv`;
    a.click();
    message.success('Leads exported successfully!');
  };

  const getActionMenu = (record) => (
    <Menu>
      <Menu.Item 
        key="view" 
        icon={<EyeOutlined />}
        onClick={() => navigate(`/leads/${record.lead_id}`)}
      >
        View Details
      </Menu.Item>
      <Menu.Item 
        key="edit" 
        icon={<EditOutlined />}
        onClick={() => {
          form.setFieldsValue({
            ...record,
            follow_up_date: record.follow_up_date ? dayjs(record.follow_up_date) : null,
          });
          setDrawerVisible(true);
        }}
      >
        Edit Lead
      </Menu.Item>
      <Menu.Item 
        key="whatsapp" 
        icon={<WhatsAppOutlined />}
        onClick={() => window.open(`https://wa.me/${record.phone?.replace(/[^0-9]/g, '')}`)}
      >
        WhatsApp
      </Menu.Item>
      <Menu.Item 
        key="email" 
        icon={<MailOutlined />}
        onClick={() => window.location.href = `mailto:${record.email}`}
      >
        Send Email
      </Menu.Item>
      <Menu.Divider />
      <Menu.Item 
        key="delete" 
        icon={<DeleteOutlined />}
        danger
        onClick={() => {
          deleteLeadMutation.mutate(record.lead_id);
        }}
      >
        Delete Lead
      </Menu.Item>
    </Menu>
  );

  // Enhanced table columns
  const columns = [
    {
      title: '',
      key: 'selection',
      width: 50,
      render: (_, record) => (
        <Checkbox
          checked={selectedRows.includes(record.lead_id)}
          onChange={(e) => {
            if (e.target.checked) {
              setSelectedRows([...selectedRows, record.lead_id]);
            } else {
              setSelectedRows(selectedRows.filter(id => id !== record.lead_id));
            }
          }}
        />
      ),
    },
    {
      title: 'Lead Info',
      key: 'lead_info',
      fixed: 'left',
      width: 280,
      render: (_, record) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Avatar 
            size={48} 
            style={{ 
              backgroundColor: record.ai_segment === 'Hot' ? '#ff4d4f' : 
                              record.ai_segment === 'Warm' ? '#faad14' : '#52c41a',
              flexShrink: 0
            }}
          >
            {record.full_name?.charAt(0)?.toUpperCase()}
          </Avatar>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div>
              <a 
                onClick={() => navigate(`/leads/${record.lead_id}`)}
                style={{ fontWeight: 600, fontSize: 14 }}
              >
                {record.full_name}
              </a>
              <Tag 
                style={{ marginLeft: 8 }} 
                color={
                  record.ai_segment === 'Hot' ? 'red' :
                  record.ai_segment === 'Warm' ? 'orange' : 'green'
                }
                icon={record.ai_segment === 'Hot' ? <FireOutlined /> : 
                      record.ai_segment === 'Warm' ? <ThunderboltOutlined /> : null}
              >
                {record.ai_segment}
              </Tag>
            </div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              ID: {record.lead_id}
            </Text>
            <div style={{ fontSize: 12, marginTop: 2 }}>
              <PhoneOutlined /> {record.phone}
            </div>
          </div>
        </div>
      ),
    },
    {
      title: 'Country & Course',
      key: 'location',
      width: 200,
      filters: [
        { text: 'All Countries', value: 'all' },
        ...uniqueCountries.map(country => ({ text: country, value: country }))
      ],
      onFilter: (value, record) => value === 'all' || record.country === value,
      render: (_, record) => (
        <div>
          <div style={{ marginBottom: 4 }}>
            <GlobalOutlined /> <Text strong>{record.country}</Text>
          </div>
          <Text type="secondary" ellipsis style={{ fontSize: 12 }}>
            <BookOutlined /> {record.course_interested}
          </Text>
        </div>
      ),
    },
    {
      title: 'Course',
      dataIndex: 'course_interested',
      key: 'course',
      width: 200,
      filters: [
        { text: 'All Courses', value: 'all' },
        ...uniqueCourses.map(course => ({ text: course, value: course }))
      ],
      onFilter: (value, record) => value === 'all' || record.course_interested === value,
      render: (course) => (
        <Text ellipsis style={{ fontSize: 12 }}>
          <BookOutlined style={{ marginRight: 6, color: '#1890ff' }} />
          {course}
        </Text>
      ),
    },
    {
      title: 'Status & Score',
      key: 'status_score',
      width: 180,
      filters: [
        { text: 'All Statuses', value: 'all' },
        ...uniqueStatuses.map(status => ({ text: status, value: status }))
      ],
      onFilter: (value, record) => value === 'all' || record.status === value,
      render: (_, record) => (
        <div>
          <Tag 
            color={
              record.status === 'Enrolled' ? 'green' :
              record.status === 'Hot' ? 'red' :
              record.status === 'Warm' ? 'orange' : 'blue'
            }
            style={{ marginBottom: 8, width: '100%', textAlign: 'center' }}
          >
            {record.status}
          </Tag>
          <Progress
            percent={record.ai_score || 0}
            size="small"
            strokeColor={{
              '0%': '#108ee9',
              '50%': '#87d068',
              '100%': '#ff4d4f',
            }}
            format={(percent) => `Score: ${percent?.toFixed(0)}`}
          />
        </div>
      ),
    },
    {
      title: 'Assigned To',
      dataIndex: 'assigned_to',
      key: 'assigned_to',
      width: 180,
      filters: [
        { text: 'All Users', value: 'all' },
        { text: 'Unassigned', value: 'unassigned' },
        ...uniqueAssignedUsers.map(user => ({ text: user, value: user }))
      ],
      onFilter: (value, record) => {
        if (value === 'all') return true;
        if (value === 'unassigned') return !record.assigned_to;
        return record.assigned_to === value;
      },
      render: (assignedTo, record) => (
        <Select
          value={assignedTo || 'Unassigned'}
          style={{ width: '100%' }}
          size="small"
          onChange={(value) => {
            updateLeadMutation.mutate({
              leadId: record.lead_id,
              data: { assigned_to: value === 'Unassigned' ? null : value }
            });
          }}
          options={[
            { label: 'Unassigned', value: 'Unassigned' },
            ...users.map(user => ({
              label: (
                <Space>
                  <Avatar size="small" style={{ backgroundColor: '#1890ff' }}>
                    {user.full_name?.charAt(0)}
                  </Avatar>
                  {user.full_name}
                </Space>
              ),
              value: user.full_name
            }))
          ]}
        />
      ),
    },
    {
      title: 'Revenue',
      key: 'revenue',
      width: 140,
      sorter: (a, b) => {
        const aRev = a.status === 'Enrolled' ? a.actual_revenue : a.expected_revenue;
        const bRev = b.status === 'Enrolled' ? b.actual_revenue : b.expected_revenue;
        return aRev - bRev;
      },
      render: (_, record) => {
        const revenue = record.status === 'Enrolled' ? record.actual_revenue : record.expected_revenue;
        const isActual = record.status === 'Enrolled';
        
        return (
          <div>
            <div style={{ 
              color: isActual ? '#52c41a' : '#faad14', 
              fontWeight: 600,
              fontSize: 16
            }}>
              ₹{((revenue || 0) / 1000).toFixed(0)}K
            </div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {isActual ? 'Actual' : 'Expected'}
            </Text>
          </div>
        );
      },
    },
    {
      title: 'Follow Up',
      dataIndex: 'follow_up_date',
      key: 'follow_up_date',
      width: 160,
      sorter: (a, b) => {
        if (!a.follow_up_date) return 1;
        if (!b.follow_up_date) return -1;
        return new Date(a.follow_up_date) - new Date(b.follow_up_date);
      },
      render: (date, record) => {
        if (!date) return <Text type="secondary">Not set</Text>;
        
        const followUpDate = dayjs(date);
        const isOverdue = followUpDate.isBefore(dayjs(), 'day');
        const isToday = followUpDate.isSame(dayjs(), 'day');
        
        return (
          <div>
            <div style={{ color: isOverdue ? '#ff4d4f' : isToday ? '#faad14' : undefined }}>
              <CalendarOutlined /> {followUpDate.format('MMM DD')}
            </div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {followUpDate.fromNow()}
            </Text>
          </div>
        );
      },
    },
    {
      title: 'Assigned To',
      dataIndex: 'assigned_to',
      key: 'assigned_to',
      width: 140,
      render: (counselor) => counselor ? (
        <div>
          <Avatar size="small" icon={<UserOutlined />} style={{ marginRight: 8 }} />
          <Text>{counselor}</Text>
        </div>
      ) : <Text type="secondary">Unassigned</Text>,
    },
    {
      title: () => (
        <div>
          <div>Created</div>
          {customCreatedRange && (
            <Text style={{ fontSize: 10, color: '#52c41a' }}>
              {customCreatedRange[0].format('MMM DD')} - {customCreatedRange[1].format('MMM DD')}
            </Text>
          )}
        </div>
      ),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      sorter: (a, b) => new Date(a.created_at) - new Date(b.created_at),
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }) => (
        <div style={{ padding: 16, width: 300 }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Button
              type={!customCreatedRange && selectedKeys[0] === 'all' ? 'primary' : 'default'}
              block
              onClick={() => {
                setCustomCreatedRange(null);
                setSelectedKeys(['all']);
                confirm();
              }}
            >
              All Time
            </Button>
            <Button
              type={selectedKeys[0] === 'today' ? 'primary' : 'default'}
              block
              onClick={() => {
                setCustomCreatedRange(null);
                setSelectedKeys(['today']);
                confirm();
              }}
            >
              Today
            </Button>
            <Button
              type={selectedKeys[0] === 'week' ? 'primary' : 'default'}
              block
              onClick={() => {
                setCustomCreatedRange(null);
                setSelectedKeys(['week']);
                confirm();
              }}
            >
              This Week
            </Button>
            <Button
              type={selectedKeys[0] === 'month' ? 'primary' : 'default'}
              block
              onClick={() => {
                setCustomCreatedRange(null);
                setSelectedKeys(['month']);
                confirm();
              }}
            >
              This Month
            </Button>
            <Button
              type={selectedKeys[0] === '3months' ? 'primary' : 'default'}
              block
              onClick={() => {
                setCustomCreatedRange(null);
                setSelectedKeys(['3months']);
                confirm();
              }}
            >
              Last 3 Months
            </Button>
            <Divider style={{ margin: '8px 0' }}>Custom Range</Divider>
            <RangePicker
              style={{ width: '100%' }}
              value={customCreatedRange}
              onChange={(dates) => {
                setCustomCreatedRange(dates);
                if (dates) {
                  setSelectedKeys(['custom']);
                }
              }}
              format="YYYY-MM-DD"
            />
            <Space style={{ width: '100%', justifyContent: 'space-between', marginTop: 8 }}>
              <Button
                size="small"
                onClick={() => {
                  setCustomCreatedRange(null);
                  clearFilters();
                }}
              >
                Reset
              </Button>
              <Button
                type="primary"
                size="small"
                onClick={() => confirm()}
                disabled={selectedKeys[0] === 'custom' && !customCreatedRange}
              >
                OK
              </Button>
            </Space>
          </Space>
        </div>
      ),
      onFilter: (value, record) => {
        if (value === 'all') return true;
        if (value === 'custom' && customCreatedRange) {
          const createdDate = dayjs(record.created_at);
          return createdDate.isAfter(customCreatedRange[0].startOf('day')) && 
                 createdDate.isBefore(customCreatedRange[1].endOf('day'));
        }
        const createdDate = dayjs(record.created_at);
        const now = dayjs();
        if (value === 'today') return createdDate.isSame(now, 'day');
        if (value === 'week') return createdDate.isAfter(now.subtract(7, 'day'));
        if (value === 'month') return createdDate.isAfter(now.subtract(1, 'month'));
        if (value === '3months') return createdDate.isAfter(now.subtract(3, 'month'));
        return true;
      },
      render: (date) => (
        <Tooltip title={dayjs(date).format('YYYY-MM-DD HH:mm')}>
          <Text type="secondary">{dayjs(date).fromNow()}</Text>
        </Tooltip>
      ),
    },
    {
      title: () => (
        <div>
          <div>Last Updated</div>
          {customUpdatedRange && (
            <Text style={{ fontSize: 10, color: '#52c41a' }}>
              {customUpdatedRange[0].format('MMM DD')} - {customUpdatedRange[1].format('MMM DD')}
            </Text>
          )}
        </div>
      ),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      sorter: (a, b) => new Date(a.updated_at || a.created_at) - new Date(b.updated_at || b.created_at),
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }) => (
        <div style={{ padding: 16, width: 300 }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Button
              type={!customUpdatedRange && selectedKeys[0] === 'all' ? 'primary' : 'default'}
              block
              onClick={() => {
                setCustomUpdatedRange(null);
                setSelectedKeys(['all']);
                confirm();
              }}
            >
              All Time
            </Button>
            <Button
              type={selectedKeys[0] === 'today' ? 'primary' : 'default'}
              block
              onClick={() => {
                setCustomUpdatedRange(null);
                setSelectedKeys(['today']);
                confirm();
              }}
            >
              Today
            </Button>
            <Button
              type={selectedKeys[0] === 'week' ? 'primary' : 'default'}
              block
              onClick={() => {
                setCustomUpdatedRange(null);
                setSelectedKeys(['week']);
                confirm();
              }}
            >
              This Week
            </Button>
            <Button
              type={selectedKeys[0] === 'month' ? 'primary' : 'default'}
              block
              onClick={() => {
                setCustomUpdatedRange(null);
                setSelectedKeys(['month']);
                confirm();
              }}
            >
              This Month
            </Button>
            <Divider style={{ margin: '8px 0' }}>Custom Range</Divider>
            <RangePicker
              style={{ width: '100%' }}
              value={customUpdatedRange}
              onChange={(dates) => {
                setCustomUpdatedRange(dates);
                if (dates) {
                  setSelectedKeys(['custom']);
                }
              }}
              format="YYYY-MM-DD"
            />
            <Space style={{ width: '100%', justifyContent: 'space-between', marginTop: 8 }}>
              <Button
                size="small"
                onClick={() => {
                  setCustomUpdatedRange(null);
                  clearFilters();
                }}
              >
                Reset
              </Button>
              <Button
                type="primary"
                size="small"
                onClick={() => confirm()}
                disabled={selectedKeys[0] === 'custom' && !customUpdatedRange}
              >
                OK
              </Button>
            </Space>
          </Space>
        </div>
      ),
      onFilter: (value, record) => {
        if (value === 'all') return true;
        if (value === 'custom' && customUpdatedRange) {
          const updatedDate = dayjs(record.updated_at || record.created_at);
          return updatedDate.isAfter(customUpdatedRange[0].startOf('day')) && 
                 updatedDate.isBefore(customUpdatedRange[1].endOf('day'));
        }
        const updatedDate = dayjs(record.updated_at || record.created_at);
        const now = dayjs();
        if (value === 'today') return updatedDate.isSame(now, 'day');
        if (value === 'week') return updatedDate.isAfter(now.subtract(7, 'day'));
        if (value === 'month') return updatedDate.isAfter(now.subtract(1, 'month'));
        return true;
      },
      render: (date, record) => {
        const displayDate = date || record.created_at;
        return (
          <Tooltip title={dayjs(displayDate).format('YYYY-MM-DD HH:mm')}>
            <Text type="secondary">{dayjs(displayDate).fromNow()}</Text>
          </Tooltip>
        );
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      fixed: 'right',
      width: 120,
      render: (_, record) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/leads/${record.lead_id}`)}
          >
            View
          </Button>
          <Dropdown overlay={getActionMenu(record)} trigger={['click']}>
            <Button size="small" icon={<MoreOutlined />} />
          </Dropdown>
        </Space>
      ),
    },
  ];

  // Show loading state
  if (isLoading) {
    return (
      <div style={{ padding: '24px', display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <Space direction="vertical" align="center" size="large">
          <div style={{ fontSize: 48 }}>📊</div>
          <Typography.Title level={4}>Loading leads...</Typography.Title>
        </Space>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', background: '#f0f2f5', minHeight: '100vh' }}>
      {/* Header Stats */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" hoverable>
            <Statistic
              title="Total Leads"
              value={stats.total || 0}
              prefix={<TeamOutlined />}
              valueStyle={{ color: '#1890ff', fontSize: 24 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" hoverable>
            <Statistic
              title="Hot Leads"
              value={stats.hot || 0}
              prefix={<FireOutlined />}
              valueStyle={{ color: '#ff4d4f', fontSize: 24 }}
              suffix={
                <Text type="secondary" style={{ fontSize: 12 }}>
                  / {stats.total || 0}
                </Text>
              }
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" hoverable>
            <Statistic
              title="Warm Leads"
              value={stats.warm || 0}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: '#faad14', fontSize: 24 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" hoverable>
            <Statistic
              title="Enrolled"
              value={stats.enrolled}
              prefix={<StarOutlined />}
              valueStyle={{ color: '#52c41a', fontSize: 24 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" hoverable>
            <Statistic
              title="Avg Score"
              value={stats.avgScore}
              suffix="/ 100"
              valueStyle={{ color: '#722ed1', fontSize: 24 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={4}>
          <Card size="small" hoverable style={{ background: stats.overdue > 0 ? '#fff2e8' : undefined }}>
            <Statistic
              title="Overdue"
              value={stats.overdue}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: stats.overdue > 0 ? '#ff4d4f' : '#8c8c8c', fontSize: 24 }}
            />
          </Card>
        </Col>
      </Row>

      {/* Main Card */}
      <Card
        title={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Title level={4} style={{ margin: 0 }}>
              Lead Management
            </Title>
            <Space>
              <Segmented
                value={quickFilters}
                onChange={setQuickFilters}
                options={[
                  { label: 'All', value: 'all' },
                  { label: 'Hot 🔥', value: 'hot' },
                  { label: 'Warm ⚡', value: 'warm' },
                  { label: 'Today', value: 'today' },
                  { label: 'Overdue', value: 'overdue' },
                ]}
              />
            </Space>
          </div>
        }
        extra={
          <Space>
            <Input.Search
              placeholder="Search leads..."
              allowClear
              style={{ width: 250 }}
              onChange={(e) => setSearchText(e.target.value)}
              prefix={<SearchOutlined />}
            />
            <Button icon={<FilterOutlined />} onClick={() => setFilterDrawerVisible(true)}>
              Filters
            </Button>
            <Tooltip title="Clear all filters">
              <Button 
                icon={<SyncOutlined />} 
                onClick={() => {
                  setSearchText('');
                  setQuickFilters('all');
                  setCustomCreatedRange(null);
                  setCustomUpdatedRange(null);
                  setFilters({});
                  message.success('All filters cleared!');
                }}
              >
                Clear Filters
              </Button>
            </Tooltip>
            <Button icon={<ExportOutlined />} onClick={handleExport}>
              Export
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
              Refresh
            </Button>
            <Button 
              type="primary" 
              icon={<PlusOutlined />} 
              onClick={() => setDrawerVisible(true)}
            >
              Add Lead
            </Button>
          </Space>
        }
      >
        {/* Bulk Actions Bar */}
        {selectedRows.length > 0 && (
          <Alert
            message={
              <Space>
                <Text strong>{selectedRows.length} leads selected</Text>
                <Button size="small" onClick={() => setSelectedRows([])}>Clear Selection</Button>
                <Divider type="vertical" />
                <Button size="small" onClick={() => setBulkDrawerVisible(true)}>Bulk Update</Button>
                <Button size="small" danger>Bulk Delete</Button>
              </Space>
            }
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        {/* Table */}
        <Table
          columns={columns}
          dataSource={leads}
          loading={isLoading}
          rowKey="lead_id"
          scroll={{ x: 1500 }}
          pagination={{
            total: leads.length,
            pageSize: 20,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} leads`,
            position: ['bottomCenter'],
          }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="No leads found"
              >
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawerVisible(true)}>
                  Create First Lead
                </Button>
              </Empty>
            ),
          }}
        />
      </Card>

      {/* Create/Edit Lead Drawer */}
      <Drawer
        title={form.getFieldValue('lead_id') ? 'Edit Lead' : 'Create New Lead'}
        width={600}
        open={drawerVisible}
        onClose={() => {
          setDrawerVisible(false);
          form.resetFields();
        }}
        extra={
          <Space>
            <Button onClick={() => setDrawerVisible(false)}>Cancel</Button>
            <Button type="primary" onClick={() => form.submit()} loading={createLeadMutation.isLoading}>
              {form.getFieldValue('lead_id') ? 'Update' : 'Create'}
            </Button>
          </Space>
        }
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateLead}
        >
          <Form.Item
            name="full_name"
            label="Full Name"
            rules={[{ required: true, message: 'Please enter full name' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="John Doe" size="large" />
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="email" label="Email">
                <Input prefix={<MailOutlined />} placeholder="john@email.com" size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item 
                name="phone" 
                label="Phone"
                rules={[{ required: true, message: 'Please enter phone' }]}
              >
                <Input prefix={<PhoneOutlined />} placeholder="+91-9876543210" size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item 
                name="country" 
                label="Country"
                rules={[{ required: true }]}
              >
                <Select placeholder="Select country" size="large">
                  <Option value="India">🇮🇳 India</Option>
                  <Option value="USA">🇺🇸 USA</Option>
                  <Option value="UK">🇬🇧 UK</Option>
                  <Option value="Canada">🇨🇦 Canada</Option>
                  <Option value="Australia">🇦🇺 Australia</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="source" label="Source">
                <Select placeholder="Lead source" size="large">
                  <Option value="Website">Website</Option>
                  <Option value="Facebook">Facebook</Option>
                  <Option value="Google Ads">Google Ads</Option>
                  <Option value="Instagram">Instagram</Option>
                  <Option value="Referral">Referral</Option>
                  <Option value="Direct">Direct</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Form.Item 
            name="course_interested" 
            label="Course Interested"
            rules={[{ required: true }]}
          >
            <Select 
              placeholder="Select course" 
              size="large"
              showSearch
              onChange={handleCourseChange}
              filterOption={(input, option) =>
                option.children.toLowerCase().includes(input.toLowerCase())
              }
            >
              {courses.map(course => (
                <Option key={course.id} value={course.course_name}>
                  {course.course_name} - ₹{(course.price / 1000).toFixed(0)}K
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="status" label="Status" initialValue="Follow Up">
                <Select size="large">
                  <Option value="Fresh">Fresh</Option>
                  <Option value="Follow Up">Follow Up</Option>
                  <Option value="Warm">Warm</Option>
                  <Option value="Hot">Hot</Option>
                  <Option value="Not Interested">Not Interested</Option>
                  <Option value="Not Answering">Not Answering</Option>
                  <Option value="Enrolled">Enrolled</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="follow_up_date" label="Follow-up Date">
                <DatePicker style={{ width: '100%' }} size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="expected_revenue" label="Expected Revenue">
                <InputNumber
                  style={{ width: '100%' }}
                  size="large"
                  formatter={value => `₹ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={value => value.replace(/₹\s?|(,*)/g, '')}
                  placeholder="Auto-filled from course"
                  min={0}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="actual_revenue" label="Actual Revenue (if enrolled)">
                <InputNumber
                  style={{ width: '100%' }}
                  size="large"
                  formatter={value => `₹ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={value => value.replace(/₹\s?|(,*)/g, '')}
                  placeholder="Enter if enrolled"
                  min={0}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="assigned_to" label="Assign To">
            <Select 
              placeholder="Select user" 
              size="large" 
              allowClear
              showSearch
              filterOption={(input, option) =>
                option.children.toLowerCase().includes(input.toLowerCase())
              }
            >
              {users.map(user => (
                <Option key={user.id} value={user.full_name}>
                  <Space>
                    <Avatar size="small" style={{ backgroundColor: '#1890ff' }}>
                      {user.full_name?.charAt(0)}
                    </Avatar>
                    {user.full_name} - {user.role}
                  </Space>
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="notes" label="Notes">
            <Input.TextArea 
              rows={4} 
              placeholder="Add initial notes about this lead..."
              showCount
              maxLength={500}
            />
          </Form.Item>
        </Form>
      </Drawer>

      {/* Bulk Update Drawer */}
      <Drawer
        title={`Bulk Update ${selectedRows.length} Leads`}
        width={500}
        open={bulkDrawerVisible}
        onClose={() => setBulkDrawerVisible(false)}
        extra={
          <Space>
            <Button onClick={() => setBulkDrawerVisible(false)}>Cancel</Button>
            <Button type="primary" onClick={() => bulkForm.submit()}>
              Update All
            </Button>
          </Space>
        }
      >
        <Form form={bulkForm} layout="vertical" onFinish={handleBulkUpdate}>
          <Alert
            message="These changes will apply to all selected leads"
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
          />
          
          <Form.Item name="status" label="Status">
            <Select placeholder="Keep unchanged" allowClear>
              <Option value="Fresh">Fresh</Option>
              <Option value="Follow Up">Follow Up</Option>
              <Option value="Warm">Warm</Option>
              <Option value="Hot">Hot</Option>
              <Option value="Not Interested">Not Interested</Option>
            </Select>
          </Form.Item>

          <Form.Item name="assigned_to" label="Assign To">
            <Select 
              placeholder="Keep unchanged" 
              allowClear
              showSearch
              filterOption={(input, option) =>
                option.children.toLowerCase().includes(input.toLowerCase())
              }
            >
              {users.map(user => (
                <Option key={user.id} value={user.full_name}>
                  <Space>
                    <Avatar size="small" style={{ backgroundColor: '#1890ff' }}>
                      {user.full_name?.charAt(0)}
                    </Avatar>
                    {user.full_name} - {user.role}
                  </Space>
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="follow_up_date" label="Follow-up Date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Drawer>

      {/* Advanced Filters Drawer */}
      <Drawer
        title="Advanced Filters"
        width={400}
        open={filterDrawerVisible}
        onClose={() => setFilterDrawerVisible(false)}
        extra={
          <Button onClick={() => {
            setFilters({});
            setFilterDrawerVisible(false);
          }}>
            Clear All
          </Button>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          <div>
            <Text strong>AI Score Range</Text>
            <InputNumber
              min={0}
              max={100}
              style={{ width: '100%', marginTop: 8 }}
              placeholder="Min score"
              onChange={(value) => setFilters(f => ({ ...f, min_score: value }))}
            />
          </div>

          <div>
            <Text strong>Created Date Range</Text>
            <RangePicker
              style={{ width: '100%', marginTop: 8 }}
              onChange={(dates) => setFilters(f => ({
                ...f,
                start_date: dates?.[0]?.format('YYYY-MM-DD'),
                end_date: dates?.[1]?.format('YYYY-MM-DD'),
              }))}
            />
          </div>

          <div>
            <Text strong>Source</Text>
            <Select
              mode="multiple"
              style={{ width: '100%', marginTop: 8 }}
              placeholder="Select sources"
              onChange={(value) => setFilters(f => ({ ...f, sources: value }))}
            >
              <Option value="Website">Website</Option>
              <Option value="Facebook">Facebook</Option>
              <Option value="Google Ads">Google Ads</Option>
              <Option value="Instagram">Instagram</Option>
              <Option value="Referral">Referral</Option>
            </Select>
          </div>

          <Button 
            type="primary" 
            block 
            onClick={() => setFilterDrawerVisible(false)}
          >
            Apply Filters
          </Button>
        </Space>
      </Drawer>
    </div>
  );
};

export default LeadsPageEnhanced;
