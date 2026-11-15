/**
 * The view side of MCP Apps: JSON-RPC 2.0 over postMessage with the host that embeds the view in an iframe.
 * Written against what plume-6f's docs/mcp-apps.md records of the spec (2026-01-26):
 *
 *   view -> host   request       ui/initialize {protocolVersion, appInfo, appCapabilities}
 *   host -> view   result        {protocolVersion, hostCapabilities, hostInfo, hostContext}
 *   view -> host   notification  ui/notifications/initialized          (only then does the host send data)
 *   host -> view   notification  ui/notifications/tool-input | tool-result | host-context-changed
 *   view -> host   notification  ui/notifications/size-changed {width?, height?}
 *   view -> host   request       ui/open-link {url}                    (only with the host capability openLinks)
 *
 * Nothing here touches the network and nothing is stored: the iframe is sandboxed without same-origin.
 */
export const PROTOCOL_VERSION = '2026-01-26';

export interface HostContext {
  theme?: 'light' | 'dark';
  /** CSS variables of the host, such as --color-background-primary (any subset). */
  styles?: { variables?: Record<string, string> };
  displayMode?: string;
  locale?: string;
  [key: string]: unknown;
}

export interface HostInit {
  hostContext: HostContext;
  hostCapabilities: { openLinks?: unknown; serverTools?: unknown; [key: string]: unknown };
}

export interface CallToolResult {
  content?: { type: string; text?: string }[];
  structuredContent?: unknown;
  isError?: boolean;
}

type Json = unknown;
interface Message {
  jsonrpc: '2.0';
  id?: number | string;
  method?: string;
  params?: Json;
  result?: Json;
  error?: { code: number; message: string };
}

/** What the connection needs from the page, so it can be tested without a window. */
export interface Transport {
  /** The host: window.parent. */
  send(message: Message): void;
  /** Calls `handler` for each message that came from the host (and from nobody else). */
  listen(handler: (data: unknown) => void): () => void;
}

export function windowTransport(win: Window = window): Transport {
  return {
    send: (message) => win.parent.postMessage(message, '*'),
    listen: (handler) => {
      const on = (e: MessageEvent) => {
        // only the embedding host: other frames and windows are not trusted
        if (e.source === win.parent) handler(e.data);
      };
      win.addEventListener('message', on);
      return () => win.removeEventListener('message', on);
    },
  };
}

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null;

export class HostConnection {
  private nextId = 1;
  private pending = new Map<
    number | string,
    { resolve: (v: Json) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }
  >();
  private handlers = new Map<string, (params: Json) => void>();
  private stop: () => void;
  hostContext: HostContext = {};
  hostCapabilities: HostInit['hostCapabilities'] = {};

  constructor(
    private transport: Transport,
    private timeoutMs = 10_000,
  ) {
    this.stop = transport.listen((data) => this.receive(data));
  }

  /** Registers the handler of a host notification (the last registration of a method wins). */
  on(method: string, handler: (params: Json) => void) {
    this.handlers.set(method, handler);
  }

  notify(method: string, params?: Json) {
    this.transport.send({ jsonrpc: '2.0', method, ...(params === undefined ? {} : { params }) });
  }

  request(method: string, params?: Json): Promise<Json> {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`The host did not answer ${method}`));
      }, this.timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      this.transport.send({
        jsonrpc: '2.0',
        id,
        method,
        ...(params === undefined ? {} : { params }),
      });
    });
  }

  /** The handshake: ui/initialize, then ui/notifications/initialized. Resolves with the host's context. */
  async initialize(appInfo: { name: string; version: string }): Promise<HostInit> {
    const result = await this.request('ui/initialize', {
      protocolVersion: PROTOCOL_VERSION,
      appInfo,
      appCapabilities: {},
    });
    const r = isObject(result) ? result : {};
    this.hostContext = isObject(r.hostContext) ? (r.hostContext as HostContext) : {};
    this.hostCapabilities = isObject(r.hostCapabilities)
      ? (r.hostCapabilities as HostInit['hostCapabilities'])
      : {};
    this.notify('ui/notifications/initialized');
    return { hostContext: this.hostContext, hostCapabilities: this.hostCapabilities };
  }

  /** The host's context changes arrive as partial objects: merge them. */
  mergeContext(partial: unknown): HostContext {
    if (isObject(partial)) {
      const styles = isObject(partial.styles)
        ? (partial.styles as HostContext['styles'])
        : undefined;
      this.hostContext = {
        ...this.hostContext,
        ...(partial as HostContext),
        ...(styles
          ? {
              styles: {
                ...this.hostContext.styles,
                ...styles,
                variables: { ...this.hostContext.styles?.variables, ...styles?.variables },
              },
            }
          : {}),
      };
    }
    return this.hostContext;
  }

  sizeChanged(size: { width?: number; height?: number }) {
    this.notify('ui/notifications/size-changed', size);
  }

  /** Asks the host to open a link (it decides how). Only when it offers the capability. */
  async openLink(url: string): Promise<boolean> {
    if (!this.hostCapabilities.openLinks) return false;
    try {
      await this.request('ui/open-link', { url });
      return true;
    } catch {
      return false;
    }
  }

  dispose() {
    this.stop();
    for (const p of this.pending.values()) clearTimeout(p.timer);
    this.pending.clear();
  }

  private receive(data: unknown) {
    if (!isObject(data) || data.jsonrpc !== '2.0') return;
    const m = data as unknown as Message;
    if (m.method !== undefined) {
      if (m.id !== undefined) this.answerRequest(m);
      else this.handlers.get(m.method)?.(m.params);
      return;
    }
    if (m.id !== undefined) {
      const p = this.pending.get(m.id);
      if (!p) return;
      this.pending.delete(m.id);
      clearTimeout(p.timer);
      if (m.error) p.reject(new Error(m.error.message));
      else p.resolve(m.result);
    }
  }

  /** Requests from the host: ping and teardown are answered, anything else is "method not found". */
  private answerRequest(m: Message) {
    const id = m.id as number | string;
    if (m.method === 'ping' || m.method === 'ui/resource-teardown') {
      this.transport.send({ jsonrpc: '2.0', id, result: {} });
    } else {
      this.transport.send({
        jsonrpc: '2.0',
        id,
        error: { code: -32601, message: `Method not found: ${m.method}` },
      });
    }
  }
}
