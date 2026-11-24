// Helpers for the email composer. Lead data comes from outside forms, so anything that is put into
// the page as HTML goes through the allowlist below first.

const ALLOWED = new Set(['P', 'BR', 'DIV', 'B', 'STRONG', 'I', 'EM', 'U', 'UL', 'OL', 'LI', 'A']);
const DROP_WITH_CONTENT = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'SVG', 'MATH', 'HEAD', 'TITLE']);
const SAFE_HREF = /^(https?:\/\/|mailto:)/i;

export const escapeHtml = (s) =>
  String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/** Keep only simple formatting; drop scripts, styles, event handlers, unknown tags and unsafe links. */
export function sanitizeEmailHtml(html) {
  if (!html) return '';
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html');
  const walk = (node) => {
    let out = '';
    node.childNodes.forEach((child) => {
      if (child.nodeType === 3) {
        out += escapeHtml(child.nodeValue);
      } else if (child.nodeType === 1) {
        const tag = child.tagName;
        if (DROP_WITH_CONTENT.has(tag)) return;
        const inner = walk(child);
        if (!ALLOWED.has(tag)) { out += inner; return; }          // unwrap unknown tags, keep their text
        if (tag === 'BR') { out += '<br>'; return; }
        if (tag === 'A') {
          const href = (child.getAttribute('href') || '').trim();
          out += SAFE_HREF.test(href)
            ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${inner}</a>` : inner;
          return;
        }
        const t = tag.toLowerCase();
        out += `<${t}>${inner}</${t}>`;
      }
    });
    return out;
  };
  return walk(doc.body);
}

/** Plain text version of the (sanitised) html, with list bullets and paragraph breaks. */
export function htmlToText(html) {
  const doc = new DOMParser().parseFromString(`<body>${sanitizeEmailHtml(html)}</body>`, 'text/html');
  const walk = (node) => {
    let out = '';
    node.childNodes.forEach((c) => {
      if (c.nodeType === 3) out += c.nodeValue;
      else if (c.nodeType === 1) {
        const t = c.tagName;
        if (t === 'BR') out += '\n';
        else if (t === 'LI') out += `\n- ${walk(c)}`;
        else if (t === 'P' || t === 'DIV' || t === 'UL' || t === 'OL') out += `\n${walk(c)}\n`;
        else out += walk(c);
      }
    });
    return out;
  };
  return walk(doc.body).replace(/\n{3,}/g, '\n\n').trim();
}

/** A plain-text template as editor html (paragraphs). */
export function textToHtml(text) {
  return String(text || '').split(/\n{2,}/).map((p) => `<p>${escapeHtml(p).replace(/\n/g, '<br>')}</p>`).join('');
}

/** Same placeholders the server fills: {name} {course} {counselor} {phone} {email}. Values are escaped for html. */
export function fillVariables(text, lead, counselor, { html = false } = {}) {
  const values = {
    name: lead?.full_name || 'there',
    course: lead?.course_interested || 'our programmes',
    counselor: counselor || 'your counselor',
    phone: lead?.phone || '',
    email: lead?.email || '',
  };
  return String(text || '').replace(/\{(name|course|counselor|phone|email)\}/g, (_, k) => (html ? escapeHtml(values[k]) : String(values[k])));
}
