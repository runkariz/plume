import type { ReactNode } from 'react';
import type { ModelSnapshot } from '@/api/types';
import { Chip } from '@/components';
import { ConversionDetail } from './Conversion';
import { findField } from './fields';
import type { Selection } from './graph';
import { warningSummary, warningsFor } from './warnings';

/** One mapping in full: where the data is fetched, the source path, how it is transformed, and the evidence. */
export function MappingDetail({
  snap,
  sel,
  renderDocLink,
}: {
  snap: ModelSnapshot;
  sel: Selection;
  /** How a cited document is shown: a link in the web app. Without it, plain text (the embedded view has no pages). */
  renderDocLink?: (apiId: string, docId: string) => ReactNode;
}) {
  const field = findField(snap, sel.field)?.field;
  const api = snap.inputs.find((a) => a.id === sel.apiId);
  const src = field?.sources[sel.apiId];
  const support = field?.support[sel.apiId];
  if (!field || !api) return null;
  return (
    <>
      <div className="rowhead">
        <h2 className="mono-h">
          {field.path ?? field.name} ← {api.shortName}
        </h2>
        {support === 'derived' ? (
          <Chip tone="warn">
            derived: {src?.join?.length ? 'join' : src?.transform ? 'transform' : 'combine'}
          </Chip>
        ) : support === 'supported' ? (
          <Chip tone="ok">direct</Chip>
        ) : (
          <Chip>not supported</Chip>
        )}
      </div>
      {field.description ? <p className="muted small">{field.description}</p> : null}
      {warningsFor(snap, sel.field, sel.apiId).map((w, i) => (
        <p key={`${w.code}-${i}`} className="cite warn" role="note">
          {w.message || warningSummary(w.code, [w])}
        </p>
      ))}
      {!src ? (
        <p className="muted">{api.shortName} has no equivalent field.</p>
      ) : (
        <>
          {src.fetch ? (
            <div className="dl">
              <div className="dl-k">Fetch</div>
              <div className="mono">{src.fetch.endpoint}</div>
            </div>
          ) : null}
          <div className="dl">
            <div className="dl-k">Source</div>
            <div className="mono">{src.paths.map((p) => p.path).join(', ')}</div>
          </div>
          <ConversionDetail conversion={src.conversion} />
          {src.transform ? (
            <div className="dl">
              <div className="dl-k">Transform</div>
              <div className="mono">{src.transform}</div>
            </div>
          ) : null}
          {src.join?.length ? (
            <div className="dl">
              <div className="dl-k">Join</div>
              {src.join.map((j) => (
                <div key={j} className="mono">
                  {j}
                </div>
              ))}
            </div>
          ) : null}
          {src.evidence?.map((e) => (
            <blockquote key={e.quote} className="evidence">
              <p>“{e.quote}”</p>
              <cite className="faint small">
                {e.docId ? (
                  renderDocLink ? (
                    renderDocLink(sel.apiId, e.docId)
                  ) : (
                    <span>{e.docId}</span>
                  )
                ) : null}
                {e.docId && e.anchor ? ' · ' : ''}
                {e.anchor}
              </cite>
            </blockquote>
          ))}
        </>
      )}
      {snap.citations.missing.length === 0 ? (
        <p className="cite ok">
          All {snap.citations.checked} cited paths found in the pinned builds
        </p>
      ) : (
        <p className="cite warn">
          {snap.citations.checked - snap.citations.found} of {snap.citations.checked} cited paths
          were not found and were dropped: {snap.citations.missing.join(', ')}
        </p>
      )}
    </>
  );
}
