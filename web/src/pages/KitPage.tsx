import { useState } from 'react';
import {
  Button,
  Card,
  Chip,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Tile,
} from '@/components';
import { CheckIcon, SearchIcon } from '@/icons';

export function KitPage() {
  const [on, setOn] = useState('All');
  return (
    <div>
      <section className="section">
        <h2>Buttons &amp; chips</h2>
        <div className="row" style={{ marginTop: 14 }}>
          <Button variant="primary">
            <CheckIcon /> Primary
          </Button>
          <Button>Default</Button>
          <Button variant="ghost">Ghost</Button>
          <Button disabled>Disabled</Button>
          <Chip>Neutral</Chip>
          <Chip tone="ok" dot>
            Recall@5 0.94
          </Chip>
          <Chip tone="warn" dot>
            Recall@5 0.88
          </Chip>
          <Chip tone="bad">Failed</Chip>
          <Chip tone="info">Info</Chip>
          <Chip tone="acc" dot>
            Updating · 62%
          </Chip>
        </div>
      </section>
      <section className="section">
        <h2>Filter pills</h2>
        <div className="row" style={{ marginTop: 14 }} role="group" aria-label="Category">
          {['All', 'E-commerce', 'Payments'].map((c) => (
            <button
              key={c}
              type="button"
              className="pillf"
              aria-pressed={on === c}
              onClick={() => setOn(c)}
            >
              {c}
            </button>
          ))}
        </div>
      </section>
      <section className="section">
        <h2>Tiles &amp; inputs</h2>
        <div className="kit-grid" style={{ marginTop: 14 }}>
          <Tile value={137} label="endpoints" />
          <Tile value={31} label="models" />
          <Card className="pad">
            <Field label="Maintainer key" hint="Kept in memory only." mono type="password" />
            <Field label="Search APIs" type="search" placeholder="Search" />
            <SearchIcon width={18} height={18} />
          </Card>
        </div>
      </section>
      <section className="section">
        <h2>States</h2>
        <div className="kit-grid" style={{ marginTop: 14 }}>
          <Card>
            <LoadingState />
          </Card>
          <Card>
            <EmptyState title="Nothing here yet">Add an API to get started.</EmptyState>
          </Card>
          <Card>
            <ErrorState message="The API did not respond." onRetry={() => undefined} />
          </Card>
        </div>
      </section>
      <section className="section">
        <h2>Code</h2>
        <pre className="code" style={{ marginTop: 14 }}>
          GET /v1/apis
        </pre>
      </section>
    </div>
  );
}
