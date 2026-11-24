import React, { useEffect, useRef, useState } from 'react';
import { Button, Space, Tooltip, Modal, Input, Dropdown, theme } from 'antd';
import {
  BoldOutlined, ItalicOutlined, UnderlineOutlined, UnorderedListOutlined, OrderedListOutlined,
  LinkOutlined, ClearOutlined, PlusOutlined,
} from '@ant-design/icons';
import { sanitizeEmailHtml } from './emailHtml';

const VARIABLES = [
  { key: '{name}', label: 'Lead name' },
  { key: '{course}', label: 'Course' },
  { key: '{counselor}', label: 'Your name' },
];

/**
 * A small email editor (bold, italic, underline, lists, links, variables).
 * `value` is html; pasted content is always inserted as plain text so no foreign markup enters.
 */
export default function RichTextEditor({ value, onChange, minHeight = 240, placeholder = 'Write your message…' }) {
  const { token } = theme.useToken();
  const ref = useRef(null);
  const saved = useRef(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [url, setUrl] = useState('https://');

  // Only touch the DOM when the value changed from outside (a template, a restored draft): typing must not move the caret.
  useEffect(() => {
    const el = ref.current;
    if (el && el.innerHTML !== (value || '')) el.innerHTML = sanitizeEmailHtml(value || '');
  }, [value]);

  const emit = () => onChange && onChange(ref.current ? ref.current.innerHTML : '');
  const run = (cmd, arg) => {
    ref.current?.focus();
    document.execCommand(cmd, false, arg);   // deprecated but supported everywhere and fine for this small toolbar
    emit();
  };
  const keepFocus = (e) => e.preventDefault();           // toolbar clicks must not steal the text selection

  const openLink = () => {
    const sel = window.getSelection();
    saved.current = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
    setUrl('https://');
    setLinkOpen(true);
  };
  const applyLink = () => {
    setLinkOpen(false);
    const href = url.trim();
    if (!/^(https?:\/\/|mailto:)/i.test(href) || href === 'https://') return;
    ref.current?.focus();
    const sel = window.getSelection();
    if (saved.current) { sel.removeAllRanges(); sel.addRange(saved.current); }
    if (sel && sel.isCollapsed) document.execCommand('insertHTML', false, `<a href="${href.replace(/"/g, '&quot;')}">${href}</a>`);
    else document.execCommand('createLink', false, href);
    emit();
  };

  const tool = (title, icon, onClick) => (
    <Tooltip title={title}><Button type="text" size="small" icon={icon} onMouseDown={keepFocus} onClick={onClick} aria-label={title} /></Tooltip>
  );

  return (
    <div style={{ border: `1px solid ${token.colorBorder}`, borderRadius: 8, background: token.colorBgContainer, overflow: 'hidden' }}>
      <div style={{ padding: '4px 8px', borderBottom: `1px solid ${token.colorBorderSecondary}`, background: token.colorFillQuaternary }}>
        <Space size={2} wrap>
          {tool('Bold', <BoldOutlined />, () => run('bold'))}
          {tool('Italic', <ItalicOutlined />, () => run('italic'))}
          {tool('Underline', <UnderlineOutlined />, () => run('underline'))}
          {tool('Bullet list', <UnorderedListOutlined />, () => run('insertUnorderedList'))}
          {tool('Numbered list', <OrderedListOutlined />, () => run('insertOrderedList'))}
          {tool('Add link', <LinkOutlined />, openLink)}
          {tool('Clear formatting', <ClearOutlined />, () => run('removeFormat'))}
          <Dropdown trigger={['click']} menu={{
            items: VARIABLES.map((v) => ({ key: v.key, label: `${v.label}  ${v.key}` })),
            onClick: ({ key }) => run('insertText', key),
          }}>
            <Button type="text" size="small" icon={<PlusOutlined />} onMouseDown={keepFocus}>Insert</Button>
          </Dropdown>
        </Space>
      </div>
      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        data-placeholder={placeholder}
        className="email-editor"
        onInput={emit}
        onBlur={emit}
        onPaste={(e) => {
          e.preventDefault();
          document.execCommand('insertText', false, e.clipboardData.getData('text/plain'));
        }}
        style={{ minHeight, padding: '12px 14px', outline: 'none', fontSize: 14, lineHeight: 1.6, color: token.colorText, overflowWrap: 'anywhere' }}
      />
      <style>{`
        .email-editor:empty:before { content: attr(data-placeholder); color: ${token.colorTextPlaceholder}; pointer-events: none; }
        .email-editor p { margin: 0 0 10px; }
        .email-editor ul, .email-editor ol { margin: 0 0 10px 22px; padding: 0; }
        .email-editor a { color: ${token.colorLink}; }
      `}</style>
      <Modal title="Add link" open={linkOpen} onOk={applyLink} onCancel={() => setLinkOpen(false)} okText="Add link" width={420}>
        <Input value={url} onChange={(e) => setUrl(e.target.value)} onPressEnter={applyLink} placeholder="https://example.com" autoFocus />
      </Modal>
    </div>
  );
}
