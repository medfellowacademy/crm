import React, { useState, useEffect, useRef } from 'react';
import {
  Drawer,
  List,
  Badge,
  Avatar,
  Typography,
  Input,
  Button,
  Spin,
  Empty,
  Tag,
  Space,
  Divider,
  message as antMessage,
} from 'antd';
import {
  WhatsAppOutlined,
  SendOutlined,
  UserOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../api/api';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useAuth } from '../../context/AuthContext';
import { hasPermission, PERMISSIONS } from '../../config/rbac';

dayjs.extend(relativeTime);

const { Text, Title } = Typography;
const { TextArea } = Input;

const WhatsAppInbox = ({ open, onClose }) => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeConversation, setActiveConversation] = useState(null);
  const [inputText, setInputText] = useState('');
  const messagesEndRef = useRef(null);

  const canViewAll = hasPermission(user?.role, PERMISSIONS.VIEW_ALL_WHATSAPP);
  const canSend = hasPermission(user?.role, PERMISSIONS.SEND_WHATSAPP);

  // ── Conversations list ──────────────────────────────────────
  const { data: conversations = [], isLoading: loadingConvs } = useQuery({
    queryKey: ['whatsapp-conversations', user?.role],
    queryFn: async () => {
      const res = await api.get('/api/whatsapp/conversations');
      return res.data;
    },
    enabled: open,
    refetchInterval: 15000,
  });

  // ── Message history for active conversation ─────────────────
  const { data: messages = [], isLoading: loadingMsgs } = useQuery({
    queryKey: ['whatsapp-history', activeConversation?.phone_number],
    queryFn: async () => {
      const res = await api.get(
        `/api/whatsapp/history/${encodeURIComponent(activeConversation.phone_number)}`
      );
      return res.data;
    },
    enabled: !!activeConversation,
    refetchInterval: 5000,
  });

  // ── Mark as read when opening a conversation ────────────────
  useEffect(() => {
    if (!activeConversation) return;
    api
      .post('/api/whatsapp/mark-read', { phone_number: activeConversation.phone_number })
      .then(() => {
        queryClient.invalidateQueries({ queryKey: ['whatsapp-conversations'] });
      })
      .catch(() => {});
  }, [activeConversation, queryClient]);

  // ── Scroll to latest message ────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ── Send message ────────────────────────────────────────────
  const sendMutation = useMutation({
    mutationFn: async (text) => {
      const res = await api.post('/api/whatsapp/send', {
        lead_id: activeConversation.lead_id,
        message: text,
      });
      return res.data;
    },
    onSuccess: () => {
      setInputText('');
      queryClient.invalidateQueries({
        queryKey: ['whatsapp-history', activeConversation?.phone_number],
      });
    },
    onError: (err) => {
      antMessage.error(err.response?.data?.detail || 'Failed to send message');
    },
  });

  const handleSend = () => {
    if (!inputText.trim()) return;
    if (!activeConversation?.lead_id) {
      antMessage.warning('This conversation has no linked lead — cannot send.');
      return;
    }
    sendMutation.mutate(inputText.trim());
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ─────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────
  const drawerTitle = activeConversation ? (
    <Space>
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => setActiveConversation(null)}
      />
      <Avatar
        icon={<UserOutlined />}
        style={{ backgroundColor: '#25D366' }}
      />
      <span>{activeConversation.contact_name || activeConversation.phone_number}</span>
      {activeConversation.unread_count > 0 && (
        <Badge count={activeConversation.unread_count} />
      )}
    </Space>
  ) : (
    <Space>
      <WhatsAppOutlined style={{ color: '#25D366', fontSize: 20 }} />
      <span>WhatsApp Inbox</span>
      {canViewAll && <Tag color="blue">All Conversations</Tag>}
      {!canViewAll && <Tag color="green">My Conversations</Tag>}
    </Space>
  );

  return (
    <Drawer
      title={drawerTitle}
      open={open}
      onClose={() => {
        setActiveConversation(null);
        onClose();
      }}
      width={440}
      bodyStyle={{ padding: 0, display: 'flex', flexDirection: 'column', height: '100%' }}
    >
      {/* ── Conversation list ── */}
      {!activeConversation && (
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {loadingConvs ? (
            <div style={{ textAlign: 'center', paddingTop: 40 }}>
              <Spin />
            </div>
          ) : conversations.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="No conversations yet"
              style={{ paddingTop: 60 }}
            />
          ) : (
            <List
              dataSource={conversations}
              renderItem={(conv) => (
                <List.Item
                  key={conv.id}
                  onClick={() => setActiveConversation(conv)}
                  style={{
                    cursor: 'pointer',
                    padding: '12px 16px',
                    borderBottom: '1px solid #f0f0f0',
                  }}
                  className="wa-inbox-row"
                >
                  <List.Item.Meta
                    avatar={
                      <Badge count={conv.unread_count} offset={[-4, 4]}>
                        <Avatar
                          icon={<UserOutlined />}
                          style={{ backgroundColor: '#25D366' }}
                        />
                      </Badge>
                    }
                    title={
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Text strong={conv.unread_count > 0}>
                          {conv.contact_name || conv.phone_number}
                        </Text>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {conv.last_message_time
                            ? dayjs(conv.last_message_time).fromNow()
                            : ''}
                        </Text>
                      </Space>
                    }
                    description={
                      <Text
                        type="secondary"
                        ellipsis
                        style={{ fontSize: 12, fontWeight: conv.unread_count > 0 ? 600 : 400 }}
                      >
                        {conv.last_message || '—'}
                      </Text>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </div>
      )}

      {/* ── Chat view ── */}
      {activeConversation && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
          {/* Messages area */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
            {loadingMsgs ? (
              <div style={{ textAlign: 'center', paddingTop: 40 }}>
                <Spin />
              </div>
            ) : messages.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="No messages yet"
                style={{ paddingTop: 40 }}
              />
            ) : (
              messages.map((msg) => {
                const isOutbound = msg.direction === 'outbound';
                return (
                  <div
                    key={msg.id}
                    style={{
                      display: 'flex',
                      justifyContent: isOutbound ? 'flex-end' : 'flex-start',
                      marginBottom: 12,
                    }}
                  >
                    <div
                      style={{
                        maxWidth: '75%',
                        padding: '8px 12px',
                        borderRadius: isOutbound ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                        backgroundColor: isOutbound ? '#dcf8c6' : '#fff',
                        border: '1px solid',
                        borderColor: isOutbound ? '#b7eb8f' : '#f0f0f0',
                        boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
                      }}
                    >
                      <Text style={{ fontSize: 13 }}>{msg.content}</Text>
                      <div style={{ fontSize: 10, color: '#999', marginTop: 4, textAlign: 'right' }}>
                        {dayjs(msg.timestamp).format('HH:mm')}
                        {msg.status && (
                          <span style={{ marginLeft: 6 }}>
                            {msg.status === 'read' ? '✓✓' : msg.status === 'delivered' ? '✓✓' : '✓'}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input area */}
          {canSend && activeConversation.lead_id ? (
            <>
              <Divider style={{ margin: 0 }} />
              <div style={{ padding: '12px 16px', backgroundColor: '#f9f9f9' }}>
                <Space.Compact style={{ width: '100%' }}>
                  <TextArea
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Type a message… (Enter to send)"
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    style={{ borderRadius: '20px 0 0 20px' }}
                  />
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleSend}
                    loading={sendMutation.isPending}
                    style={{
                      backgroundColor: '#25D366',
                      borderColor: '#25D366',
                      borderRadius: '0 20px 20px 0',
                    }}
                  />
                </Space.Compact>
                <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
                  Sending via Meta WhatsApp Cloud API
                </Text>
              </div>
            </>
          ) : (
            !canSend && (
              <div style={{ padding: 12, textAlign: 'center' }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  You do not have permission to send messages.
                </Text>
              </div>
            )
          )}
        </div>
      )}
    </Drawer>
  );
};

export default WhatsAppInbox;
