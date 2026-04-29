import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card,
  Row,
  Col,
  Descriptions,
  Tag,
  Button,
  Input,
  Select,
  Form,
  message,
  Timeline,
  Progress,
  Space,
  Modal,
  DatePicker,
  Divider,
  Alert,
  Badge,
  Statistic,
} from 'antd';
import {
  ArrowLeftOutlined,
  WhatsAppOutlined,
  MailOutlined,
  PhoneOutlined,
  SaveOutlined,
  ThunderboltOutlined,
  DollarOutlined,
  WarningOutlined,
  FireOutlined,
} from '@ant-design/icons';
import { leadsAPI, coursesAPI, counselorsAPI } from '../api/api';
import dayjs from 'dayjs';
import ActivityTimeline from '../features/activity/ActivityTimeline';
import CallTimeWidget from '../components/leads/CallTimeWidget';
import WhatsAppTemplateDrawer from '../components/whatsapp/WhatsAppTemplateDrawer';
import { isFeatureEnabled } from '../config/featureFlags';

const { TextArea } = Input;
const { Option } = Select;

const LeadDetails = () => {
  const { leadId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [noteForm] = Form.useForm();
  const [leadForm] = Form.useForm();
  const [lossForm] = Form.useForm();
  const [emailModal, setEmailModal] = useState(false);
  const [whatsappModal, setWhatsappModal] = useState(false);
  const [templateDrawer, setTemplateDrawer] = useState(false);
  const [lossModal, setLossModal] = useState(false);
  const [pendingStatus, setPendingStatus] = useState(null);
  const [isEditing, setIsEditing] = useState(false);

  // Fetch lead details
  const { data: lead, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['lead', leadId],
    queryFn: () => leadsAPI.getById(leadId).then(res => res.data),
    refetchOnMount: 'always', // Always fetch fresh data when component mounts
    refetchOnWindowFocus: true, // Refetch when user returns to tab
    staleTime: 0, // Consider data stale immediately
    retry: 1, // Only retry once on failure
  });

  // Update form when lead data changes
  React.useEffect(() => {
    if (lead) {
      leadForm.setFieldsValue({
        course_interested: lead.course_interested,
        status: lead.status,
        follow_up_date: lead.follow_up_date ? dayjs(lead.follow_up_date) : null,
        assigned_to: lead.assigned_to,
      });
    }
  }, [lead, leadForm]);

  const { data: courses } = useQuery({
    queryKey: ['courses'],
    queryFn: () => coursesAPI.getAll().then(res => Array.isArray(res.data) ? res.data : [])
  });

  const { data: counselors } = useQuery({
    queryKey: ['counselors'],
    queryFn: () => counselorsAPI.getAll().then(res => Array.isArray(res.data) ? res.data : [])
  });

  // Update lead mutation
  const updateLeadMutation = useMutation({
    mutationFn: (data) => leadsAPI.update(leadId, data),
    onSuccess: () => {
      message.success('Lead updated successfully!');
      setIsEditing(false);
      // Invalidate and refetch to ensure UI updates
      queryClient.invalidateQueries({ queryKey: ['lead', leadId] });
      queryClient.invalidateQueries({ queryKey: ['leads'] }); // Invalidate leads list
      refetch();
    },
    onError: (error) => {
      message.error(`Failed to update lead: ${error.message}`);
    },
  });

  // Handle form submission
  const handleSaveChanges = (values) => {
    // Check if status changed to loss status
    const statusChanged = values.status !== lead.status;
    const isLossStatus = values.status === 'Not Interested' || values.status === 'Junk';
    
    if (statusChanged && isLossStatus) {
      setPendingStatus(values.status);
      setLossModal(true);
      return;
    }
    
    // Convert DatePicker value to ISO string
    const updateData = {
      ...values,
      follow_up_date: values.follow_up_date ? values.follow_up_date.toISOString() : null,
    };
    updateLeadMutation.mutate(updateData);
  };

  // Add note mutation
  const addNoteMutation = useMutation({
    mutationFn: (data) => leadsAPI.addNote(leadId, data),
    onSuccess: () => {
      message.success('Note added successfully!');
      noteForm.resetFields();
      // Invalidate and refetch to ensure notes update
      queryClient.invalidateQueries({ queryKey: ['lead', leadId] });
      refetch();
    },
    onError: (error) => {
      message.error(`Failed to add note: ${error.message}`);
    },
  });

  const handleAddNote = (values) => {
    addNoteMutation.mutate({
      content: values.content,
      channel: values.channel || 'manual',
      created_by: values.created_by, // Backend will use authenticated user's name
    });
  };

  const handleLossSubmit = () => {
    lossForm.validateFields().then(values => {
      const formValues = leadForm.getFieldsValue();
      updateLeadMutation.mutate({
        status: pendingStatus,
        loss_reason: values.loss_reason,
        loss_note: values.loss_note || '',
        course_interested: formValues.course_interested,
        follow_up_date: formValues.follow_up_date ? formValues.follow_up_date.toISOString() : null,
        assigned_to: formValues.assigned_to,
      });
      setLossModal(false);
      lossForm.resetFields();
      setPendingStatus(null);
    });
  };

  if (isLoading) {
    return <div style={{ padding: '40px', textAlign: 'center' }}>Loading lead details...</div>;
  }

  if (isError || !lead) {
    const errMsg = error?.response?.status === 404
      ? 'Lead not found. It may have been deleted.'
      : `Failed to load lead: ${error?.message || 'Unknown error'}`;
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <p style={{ color: '#ff4d4f', marginBottom: '16px' }}>{errMsg}</p>
        <button onClick={() => navigate('/leads')} style={{ marginRight: '8px' }}>← Back to Leads</button>
        <button onClick={() => refetch()}>Retry</button>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/leads')}
          >
            Back
          </Button>
          <div>
            <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 600 }}>
              {lead?.full_name}
            </h1>
            <div style={{ color: '#8c8c8c', marginTop: '4px' }}>
              {lead?.lead_id} • Created {dayjs(lead?.created_at).format('MMM DD, YYYY')}
            </div>
          </div>
        </div>

        <Space>
          <Button
            icon={<PhoneOutlined />}
            href={`tel:${lead?.phone}`}
          >
            Call
          </Button>
          <Button.Group>
            <Button
              icon={<WhatsAppOutlined />}
              style={{ background: '#25D366', borderColor: '#25D366', color: '#fff' }}
              onClick={() => setWhatsappModal(true)}
            >
              WhatsApp
            </Button>
            <Button
              style={{
                background: '#1ebe57', borderColor: '#1ebe57', color: '#fff',
                borderLeft: '1px solid rgba(255,255,255,0.35)',
              }}
              onClick={() => setTemplateDrawer(true)}
              title="Template library"
            >
              📋
            </Button>
          </Button.Group>
          <Button
            icon={<MailOutlined />}
            type="primary"
            onClick={() => setEmailModal(true)}
          >
            Email
          </Button>
        </Space>
      </div>

      {/* AI Insights Alert */}
      {lead?.next_action && (
        <Alert
          message={<span><ThunderboltOutlined /> AI Recommendation</span>}
          description={
            <div>
              <div style={{ fontWeight: 600, marginBottom: '8px' }}>{lead.next_action}</div>
              <div style={{ fontSize: '12px', color: '#8c8c8c' }}>
                Priority: {lead.priority_level} • Follow up: {lead.follow_up_date ? dayjs(lead.follow_up_date).format('MMM DD, hh:mm A') : 'Not set'}
              </div>
            </div>
          }
          type={
            lead.ai_segment === 'Hot' ? 'error' :
            lead.ai_segment === 'Warm' ? 'warning' : 'info'
          }
          showIcon
          style={{ marginBottom: '24px' }}
        />
      )}

      <Row gutter={[24, 24]}>
        {/* Left Column */}
        <Col xs={24} lg={16}>
          {/* Lead Information */}
          <Card 
            title="Lead Information"
            extra={
              <Space>
                {!isEditing ? (
                  <Button type="primary" onClick={() => setIsEditing(true)}>
                    Edit
                  </Button>
                ) : (
                  <>
                    <Button onClick={() => {
                      setIsEditing(false);
                      leadForm.setFieldsValue({
                        course_interested: lead.course_interested,
                        status: lead.status,
                        follow_up_date: lead.follow_up_date ? dayjs(lead.follow_up_date) : null,
                        assigned_to: lead.assigned_to,
                      });
                    }}>
                      Cancel
                    </Button>
                    <Button 
                      type="primary" 
                      icon={<SaveOutlined />}
                      loading={updateLeadMutation.isLoading}
                      onClick={() => leadForm.submit()}
                    >
                      Save
                    </Button>
                  </>
                )}
              </Space>
            }
            style={{ marginBottom: '24px' }}
          >
            <Form form={leadForm} onFinish={handleSaveChanges} layout="vertical">
              <Descriptions column={2} bordered>
                <Descriptions.Item label="Full Name">
                  {lead?.full_name}
                </Descriptions.Item>
                <Descriptions.Item label="Email">
                  {lead?.email || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="Phone">
                  {lead?.phone}
                </Descriptions.Item>
                <Descriptions.Item label="WhatsApp">
                  {lead?.whatsapp || lead?.phone}
                </Descriptions.Item>
                <Descriptions.Item label="Country">
                  <Tag color="blue">{lead?.country}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Source">
                  <Tag>{lead?.source}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Course Interested" span={2}>
                  {!isEditing ? (
                    <span>{lead?.course_interested}</span>
                  ) : (
                    <Form.Item name="course_interested" noStyle>
                      <Select style={{ width: '100%' }}>
                        {courses?.map(course => (
                          <Option key={course.id} value={course.course_name}>
                            {course.course_name}
                          </Option>
                        ))}
                      </Select>
                    </Form.Item>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="Status">
                  {!isEditing ? (
                    <Tag color={
                      lead?.status === 'Enrolled' ? 'green' :
                      lead?.status === 'Hot' ? 'red' :
                      lead?.status === 'Warm' ? 'orange' :
                      lead?.status === 'Not Interested' ? 'red' :
                      lead?.status === 'Junk' ? 'red' : 'blue'
                    }>
                      {lead?.status}
                    </Tag>
                  ) : (
                    <Form.Item name="status" noStyle>
                      <Select style={{ width: '100%' }}>
                        <Option value="Fresh">Fresh</Option>
                        <Option value="Follow Up">Follow Up</Option>
                        <Option value="Warm">Warm</Option>
                        <Option value="Hot">Hot</Option>
                        <Option value="Not Interested">Not Interested</Option>
                        <Option value="Junk">Junk</Option>
                        <Option value="Not Answering">Not Answering</Option>
                        <Option value="Enrolled">Enrolled</Option>
                      </Select>
                    </Form.Item>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="Follow-up Date">
                  {!isEditing ? (
                    <span>
                      {lead?.follow_up_date ? dayjs(lead.follow_up_date).format('MMM DD, YYYY hh:mm A') : '-'}
                    </span>
                  ) : (
                    <Form.Item name="follow_up_date" noStyle>
                      <DatePicker
                        showTime
                        style={{ width: '100%' }}
                        format="MMM DD, YYYY hh:mm A"
                      />
                    </Form.Item>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="Assigned To" span={2}>
                  {!isEditing ? (
                    <span>{lead?.assigned_to || '-'}</span>
                  ) : (
                    <Form.Item name="assigned_to" noStyle>
                      <Select style={{ width: '100%' }} allowClear>
                        {counselors?.map(counselor => (
                          <Option key={counselor.id} value={counselor.name}>
                            {counselor.name}
                          </Option>
                        ))}
                      </Select>
                    </Form.Item>
                  )}
                </Descriptions.Item>
              </Descriptions>
            </Form>
          </Card>

          {/* Notes Section */}
          <Card title="Notes & Communication History">
            <Form form={noteForm} onFinish={handleAddNote} layout="vertical">
              <Form.Item name="content" rules={[{ required: true, message: 'Please enter note' }]}>
                <TextArea
                  rows={4}
                  placeholder="Add note about conversation, objections, requirements..."
                />
              </Form.Item>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="channel">
                    <Select placeholder="Channel" defaultValue="manual">
                      <Option value="manual">Manual Note</Option>
                      <Option value="call">Phone Call</Option>
                      <Option value="whatsapp">WhatsApp</Option>
                      <Option value="email">Email</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="created_by">
                    <Select placeholder="Counselor" defaultValue={counselors?.[0]?.name}>
                      {counselors?.map(counselor => (
                        <Option key={counselor.id} value={counselor.name}>
                          {counselor.name}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                </Col>
              </Row>
              <Button
                type="primary"
                htmlType="submit"
                icon={<SaveOutlined />}
                loading={addNoteMutation.isLoading}
              >
                Add Note
              </Button>
            </Form>

            <Divider />

            <Timeline style={{ marginTop: '24px' }}>
              {lead?.notes?.map((note, index) => (
                <Timeline.Item
                  key={note.id}
                  color={
                    note.channel === 'whatsapp' ? 'green' :
                    note.channel === 'email' ? 'blue' :
                    note.channel === 'call' ? 'orange' : 'gray'
                  }
                >
                  <div style={{ marginBottom: '8px' }}>
                    <Tag color={
                      note.channel === 'whatsapp' ? 'green' :
                      note.channel === 'email' ? 'blue' :
                      note.channel === 'call' ? 'orange' : 'default'
                    }>
                      {note.channel}
                    </Tag>
                    <span style={{ fontWeight: 600, marginLeft: '8px' }}>
                      {note.created_by}
                    </span>
                    <span style={{ color: '#8c8c8c', marginLeft: '8px', fontSize: '12px' }}>
                      {dayjs(note.created_at).format('MMM DD, YYYY hh:mm A')}
                    </span>
                  </div>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{note.content}</div>
                </Timeline.Item>
              ))}
            </Timeline>
          </Card>
        </Col>

        {/* Right Column - AI Insights */}
        <Col xs={24} lg={8}>
          {/* AI Score Card */}
          <Card
            title={<span><ThunderboltOutlined /> AI Lead Score</span>}
            style={{ marginBottom: '24px' }}
          >
            <div style={{ textAlign: 'center', marginBottom: '24px' }}>
              <Progress
                type="circle"
                percent={lead?.ai_score}
                strokeColor={
                  lead?.ai_score >= 75 ? '#ff4d4f' :
                  lead?.ai_score >= 50 ? '#faad14' :
                  lead?.ai_score >= 25 ? '#52c41a' : '#8c8c8c'
                }
                format={(percent) => (
                  <div>
                    <div style={{ fontSize: '32px', fontWeight: 600 }}>{percent.toFixed(0)}</div>
                    <div style={{ fontSize: '12px', color: '#8c8c8c' }}>AI Score</div>
                  </div>
                )}
              />
            </div>

            <Divider />

            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: '4px' }}>Segment</div>
              <Badge
                color={
                  lead?.ai_segment === 'Hot' ? 'red' :
                  lead?.ai_segment === 'Warm' ? 'orange' :
                  lead?.ai_segment === 'Cold' ? 'green' : 'default'
                }
                text={<span style={{ fontSize: '16px', fontWeight: 600 }}>{lead?.ai_segment}</span>}
              />
            </div>

            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: '4px' }}>Conversion Probability</div>
              <div style={{ fontSize: '16px', fontWeight: 600 }}>
                {((lead?.conversion_probability || 0) * 100).toFixed(1)}%
              </div>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: '4px' }}>Buying Signal Strength</div>
              <Progress
                percent={lead?.buying_signal_strength}
                strokeColor="#52c41a"
                format={(percent) => `${percent.toFixed(0)}`}
              />
            </div>

            {lead?.primary_objection && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: '4px' }}>Primary Objection</div>
                <Tag color="orange">{lead.primary_objection}</Tag>
              </div>
            )}

            {lead?.loss_reason && (
              <div style={{ marginBottom: '16px', background: '#fff2f0', padding: '10px 12px', borderRadius: 6, borderLeft: '3px solid #f5222d' }}>
                <div style={{ fontSize: '12px', color: '#f5222d', fontWeight: 600, marginBottom: 4 }}>Loss Reason</div>
                <Tag color="red">{lead.loss_reason}</Tag>
                {lead.loss_note && <div style={{ marginTop: 6, fontSize: 12, color: '#666' }}>{lead.loss_note}</div>}
              </div>
            )}

            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: '4px' }}>Churn Risk</div>
              <Progress
                percent={lead?.churn_risk * 100}
                strokeColor="#ff4d4f"
                format={(percent) => `${percent.toFixed(0)}%`}
              />
            </div>
          </Card>

          {/* Revenue Card */}
          <Card title={<span><DollarOutlined /> Revenue</span>} style={{ marginBottom: '24px' }}>
            {lead?.status === 'Enrolled' ? (
              <Statistic
                title="Total Revenue"
                value={lead?.actual_revenue}
                precision={0}
                prefix="₹"
                suffix=""
                valueStyle={{ color: '#52c41a', fontSize: '28px' }}
              />
            ) : (
              <Statistic
                title="Expected Revenue"
                value={lead?.expected_revenue}
                precision={0}
                prefix="₹"
                suffix=""
                valueStyle={{ color: '#faad14', fontSize: '28px' }}
              />
            )}

            {lead?.status === 'Enrolled' && (
              <div style={{ marginTop: '16px' }}>
                <Form.Item label="Actual Revenue (₹)">
                  <Input
                    type="number"
                    defaultValue={lead?.actual_revenue}
                    onBlur={(e) => handleUpdateField('actual_revenue', parseFloat(e.target.value))}
                  />
                </Form.Item>
              </div>
            )}
          </Card>

          {/* Best Time to Call */}
          <Card
            title={
              <span>
                <PhoneOutlined style={{ marginRight: 8, color: '#10b981' }} />
                Best Time to Call
              </span>
            }
            style={{ marginBottom: '24px' }}
          >
            <CallTimeWidget country={lead?.country} />
          </Card>

          {/* Recommended Script */}
          {lead?.recommended_script && (
            <Card title="Recommended Script" style={{ marginBottom: '24px' }}>
              <div style={{ whiteSpace: 'pre-wrap', fontSize: '13px', lineHeight: '1.6' }}>
                {lead.recommended_script}
              </div>
            </Card>
          )}

          {/* Activity Timeline */}
          {isFeatureEnabled('ACTIVITY_TIMELINE') && (
            <Card title="Activity Timeline" style={{ marginBottom: '24px' }}>
              <ActivityTimeline leadId={leadId} />
            </Card>
          )}
        </Col>
      </Row>

      {/* WhatsApp Modal */}
      <Modal
        title={<span><WhatsAppOutlined /> Send WhatsApp Message</span>}
        open={whatsappModal}
        onCancel={() => setWhatsappModal(false)}
        footer={null}
      >
        <Form
          onFinish={(values) => {
            leadsAPI.sendWhatsApp(leadId, values.message)
              .then(() => {
                message.success('WhatsApp message queued!');
                setWhatsappModal(false);
              })
              .catch(() => message.error('Failed to send WhatsApp'));
          }}
        >
          <Form.Item name="message" rules={[{ required: true }]}>
            <TextArea rows={6} placeholder="Type your message..." />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            Send Message
          </Button>
        </Form>
      </Modal>

      {/* Email Modal */}
      <Modal
        title={<span><MailOutlined /> Send Email</span>}
        open={emailModal}
        onCancel={() => setEmailModal(false)}
        footer={null}
        width={600}
      >
        <Form
          onFinish={(values) => {
            leadsAPI.sendEmail(leadId, values.subject, values.body)
              .then(() => {
                message.success('Email queued!');
                setEmailModal(false);
              })
              .catch(() => message.error('Failed to send email'));
          }}
        >
          <Form.Item name="subject" label="Subject" rules={[{ required: true }]}>
            <Input placeholder="Email subject" />
          </Form.Item>
          <Form.Item name="body" label="Message" rules={[{ required: true }]}>
            <TextArea rows={8} placeholder="Email message..." />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            Send Email
          </Button>
        </Form>
      </Modal>

      {/* WhatsApp Template Drawer */}
      <WhatsAppTemplateDrawer
        open={templateDrawer}
        onClose={() => setTemplateDrawer(false)}
        lead={lead}
      />

      {/* Loss Reason Modal */}
      <Modal
        open={lossModal}
        title={
          <span>
            <WarningOutlined style={{ color: '#f5222d', marginRight: 8 }} />
            Why is this lead {pendingStatus}?
          </span>
        }
        onCancel={() => { setLossModal(false); setPendingStatus(null); lossForm.resetFields(); }}
        onOk={handleLossSubmit}
        okText="Confirm & Save"
        okButtonProps={{ danger: true }}
        confirmLoading={updateLeadMutation.isPending}
        width={460}
      >
        <div style={{ marginBottom: 12, color: '#666', fontSize: 13 }}>
          Recording a reason helps the team learn what's not working and improve future outreach.
        </div>
        <Form form={lossForm} layout="vertical">
          <Form.Item
            name="loss_reason"
            label="Reason"
            rules={[{ required: true, message: 'Please select a reason' }]}
          >
            <Select placeholder="Select the main reason">
              <Option value="Price too high">Price too high</Option>
              <Option value="Went with competitor">Went with a competitor</Option>
              <Option value="Not the right course">Not the right course</Option>
              <Option value="Cannot take time off work">Cannot take time off work</Option>
              <Option value="No response / Unreachable">No response / Unreachable</Option>
              <Option value="Not eligible">Not eligible for the course</Option>
              <Option value="Needs more time">Needs more time to decide</Option>
              <Option value="Financial constraints">Financial constraints</Option>
              <Option value="Already enrolled elsewhere">Already enrolled elsewhere</Option>
              <Option value="Other">Other</Option>
            </Select>
          </Form.Item>
          <Form.Item name="loss_note" label="Additional Notes (optional)">
            <TextArea rows={3} placeholder="Any extra details about why this lead didn't convert..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default LeadDetails;
