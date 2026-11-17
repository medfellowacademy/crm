import React from 'react';
import { Image } from 'antd';

// Images live inside a note's text as markdown: ![image](https://.../crm-documents/notes/...).
// Only links into our own notes folder are drawn as pictures; anything else a person types stays text.
const IMG_RE = /!\[[^\]]*\]\((https?:\/\/[^)\s]+)\)/g;
const OURS = '/storage/v1/object/public/crm-documents/notes/';

export const splitNote = (content) => {
  const text = String(content || '');
  const images = [];
  const stripped = text.replace(IMG_RE, (whole, url) => {
    if (url.includes(OURS)) { images.push(url); return ''; }
    return whole;
  });
  return { text: stripped.replace(/\n{3,}/g, '\n\n').trim(), images };
};

export const imageMarkdown = (url) => `![image](${url})`;

export default function NoteContent({ content, textStyle }) {
  const { text, images } = splitNote(content);
  return (
    <>
      {text && <div style={{ whiteSpace: 'pre-wrap', ...textStyle }}>{text}</div>}
      {images.length > 0 && (
        <Image.PreviewGroup>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: text ? 8 : 0 }}>
            {images.map((u) => (
              <Image key={u} src={u} width={96} height={96} style={{ objectFit: 'cover', borderRadius: 6, border: '1px solid #e5e7eb' }} />
            ))}
          </div>
        </Image.PreviewGroup>
      )}
    </>
  );
}
