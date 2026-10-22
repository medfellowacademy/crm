// Draws a vacancy board as a shareable poster (PNG) and wraps it into a one-page
// PDF. Pure canvas — no extra libraries — so it works on exactly what is on screen,
// including edits that have not been saved yet.

const NAVY = '#0b3d91';
const GREEN = '#16a34a';
const YELLOW = '#facc15';
const AMBER = '#ca8a04';
const FONT = "Inter, 'Segoe UI', Arial, sans-serif";

const W = 1600;
const COLS = 10;
const M = 60; // side margin shared by logo, banner, capacity bar, seat panel and footer

function path(ctx, x, y, w, h, [tl, tr, br, bl]) {
  ctx.beginPath();
  ctx.moveTo(x + tl, y);
  ctx.lineTo(x + w - tr, y);
  ctx.arcTo(x + w, y, x + w, y + tr, tr);
  ctx.lineTo(x + w, y + h - br);
  ctx.arcTo(x + w, y + h, x + w - br, y + h, br);
  ctx.lineTo(x + bl, y + h);
  ctx.arcTo(x, y + h, x, y + h - bl, bl);
  ctx.lineTo(x, y + tl);
  ctx.arcTo(x, y, x + tl, y, tl);
  ctx.closePath();
}

const round = (ctx, x, y, w, h, r) => path(ctx, x, y, w, h, [r, r, r, r]);

function shadow(ctx, blur = 14, y = 4, color = 'rgba(15,23,42,0.14)') {
  ctx.shadowColor = color; ctx.shadowBlur = blur; ctx.shadowOffsetY = y;
}
const noShadow = (ctx) => { ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0; };

function wrap(ctx, text, maxWidth) {
  const words = String(text || '').split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (ctx.measureText(test).width > maxWidth && line) { lines.push(line); line = w; } else line = test;
  }
  if (line) lines.push(line);
  return lines.slice(0, 4);
}

function loadImage(src) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null); // a missing logo must not stop the export
    img.src = src;
  });
}

const slug = (s) => String(s || 'vacancy-board').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'vacancy-board';
const today = () => new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

export async function renderBoardCanvas(board, logoSrc = '/medfellow-logo.png') {
  const total = Number(board.total_seats) || 0;
  const seats = new Set(board.enrolled_seats || []);
  const enrolled = Number(board.enrolled) || 0;
  const available = Number(board.available) || 0;
  const percent = Number(board.percent) || 0;

  // header row (course + doctor name beside the two boxes): measured first because
  // a long name makes it taller than the boxes and everything below must move down
  const textMax = 640, boxW = 250, boxGap = 26, groupGap = 48, boxTop = 262, boxH = 164;
  const probe = document.createElement('canvas').getContext('2d');
  probe.font = `800 40px ${FONT}`;
  const courseLines = wrap(probe, board.course_name, textMax);
  const courseW = Math.max(0, ...courseLines.map((l) => probe.measureText(l).width));
  probe.font = `600 27px ${FONT}`;
  const doctorLines = board.doctor_name ? wrap(probe, board.doctor_name, textMax) : [];
  const doctorW = Math.max(0, ...doctorLines.map((l) => probe.measureText(l).width));
  const textW = Math.max(courseW, doctorW);
  const blockH = courseLines.length * 48 + (doctorLines.length ? 14 + doctorLines.length * 34 : 0);
  const rowH = Math.max(boxH, blockH + 12);
  const dy = rowH - boxH; // how much taller the header row is than the boxes

  const rows = Math.max(1, Math.ceil(total / COLS));
  const gap = 14;
  const panelX = M, panelW = W - 2 * M, pad = 28;
  const seatW = (panelW - pad * 2 - gap * (COLS - 1)) / COLS;
  const seatH = 84;
  const panelTop = 590 + dy;
  const panelH = pad * 2 + rows * seatH + (rows - 1) * gap;
  const H = panelTop + panelH + 84;

  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');
  ctx.textBaseline = 'alphabetic';

  // background
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, '#eaf2ff'); bg.addColorStop(0.35, '#ffffff'); bg.addColorStop(1, '#f4f8ff');
  ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);

  // logo
  const logo = await loadImage(logoSrc);
  const lh = 112;
  const lw = logo ? lh * (logo.naturalWidth / logo.naturalHeight) : 340;
  if (logo) ctx.drawImage(logo, M, 38, lw, lh);

  // banner (fills the rest of the row, ends exactly on the right margin)
  const bx = M + lw + 36, by = 42, bw = W - M - bx, bh = 124;
  const bannerFill = ctx.createLinearGradient(bx, by, bx + bw, by + bh);
  bannerFill.addColorStop(0, NAVY); bannerFill.addColorStop(1, '#1d5fc4');
  shadow(ctx, 18, 6, 'rgba(11,61,145,0.28)');
  ctx.fillStyle = bannerFill; path(ctx, bx, by, bw, bh, [22, 22, 22, 56]); ctx.fill();
  noShadow(ctx);
  ctx.textAlign = 'center';
  ctx.fillStyle = '#fff'; ctx.font = `800 48px ${FONT}`; ctx.fillText('ENROLLMENT', bx + bw / 2, by + 54);
  ctx.fillStyle = YELLOW; ctx.font = `800 48px ${FONT}`; ctx.fillText('VACANCY LIST', bx + bw / 2, by + 106);

  // tagline
  ctx.fillStyle = NAVY; ctx.font = `600 25px ${FONT}`;
  ctx.fillText('Limited Seats    |    High Demand    |    Be a Part of MedFellow', W / 2, 220);

  // course + doctor, then the two boxes, centred horizontally as ONE group so the
  // spacing on the left and right is equal whatever the course name length
  ctx.textAlign = 'right';
  const boxesW = boxW * 2 + boxGap;
  const groupX = (W - (textW + groupGap + boxesW)) / 2;
  const textRight = groupX + textW;
  const boxesX = textRight + groupGap;
  const boxY = boxTop + dy / 2;               // boxes sit in the middle of the row

  let ty = boxTop + rowH / 2 - blockH / 2 + 36;
  ctx.fillStyle = NAVY; ctx.font = `800 40px ${FONT}`;
  courseLines.forEach((l) => { ctx.fillText(l, textRight, ty); ty += 48; });
  ty += doctorLines.length ? 2 : 0;
  ctx.fillStyle = '#475569'; ctx.font = `600 27px ${FONT}`;
  doctorLines.forEach((l) => { ctx.fillText(l, textRight, ty + 12); ty += 34; });

  // stat boxes
  const stat = (x, num, label, colour, numColour) => {
    shadow(ctx, 16, 5, 'rgba(15,23,42,0.10)');
    ctx.fillStyle = '#fff'; round(ctx, x, boxY, boxW, boxH, 22); ctx.fill();
    noShadow(ctx);
    ctx.lineWidth = 4; ctx.strokeStyle = colour; round(ctx, x, boxY, boxW, boxH, 22); ctx.stroke();
    ctx.textAlign = 'center';
    ctx.fillStyle = numColour; ctx.font = `800 88px ${FONT}`; ctx.fillText(String(num), x + boxW / 2, boxY + 96);
    ctx.font = `800 30px ${FONT}`; ctx.fillText(label, x + boxW / 2, boxY + 142);
  };
  stat(boxesX, enrolled, 'ENROLLED', GREEN, GREEN);
  stat(boxesX + boxW + boxGap, available, 'AVAILABLE', '#eab308', AMBER);

  // capacity
  ctx.textAlign = 'left'; ctx.fillStyle = NAVY; ctx.font = `700 27px ${FONT}`;
  ctx.fillText('Capacity filled', M, 478 + dy);
  ctx.textAlign = 'right'; ctx.fillText(`${percent}%`, W - M, 478 + dy);
  ctx.fillStyle = '#e5e7eb'; round(ctx, M, 494 + dy, W - 2 * M, 16, 8); ctx.fill();
  if (percent > 0) {
    const fill = ctx.createLinearGradient(M, 0, W - M, 0);
    fill.addColorStop(0, '#22c55e'); fill.addColorStop(1, GREEN);
    ctx.fillStyle = fill; round(ctx, M, 494 + dy, Math.max(16, (W - 2 * M) * Math.min(1, percent / 100)), 16, 8); ctx.fill();
  }
  // legend
  ctx.textAlign = 'left'; ctx.font = `600 24px ${FONT}`;
  ctx.fillStyle = YELLOW; round(ctx, M, 535 + dy, 24, 24, 6); ctx.fill();
  ctx.fillStyle = NAVY; ctx.fillText('Available', M + 34, 555 + dy);
  ctx.fillStyle = GREEN; round(ctx, M + 210, 535 + dy, 24, 24, 6); ctx.fill();
  ctx.fillStyle = NAVY; ctx.fillText('Enrolled', M + 244, 555 + dy);

  // seats panel
  shadow(ctx, 22, 8, 'rgba(15,23,42,0.10)');
  ctx.fillStyle = '#fff'; round(ctx, panelX, panelTop, panelW, panelH, 24); ctx.fill();
  noShadow(ctx);
  ctx.textAlign = 'center';
  for (let n = 1; n <= total; n += 1) {
    const r = Math.floor((n - 1) / COLS), c = (n - 1) % COLS;
    const x = panelX + pad + c * (seatW + gap);
    const y = panelTop + pad + r * (seatH + gap);
    const on = seats.has(n);
    const g = ctx.createLinearGradient(0, y, 0, y + seatH);
    if (on) { g.addColorStop(0, '#22c55e'); g.addColorStop(1, GREEN); } else { g.addColorStop(0, '#fde047'); g.addColorStop(1, YELLOW); }
    shadow(ctx, 8, 3, 'rgba(0,0,0,0.16)');
    ctx.fillStyle = g; round(ctx, x, y, seatW, seatH, 16); ctx.fill();
    noShadow(ctx);
    ctx.fillStyle = on ? '#fff' : '#713f12';
    ctx.font = `700 ${n >= 100 ? 30 : 36}px ${FONT}`;
    ctx.fillText(String(n), x + seatW / 2, y + seatH / 2 + 12);
  }

  // footer
  ctx.textAlign = 'right'; ctx.fillStyle = '#94a3b8'; ctx.font = `500 22px ${FONT}`;
  ctx.fillText(`As on ${today()}`, W - M, H - 30);
  ctx.textAlign = 'left'; ctx.fillText('MedFellow Academy', M, H - 30);
  return canvas;
}

function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const toBlob = (canvas, type, quality) => new Promise((resolve, reject) =>
  canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Could not create the image'))), type, quality));

export async function downloadBoardPng(board) {
  const canvas = await renderBoardCanvas(board);
  download(await toBlob(canvas, 'image/png'), `${slug(board.course_name)}-vacancy-${new Date().toISOString().slice(0, 10)}.png`);
}

// One-page PDF: the poster as a JPEG inside a hand-written PDF container.
export function canvasToPdfBlob(canvas) {
  const b64 = canvas.toDataURL('image/jpeg', 0.92).split(',')[1];
  const bin = atob(b64);
  const jpeg = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) jpeg[i] = bin.charCodeAt(i);

  const imgW = canvas.width, imgH = canvas.height;
  const pageW = 842;
  const pageH = Math.round(((pageW * imgH) / imgW) * 100) / 100;
  const enc = new TextEncoder();
  const parts = [];
  const offsets = [];
  let pos = 0;
  const push = (d) => { const u = typeof d === 'string' ? enc.encode(d) : d; parts.push(u); pos += u.length; };
  const obj = (n, body) => { offsets[n] = pos; push(`${n} 0 obj\n${body}\nendobj\n`); };

  push('%PDF-1.4\n');
  obj(1, '<< /Type /Catalog /Pages 2 0 R >>');
  obj(2, '<< /Type /Pages /Kids [3 0 R] /Count 1 >>');
  obj(3, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageW} ${pageH}] /Contents 4 0 R /Resources << /XObject << /Im0 5 0 R >> >> >>`);
  const content = `q ${pageW} 0 0 ${pageH} 0 0 cm /Im0 Do Q`;
  obj(4, `<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
  offsets[5] = pos;
  push(`5 0 obj\n<< /Type /XObject /Subtype /Image /Width ${imgW} /Height ${imgH} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`);
  push(jpeg);
  push('\nendstream\nendobj\n');
  const xref = pos;
  let table = 'xref\n0 6\n0000000000 65535 f \n';
  for (let i = 1; i <= 5; i += 1) table += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`;
  push(table);
  push(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`);
  return new Blob(parts, { type: 'application/pdf' });
}

export async function downloadBoardPdf(board) {
  const canvas = await renderBoardCanvas(board);
  download(canvasToPdfBlob(canvas), `${slug(board.course_name)}-vacancy-${new Date().toISOString().slice(0, 10)}.pdf`);
}
