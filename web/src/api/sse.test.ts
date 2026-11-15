import { createSseParser, type SseMessage } from './sse';

function parse(chunks: string[]): SseMessage[] {
  const out: SseMessage[] = [];
  const p = createSseParser((m) => out.push(m));
  chunks.forEach((c) => p.push(c));
  return out;
}

describe('createSseParser', () => {
  it('parses id, event and data', () => {
    expect(parse(['id: 7\nevent: log\ndata: {"a":1}\n\n'])).toEqual([
      { id: '7', event: 'log', data: '{"a":1}' },
    ]);
  });
  it('handles messages split across chunks, even mid-line', () => {
    expect(parse(['id: 1\nev', 'ent: step\nda', 'ta: x\n', '\nid: 2\ndata: y\n\n'])).toEqual([
      { id: '1', event: 'step', data: 'x' },
      { id: '2', event: 'message', data: 'y' },
    ]);
  });
  it('joins multi-line data, ignores comments, accepts CRLF', () => {
    expect(parse([': keep-alive\r\ndata: a\r\ndata: b\r\n\r\n'])).toEqual([
      { id: undefined, event: 'message', data: 'a\nb' },
    ]);
  });
  it('a CRLF split between chunks does not produce a phantom line', () => {
    expect(parse(['data: a\r', '\n\r', '\n'])).toEqual([
      { id: undefined, event: 'message', data: 'a' },
    ]);
  });
  it('does not emit a message without data', () => {
    expect(parse(['event: ping\n\n'])).toEqual([]);
  });
});
