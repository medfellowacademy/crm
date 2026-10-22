import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, Switch, Typography, Spin, Alert, Space, Tooltip, message } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { restrictionsAPI } from '../../api/api';

const { Text } = Typography;

const SWITCHES = [
  { key: 'hide_unassigned_leads', title: 'Hide unassigned leads', help: 'Never sees, searches or opens a lead that has no owner.' },
  { key: 'hide_team_attendance', title: 'Hide team attendance', help: 'No access to other people\'s attendance (for non-admins: no attendance history or reports at all).' },
  { key: 'hide_payroll', title: 'Hide salary slips & advances', help: 'No access to other people\'s salary slips, advances or leave balances (for non-admins: none at all, not even their own).' },
];

// Per-user access switches. Only a Super Admin gets here (the Users page is
// Super Admin only), and the server enforces who may flip each one: a switch
// can only be lifted by the Super Admin who set it, and you can't restrict yourself.
export default function RestrictionsPanel({ user, onChanged }) {
  const queryClient = useQueryClient();
  const key = ['user-restrictions', user.id];

  const { data, isLoading, isError } = useQuery({
    queryKey: key,
    queryFn: () => restrictionsAPI.get(user.id).then((r) => r.data),
  });

  const save = useMutation({
    mutationFn: (patch) => restrictionsAPI.set(user.id, patch).then((r) => r.data),
    onSuccess: (fresh) => {
      queryClient.setQueryData(key, fresh);
      queryClient.invalidateQueries({ queryKey: ['users'] });
      onChanged?.();
      message.success('Restriction updated');
    },
    onError: (e) => message.error(e?.response?.data?.detail || 'Could not update the restriction'),
  });

  return (
    <Card
      size="small" style={{ marginTop: 24 }}
      title={<Space><LockOutlined />Access restrictions</Space>}
    >
      {isLoading && <Spin size="small" />}
      {isError && <Alert type="warning" showIcon message="Couldn't load this user's restrictions" />}
      {data?.is_self && <Alert type="info" showIcon style={{ marginBottom: 12 }} message="You can't restrict yourself." />}
      {data && SWITCHES.map((s) => {
        const f = data.flags[s.key];
        const lockedByOther = f.active && !f.can_change;
        const control = (
          <Switch
            checked={f.active}
            disabled={!f.can_change || save.isPending}
            onChange={(v) => save.mutate({ [s.key]: v })}
          />
        );
        return (
          <div key={s.key} style={{ display: 'flex', gap: 12, justifyContent: 'space-between', alignItems: 'flex-start', padding: '10px 0', borderTop: '1px solid #f0f0f0' }}>
            <div>
              <Text strong>{s.title}</Text>
              <div><Text type="secondary" style={{ fontSize: 12 }}>{s.help}</Text></div>
              {f.active && (
                <div style={{ marginTop: 2 }}>
                  <Text type="danger" style={{ fontSize: 12 }}>
                    Restricted by {f.set_by || 'an administrator'}{f.set_at ? ` on ${dayjs(f.set_at).format('DD MMM YYYY')}` : ''}
                  </Text>
                </div>
              )}
            </div>
            {lockedByOther
              ? <Tooltip title={`Only ${f.set_by || 'the administrator who set it'} can lift this`}>{control}</Tooltip>
              : control}
          </div>
        );
      })}
    </Card>
  );
}
