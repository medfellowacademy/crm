import { sanitizeEmailHtml, htmlToText, textToHtml, fillVariables, escapeHtml } from './emailHtml';

describe('sanitizeEmailHtml', () => {
  it('keeps simple formatting and safe links', () => {
    const out = sanitizeEmailHtml('<p>Hi <b>Dr</b> <a href="https://ok.in/x?a=1&b=2">link</a></p><ul><li>One</li></ul>');
    expect(out).toContain('<b>Dr</b>');
    expect(out).toContain('<li>One</li>');
    expect(out).toContain('href="https://ok.in/x?a=1&amp;b=2"');
  });

  it('removes scripts, handlers, javascript links, images and styles', () => {
    const out = sanitizeEmailHtml(
      '<p onclick="x()">A<script>alert(1)</script><a href="javascript:alert(1)">bad</a><img src=x onerror=y><style>p{}</style><iframe src="//e"></iframe></p>',
    );
    ['script', 'onclick', 'javascript:', '<img', 'onerror', '<style', 'iframe', 'alert'].forEach((bad) => expect(out).not.toContain(bad));
    expect(out).toContain('bad');          // the link text survives, the link does not
  });

  it('escapes text that only looks like markup', () => {
    expect(sanitizeEmailHtml('1 < 2 &amp; 3')).toBe('1 &lt; 2 &amp; 3');
  });
});

describe('text helpers', () => {
  it('converts html to readable text', () => {
    expect(htmlToText('<p>Hi</p><ul><li>One</li><li>Two</li></ul>')).toBe('Hi\n\n- One\n- Two');
  });

  it('turns template text into paragraphs', () => {
    expect(textToHtml('Line one\nstill one\n\nSecond')).toBe('<p>Line one<br>still one</p><p>Second</p>');
  });

  it('fills the same variables as the server and escapes lead data for html', () => {
    const lead = { full_name: '<img src=x onerror=1>', course_interested: 'MD' };
    expect(fillVariables('Hi {name}, {course} from {counselor}. {other}', { full_name: 'Priya', course_interested: 'MD' }, 'Asha'))
      .toBe('Hi Priya, MD from Asha. {other}');
    expect(fillVariables('{name}', lead, 'Asha', { html: true })).toBe('&lt;img src=x onerror=1&gt;');
    expect(fillVariables('{name}', {}, '')).toBe('there');
    expect(escapeHtml('"a" & <b>')).toBe('&quot;a&quot; &amp; &lt;b&gt;');
  });
});
