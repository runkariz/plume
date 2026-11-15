import type { ReactNode } from 'react';
import { Crumbs, Stepper } from '@/components';

export function WizardFrame({
  name,
  step,
  allDone,
  aside,
  children,
}: {
  name: string;
  step: number;
  allDone?: boolean;
  /** Right side of the title row, e.g. the "Live" indicator. */
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      <Crumbs
        items={[
          { label: 'Maintainer', to: '/maintainer' },
          { label: name },
          { label: 'Update knowledge' },
        ]}
      />
      <div className="titlerow">
        <h1 className="h1-sm">{name === 'New API' ? 'Add an API' : `Update ${name}`}</h1>
        {aside}
      </div>
      <Stepper current={step} allDone={allDone} />
      {children}
    </>
  );
}
