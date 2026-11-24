import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button, Upload, Popover, Input, List, Tag, Space, Typography, Tooltip, Empty, message } from 'antd';
import { PaperClipOutlined, FilePdfOutlined, FileTextOutlined, FileImageOutlined, FileExcelOutlined, FileWordOutlined, FilePptOutlined, BookOutlined, LinkOutlined } from '@ant-design/icons';
import { emailAPI, brochuresAPI } from '../../api/api';

const { Text } = Typography;

// Same limits the server enforces (it checks again from the file's real bytes).
export const MAX_FILE = 10 * 1024 * 1024;
export const MAX_TOTAL = 20 * 1024 * 1024;
export const MAX_COUNT = 5;
export const ACCEPT = '.png,.jpg,.jpeg,.gif,.webp,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx';
const ALLOWED = new Set(ACCEPT.replace(/\./g, '').split(','));

export const prettySize = (n) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

const iconFor = (name) => {
  const ext = String(name).split('.').pop().toLowerCase();
  if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) return <FileImageOutlined />;
  if (ext === 'pdf') return <FilePdfOutlined />;
  if (['doc', 'docx'].includes(ext)) return <FileWordOutlined />;
  if (['xls', 'xlsx'].includes(ext)) return <FileExcelOutlined />;
  if (['ppt', 'pptx'].includes(ext)) return <FilePptOutlined />;
  return <FileTextOutlined />;
};

/**
 * Attach files (images, PDF, Word, Excel, PowerPoint) or a PDF from the Brochures library.
 * `value` is [{id, source: 'upload'|'brochure', name, size}]. A brochure too big to email is added as a link instead.
 */
export default function AttachmentPicker({ value, onChange, onInsertLink, disabled }) {
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const total = value.reduce((n, a) => n + (a.size || 0), 0);

  const brochures = useQuery({
    queryKey: ['brochures', search],
    queryFn: () => brochuresAPI.getAll(search.trim() || undefined).then((r) => (Array.isArray(r.data) ? r.data : [])),
    enabled: open,
    staleTime: 60 * 1000,
  });

  const room = (size) => {
    if (value.length >= MAX_COUNT) { message.warning(`You can attach up to ${MAX_COUNT} files.`); return false; }
    if (size > MAX_FILE) { message.warning(`Each file must be ${MAX_FILE / 1024 / 1024} MB or smaller.`); return false; }
    if (total + size > MAX_TOTAL) { message.warning(`Attachments can total up to ${MAX_TOTAL / 1024 / 1024} MB.`); return false; }
    return true;
  };

  const upload = async (file) => {
    const ext = file.name.split('.').pop().toLowerCase();
    if (!ALLOWED.has(ext)) { message.warning('You can attach images, PDF, Word, Excel or PowerPoint files.'); return; }
    if (!room(file.size)) return;
    setBusy(true);
    try {
      const { data } = await emailAPI.uploadAttachment(file);
      onChange([...value, { id: data.id, source: 'upload', name: data.name, size: data.size }]);
    } catch (e) {
      message.error(e?.response?.data?.detail || 'The file could not be uploaded');
    } finally {
      setBusy(false);
    }
  };

  const addBrochure = (b) => {
    setOpen(false);
    if (value.some((a) => a.source === 'brochure' && String(a.id) === String(b.id))) return;
    if ((b.file_size || 0) > MAX_FILE) {
      message.info(`${b.name} is ${prettySize(b.file_size)}, too big to attach. A link was added to your message instead.`);
      onInsertLink && onInsertLink({ name: b.name, url: b.file_url });
      return;
    }
    if (!room(b.file_size || 0)) return;
    onChange([...value, { id: String(b.id), source: 'brochure', name: `${b.name}.pdf`, size: b.file_size || 0 }]);
  };

  const remove = (a) => {
    onChange(value.filter((x) => !(x.id === a.id && x.source === a.source)));
    if (a.source === 'upload') emailAPI.removeAttachment(a.id).catch(() => {});      // the stored copy is not needed any more
  };

  const picker = (
    <div style={{ width: 340 }}>
      <Input.Search size="small" allowClear placeholder="Search brochures" onSearch={setSearch} style={{ marginBottom: 8 }} />
      <List size="small" loading={brochures.isLoading} style={{ maxHeight: 260, overflow: 'auto' }} dataSource={brochures.data || []}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No brochures yet" /> }}
        renderItem={(b) => (
          <List.Item style={{ cursor: 'pointer' }} onClick={() => addBrochure(b)}>
            <Space><FilePdfOutlined /><span>{b.name}</span></Space>
            <Space size={4}>
              <Text type="secondary" style={{ fontSize: 12 }}>{prettySize(b.file_size || 0)}</Text>
              {(b.file_size || 0) > MAX_FILE && <Tooltip title="Too big to attach: added as a link"><LinkOutlined /></Tooltip>}
            </Space>
          </List.Item>)} />
    </div>
  );

  return (
    <div>
      <Space wrap size={8}>
        <Upload accept={ACCEPT} multiple showUploadList={false} disabled={disabled || busy}
          beforeUpload={(file) => { upload(file); return false; }}>
          <Button size="small" icon={<PaperClipOutlined />} loading={busy} disabled={disabled}>Attach file</Button>
        </Upload>
        <Popover trigger="click" placement="bottomLeft" open={open} onOpenChange={setOpen} content={picker} title="Brochures library">
          <Button size="small" icon={<BookOutlined />} disabled={disabled}>Brochure</Button>
        </Popover>
        {value.map((a) => (
          <Tag key={`${a.source}:${a.id}`} closable onClose={(e) => { e.preventDefault(); remove(a); }} style={{ margin: 0, padding: '2px 8px', maxWidth: 260 }}>
            <span style={{ marginRight: 4 }}>{iconFor(a.name)}</span>
            <span style={{ display: 'inline-block', maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', verticalAlign: 'bottom', whiteSpace: 'nowrap' }}>{a.name}</span>
            <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>{prettySize(a.size || 0)}</Text>
          </Tag>
        ))}
      </Space>
      {value.length > 0 && (
        <Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 4 }}>
          {value.length} of {MAX_COUNT} files · {prettySize(total)} of {MAX_TOTAL / 1024 / 1024} MB
        </Text>
      )}
    </div>
  );
}
