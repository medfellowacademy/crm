import React, { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card,
  Tabs,
  Button,
  Input,
  List,
  Empty,
  Tag,
  Select,
  AutoComplete,
  Upload,
  Popconfirm,
  message,
  Spin,
  Typography,
  Row,
  Col,
} from 'antd';
import {
  SendOutlined,
  PlusOutlined,
  DeleteOutlined,
  PaperClipOutlined,
  RobotOutlined,
  UserOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { aiChatAPI, leadsAPI } from '../api/api';

const { TextArea } = Input;
const { Text } = Typography;

const CATEGORY_LABEL = { course: 'Course Info', policy: 'Policy / SOP', other: 'Other' };
const CATEGORY_COLOR = { course: 'blue', policy: 'purple', other: 'default' };

function ChatPanel() {
  const queryClient = useQueryClient();
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [input, setInput] = useState('');
  const [leadSearch, setLeadSearch] = useState('');
  const [selectedLead, setSelectedLead] = useState(null);
  const scrollRef = useRef(null);

  const { data: sessions = [] } = useQuery({
    queryKey: ['ai-chat-sessions'],
    queryFn: () => aiChatAPI.listSessions().then(res => res.data),
  });

  const { data: messages = [], isLoading: messagesLoading } = useQuery({
    queryKey: ['ai-chat-messages', activeSessionId],
    queryFn: () => aiChatAPI.getMessages(activeSessionId).then(res => res.data),
    enabled: !!activeSessionId,
  });

  const { data: leadOptions = [] } = useQuery({
    queryKey: ['ai-chat-lead-search', leadSearch],
    queryFn: () => leadsAPI.getAll({ search: leadSearch, limit: 10 }).then(res => res.data?.leads || []),
    enabled: leadSearch.length > 1,
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const createSessionMutation = useMutation({
    mutationFn: () => aiChatAPI.createSession(selectedLead ? { lead_id: selectedLead.lead_id, title: `Re: ${selectedLead.full_name}` } : {}),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['ai-chat-sessions'] });
      setActiveSessionId(res.data.id);
      setSelectedLead(null);
      setLeadSearch('');
    },
  });

  const deleteSessionMutation = useMutation({
    mutationFn: (id) => aiChatAPI.deleteSession(id),
    onSuccess: (_res, id) => {
      queryClient.invalidateQueries({ queryKey: ['ai-chat-sessions'] });
      if (activeSessionId === id) setActiveSessionId(null);
    },
  });

  const sendMessageMutation = useMutation({
    mutationFn: (content) => aiChatAPI.sendMessage(activeSessionId, content),
    onSuccess: () => {
      setInput('');
      queryClient.invalidateQueries({ queryKey: ['ai-chat-messages', activeSessionId] });
      queryClient.invalidateQueries({ queryKey: ['ai-chat-sessions'] });
    },
    onError: (error) => {
      if (error?.response?.status === 503) {
        message.warning('AI chat is not configured yet. Set ANTHROPIC_API_KEY in the backend.');
      } else {
        message.error('Failed to send message');
      }
      queryClient.invalidateQueries({ queryKey: ['ai-chat-messages', activeSessionId] });
    },
  });

  const attachMutation = useMutation({
    mutationFn: (file) => aiChatAPI.attachFile(activeSessionId, file),
    onSuccess: () => {
      message.success('File attached — you can now ask about it');
      queryClient.invalidateQueries({ queryKey: ['ai-chat-messages', activeSessionId] });
    },
    onError: (error) => {
      message.error(error?.response?.data?.detail || 'Failed to attach file');
    },
  });

  const handleSend = () => {
    const content = input.trim();
    if (!content || !activeSessionId) return;
    sendMessageMutation.mutate(content);
  };

  const activeSession = sessions.find(s => s.id === activeSessionId);

  return (
    <Row gutter={16} style={{ height: 'calc(100vh - 220px)', minHeight: 500 }}>
      {/* Sessions sidebar */}
      <Col span={6} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={{ marginBottom: 12 }}>
          {leadSearch !== null && (
            <AutoComplete
              style={{ width: '100%', marginBottom: 8 }}
              placeholder="Optionally link a lead…"
              value={selectedLead ? selectedLead.full_name : leadSearch}
              onSearch={setLeadSearch}
              onSelect={(_, option) => setSelectedLead(option.lead)}
              options={leadOptions.map(l => ({ value: l.full_name, label: `${l.full_name} (${l.lead_id})`, lead: l }))}
              allowClear
              onClear={() => { setSelectedLead(null); setLeadSearch(''); }}
            />
          )}
          <Button
            type="primary"
            icon={<PlusOutlined />}
            block
            loading={createSessionMutation.isPending}
            onClick={() => createSessionMutation.mutate()}
          >
            New Chat{selectedLead ? ` (${selectedLead.full_name})` : ''}
          </Button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <List
            dataSource={sessions}
            locale={{ emptyText: <Empty description="No chats yet" /> }}
            renderItem={(s) => (
              <List.Item
                onClick={() => setActiveSessionId(s.id)}
                style={{
                  cursor: 'pointer', padding: '8px 10px', borderRadius: 6,
                  background: activeSessionId === s.id ? '#e6f4ff' : 'transparent',
                  marginBottom: 4,
                }}
                actions={[
                  <Popconfirm
                    key="del"
                    title="Delete this chat?"
                    onConfirm={(e) => { e?.stopPropagation?.(); deleteSessionMutation.mutate(s.id); }}
                    onCancel={(e) => e?.stopPropagation?.()}
                  >
                    <DeleteOutlined onClick={(e) => e.stopPropagation()} style={{ color: '#bfbfbf' }} />
                  </Popconfirm>,
                ]}
              >
                <div style={{ overflow: 'hidden' }}>
                  <div style={{ fontWeight: 500, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {s.title || 'New chat'}
                  </div>
                  {s.lead_id && <Tag color="geekblue" style={{ fontSize: 10, marginTop: 2 }}>Lead: {s.lead_id}</Tag>}
                </div>
              </List.Item>
            )}
          />
        </div>
      </Col>

      {/* Chat window */}
      <Col span={18} style={{ height: '100%' }}>
        <Card
          style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
          styles={{ body: { flex: 1, display: 'flex', flexDirection: 'column', height: '100%', padding: 16 } }}
        >
          {!activeSessionId ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Empty description="Start a new chat to ask MedFellow AI anything" />
            </div>
          ) : (
            <>
              <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', marginBottom: 12, paddingRight: 4 }}>
                {messagesLoading ? (
                  <Spin />
                ) : messages.length === 0 ? (
                  <Empty description="Ask a question to get started" />
                ) : (
                  messages.map((m) => (
                    <div
                      key={m.id}
                      style={{
                        display: 'flex',
                        justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                        marginBottom: 12,
                      }}
                    >
                      <div
                        style={{
                          maxWidth: '75%',
                          background: m.role === 'user' ? '#1677ff' : '#f5f5f5',
                          color: m.role === 'user' ? '#fff' : '#262626',
                          borderRadius: 10,
                          padding: '8px 12px',
                          whiteSpace: 'pre-wrap',
                          fontSize: 13.5,
                        }}
                      >
                        <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 4 }}>
                          {m.role === 'user' ? <UserOutlined /> : <RobotOutlined />}{' '}
                          {m.role === 'user' ? 'You' : 'MedFellow AI'}
                          {m.attachment_name && <Tag style={{ marginLeft: 6 }}>{m.attachment_name}</Tag>}
                        </div>
                        {m.content}
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div style={{ display: 'flex', gap: 8 }}>
                <Upload
                  showUploadList={false}
                  beforeUpload={(file) => { attachMutation.mutate(file); return false; }}
                >
                  <Button icon={<PaperClipOutlined />} loading={attachMutation.isPending} />
                </Upload>
                <TextArea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); handleSend(); } }}
                  placeholder="Ask about a course, policy, or this lead…"
                  autoSize={{ minRows: 1, maxRows: 4 }}
                  style={{ flex: 1 }}
                />
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  loading={sendMessageMutation.isPending}
                  onClick={handleSend}
                >
                  Send
                </Button>
              </div>
              {activeSession?.lead_id && (
                <Text type="secondary" style={{ fontSize: 11, marginTop: 6 }}>
                  This chat has context from lead {activeSession.lead_id}.
                </Text>
              )}
            </>
          )}
        </Card>
      </Col>
    </Row>
  );
}

function KnowledgeBaseTab() {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState(undefined);
  const [title, setTitle] = useState('');
  const [uploadCategory, setUploadCategory] = useState('course');

  const { data: documents = [], isLoading } = useQuery({
    queryKey: ['ai-documents', category],
    queryFn: () => aiChatAPI.listDocuments(category ? { category } : {}).then(res => res.data),
  });

  const uploadMutation = useMutation({
    mutationFn: (file) => aiChatAPI.uploadDocument(file, title || file.name, uploadCategory),
    onSuccess: () => {
      message.success('Document added to knowledge base');
      setTitle('');
      queryClient.invalidateQueries({ queryKey: ['ai-documents'] });
    },
    onError: () => message.error('Upload failed'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => aiChatAPI.deleteDocument(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['ai-documents'] }),
  });

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={8} align="middle">
          <Col span={6}>
            <Input placeholder="Document title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Col>
          <Col span={5}>
            <Select
              value={uploadCategory}
              onChange={setUploadCategory}
              style={{ width: '100%' }}
              options={[
                { value: 'course', label: 'Course Info' },
                { value: 'policy', label: 'Policy / SOP' },
                { value: 'other', label: 'Other' },
              ]}
            />
          </Col>
          <Col span={6}>
            <Upload
              showUploadList={false}
              beforeUpload={(file) => { uploadMutation.mutate(file); return false; }}
            >
              <Button icon={<UploadOutlined />} loading={uploadMutation.isPending} block>
                Upload PDF / Text
              </Button>
            </Upload>
          </Col>
        </Row>
        <Text type="secondary" style={{ fontSize: 12 }}>
          PDF and plain text files are supported. The AI chat searches this content to ground its answers.
        </Text>
      </Card>

      <div style={{ marginBottom: 12 }}>
        <Select
          allowClear
          placeholder="Filter by category"
          style={{ width: 200 }}
          value={category}
          onChange={setCategory}
          options={[
            { value: 'course', label: 'Course Info' },
            { value: 'policy', label: 'Policy / SOP' },
            { value: 'other', label: 'Other' },
          ]}
        />
      </div>

      <List
        loading={isLoading}
        dataSource={documents}
        locale={{ emptyText: <Empty description="No documents yet" /> }}
        renderItem={(doc) => (
          <List.Item
            actions={[
              <Popconfirm key="del" title="Delete this document?" onConfirm={() => deleteMutation.mutate(doc.id)}>
                <Button danger size="small" icon={<DeleteOutlined />} />
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta
              title={<span>{doc.title} <Tag color={CATEGORY_COLOR[doc.category]}>{CATEGORY_LABEL[doc.category]}</Tag></span>}
              description={
                <span style={{ fontSize: 12 }}>
                  {doc.file_name} · uploaded by {doc.uploaded_by} · {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : ''}
                </span>
              }
            />
          </List.Item>
        )}
      />
    </div>
  );
}

const AIChatPage = () => {
  const items = [
    { key: 'chat', label: 'Chat', children: <ChatPanel /> },
    { key: 'kb', label: 'Knowledge Base', children: <KnowledgeBaseTab /> },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>
          <RobotOutlined style={{ marginRight: 8 }} />MedFellow AI Chat
        </h1>
        <div style={{ color: '#8c8c8c', fontSize: 13 }}>
          Ask about courses, policies, or a specific lead. Upload documents so the AI can reference them.
        </div>
      </div>
      <Tabs items={items} />
    </div>
  );
};

export default AIChatPage;
