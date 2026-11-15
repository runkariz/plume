import { Card, Chip, RawJson } from '@/components';
import type { McpOut } from '@/api/types';

/** The MCP server(s) the vendor runs, with their tools. Only used when the package has an MCP section. */
export function McpPanel({ mcp }: { mcp: McpOut }) {
  return (
    <Card className="pad" role="region" aria-label="MCP">
      <h2 className="h2-sm">MCP servers</h2>
      <ul className="sec-list">
        {mcp.servers.map((s) => {
          const name = typeof s.server.name === 'string' ? s.server.name : s.id;
          const url = typeof s.server.url === 'string' ? s.server.url : null;
          return (
            <li key={s.id} className="sec-item" style={{ display: 'block' }}>
              <b>{name}</b> <span className="faint small mono">{s.id}</span>
              {url ? <div className="mono small">{url}</div> : null}
              <h3 style={{ marginTop: 12 }}>
                Tools <span className="faint small">({s.tools.length})</span>
              </h3>
              <ul className="sec-list">
                {s.tools.map((t) => (
                  <li key={t.tool} className="sec-item" style={{ display: 'block' }}>
                    <Chip>{t.tool}</Chip>
                    <RawJson
                      raw={t.inputSchema}
                      title="Input schema"
                      label={`Input schema of ${t.tool}`}
                    />
                    {t.outputSchema ? (
                      <RawJson
                        raw={t.outputSchema}
                        title="Output schema"
                        label={`Output schema of ${t.tool}`}
                      />
                    ) : null}
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
