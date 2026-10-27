import React, { useEffect, useState } from 'react';
import { targetsAPI } from '../../api/api';
import { LEMON, LAVENDER, CHARCOAL, DISPLAY_FONT } from './salesTheme';

const initials = (name) => String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase();

// A round photo, or brand-coloured initials when there is no photo (or it fails to load).
export function SalesAvatar({ name, src, size = 48, ring = LEMON, ringWidth = 3, glow = false, style }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => { setFailed(false); }, [src]);
  const box = {
    width: size, height: size, borderRadius: '50%', flex: '0 0 auto', overflow: 'hidden',
    border: `${ringWidth}px solid ${ring}`, boxSizing: 'border-box', background: CHARCOAL,
    boxShadow: glow ? `0 0 ${size * 0.45}px ${ring}66` : undefined, ...style,
  };
  if (src && !failed) {
    return <img src={src} alt={name} onError={() => setFailed(true)} style={{ ...box, objectFit: 'cover', display: 'block' }} />;
  }
  return (
    <div style={{ ...box, display: 'grid', placeItems: 'center', background: `linear-gradient(135deg, ${LAVENDER}, ${LEMON})`, color: CHARCOAL, fontFamily: DISPLAY_FONT, fontSize: size * 0.38 }}>
      {initials(name)}
    </div>
  );
}

// Same avatar for the logged-in pages: <img> can't send the JWT, so fetch the photo as a blob.
export function AuthAvatar({ userId, version, ...props }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    if (!userId || !version) { setSrc(null); return undefined; }
    let url;
    let alive = true;
    targetsAPI.avatar(userId).then((r) => {
      if (!alive) return;
      url = URL.createObjectURL(r.data);
      setSrc(url);
    }).catch(() => { if (alive) setSrc(null); });
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [userId, version]);
  return <SalesAvatar src={src} {...props} />;
}
