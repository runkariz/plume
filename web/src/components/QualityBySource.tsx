import type { SourceQuality } from '@/api/types';
import { formatScore } from '@/lib/format';

const NAMES: Record<string, string> = { docs: 'Docs questions', spec: 'Spec questions' };

/**
 * The answer-quality scores per question source (docs, spec), under the combined ones. Shown only when the gold set
 * has more than one source: with one, the combined scores already are that source's.
 */
export function QualityBySource({ rows }: { rows: SourceQuality[] | undefined }) {
  if (!rows || rows.length < 2) return null;
  return (
    <table className="quality-sources">
      <caption className="faint small">By question source</caption>
      <thead>
        <tr>
          <th scope="col">Questions</th>
          <th scope="col">Recall@5</th>
          <th scope="col">MRR</th>
          <th scope="col" title="Share of questions whose answer ranks first">
            Top-1 hit rate
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.source}>
            <th scope="row">
              {NAMES[r.source] ?? `${r.source} questions`}
              <span className="faint small qs-count">
                {r.questions} {r.questions === 1 ? 'question' : 'questions'}
              </span>
            </th>
            <td className="mono">{formatScore(r.recallAt5)}</td>
            <td className="mono">{formatScore(r.mrr)}</td>
            <td className="mono">{formatScore(r.top1Rate)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
