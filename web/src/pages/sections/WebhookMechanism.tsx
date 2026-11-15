import { Card, Chip, RawJson } from '@/components';

const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
const str = (v: unknown): string =>
  typeof v === 'string' || typeof v === 'number' ? String(v) : '';
const strs = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];

/** "in body at /webhook/address" from a {in, pointer, shape} object of the package. */
function whereText(v: unknown): string {
  const o = obj(v);
  const where = [
    str(o.in) && `in ${str(o.in)}`,
    str(o.pointer) && `at ${str(o.pointer)}`,
    str(o.shape) && `(${str(o.shape)})`,
  ]
    .filter(Boolean)
    .join(' ');
  return where;
}

/**
 * How the package says events are delivered (the webhook mechanism): how to subscribe, unsubscribe and list,
 * the handshake and verification, and the events available. Everything is shown as the package states it.
 */
export function WebhookMechanism({ mechanism }: { mechanism: Record<string, unknown> }) {
  const subscribe = obj(mechanism.subscribe);
  const unsubscribe = obj(mechanism.unsubscribe);
  const list = obj(mechanism.list);
  const handshake = obj(mechanism.handshake);
  const verification = obj(mechanism.verification);
  const prov = obj(mechanism.provenance);
  const events = strs(mechanism.eventsAvailable);
  const evidence = strs(prov.evidence);
  const evidenceUrl = str(prov.evidenceUrl);

  const rows: [string, string][] = [
    ['Subscribe', str(subscribe.endpointId)],
    ['Callback URL', whereText(subscribe.callbackUrl)],
    ['Events to subscribe to', whereText(subscribe.events)],
    [
      'Unsubscribe',
      [
        str(unsubscribe.endpointId),
        str(unsubscribe.idVar) && `(id variable ${str(unsubscribe.idVar)})`,
      ]
        .filter(Boolean)
        .join(' '),
    ],
    ['List subscriptions', str(list.endpointId)],
  ].filter((r): r is [string, string] => Boolean(r[1]));

  return (
    <Card className="pad doc-fields" role="region" aria-label="Webhook delivery">
      <h2 className="h2-sm">How events are delivered</h2>
      <div className="row" style={{ gap: 8, marginBottom: 10 }}>
        {str(mechanism.mode) ? <Chip tone="info">{`mode: ${str(mechanism.mode)}`}</Chip> : null}
        {str(handshake.kind) ? <Chip>{`handshake: ${str(handshake.kind)}`}</Chip> : null}
        {str(verification.kind) ? <Chip>{`verification: ${str(verification.kind)}`}</Chip> : null}
        {mechanism.verification === null ? <Chip>no verification documented</Chip> : null}
      </div>
      {rows.length ? (
        <dl className="facts">
          {rows.map(([k, v]) => (
            <div key={k} className="fact">
              <dt className="muted">{k}</dt>
              <dd className="mono">{v}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {events.length ? (
        <details className="mechanism-events">
          <summary>
            <b>{events.length}</b> events available
          </summary>
          <ul className="row" style={{ gap: 6, marginTop: 8, listStyle: 'none' }}>
            {events.map((e) => (
              <li key={e}>
                <span className="chip mono">{e}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {evidence.length || evidenceUrl ? (
        <details className="mechanism-events">
          <summary>Where the docs say this</summary>
          {evidence.length ? (
            <ul className="mechanism-evidence">
              {evidence.map((e, i) => (
                <li key={i}>
                  <q className="muted">{e}</q>
                </li>
              ))}
            </ul>
          ) : null}
          {evidenceUrl ? (
            <p style={{ marginTop: 8 }}>
              <a href={evidenceUrl} target="_blank" rel="noreferrer">
                Open the vendor page
              </a>
            </p>
          ) : null}
        </details>
      ) : null}
      <RawJson raw={mechanism} title="Mechanism JSON, as in the package" label="Mechanism JSON" />
    </Card>
  );
}
