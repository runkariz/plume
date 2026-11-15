import { Fragment, type ReactNode } from 'react';

/** Lets a long path wrap after its slashes instead of in the middle of a word. */
export function breakable(path: string): ReactNode {
  const parts = path.split('/');
  return parts.map((part, i) => (
    <Fragment key={i}>
      {i > 0 ? (
        <>
          /<wbr />
        </>
      ) : null}
      {part}
    </Fragment>
  ));
}
