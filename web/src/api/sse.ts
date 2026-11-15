export interface SseMessage {
  id?: string;
  event: string;
  data: string;
}

/** Incremental Server-Sent Events parser: feed chunks, get complete messages. */
export function createSseParser(onMessage: (m: SseMessage) => void) {
  let buffer = '';
  let id: string | undefined;
  let event = 'message';
  let data: string[] = [];

  function flush() {
    if (data.length > 0) onMessage({ id, event, data: data.join('\n') });
    event = 'message';
    data = [];
  }

  function line(l: string) {
    if (l === '') return flush();
    if (l.startsWith(':')) return; // comment / keep-alive
    const i = l.indexOf(':');
    const field = i === -1 ? l : l.slice(0, i);
    let value = i === -1 ? '' : l.slice(i + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') event = value;
    else if (field === 'data') data.push(value);
    else if (field === 'id') id = value;
  }

  return {
    push(chunk: string) {
      buffer += chunk;
      let nl: number;
      while ((nl = buffer.search(/\r\n|\n|\r/)) !== -1) {
        const len = buffer[nl] === '\r' && buffer[nl + 1] === '\n' ? 2 : 1;
        // a lone trailing "\r" may be half of "\r\n": wait for more input
        if (buffer[nl] === '\r' && nl === buffer.length - 1) break;
        line(buffer.slice(0, nl));
        buffer = buffer.slice(nl + len);
      }
    },
  };
}
