import type { ModelField, ModelSnapshot } from '@/api/types';

/** The canonical path of a field ("lines[].price.amount"); top-level fields have their name. */
export const fieldPath = (f: ModelField): string => f.path ?? f.name;

/** A field in the order it is shown, with where it sits. */
export interface FlatField {
  field: ModelField;
  path: string;
  depth: number;
  parent: string | null;
  /** An object or array with sub-fields. */
  container: boolean;
}

export const isContainer = (f: ModelField): boolean =>
  Array.isArray(f.fields) && f.fields.length > 0;

/** Every field, parents before their children, with its depth. */
export function flatten(
  fields: ModelField[],
  depth = 0,
  parent: string | null = null,
): FlatField[] {
  return fields.flatMap((field) => {
    const path = fieldPath(field);
    return [
      { field, path, depth, parent, container: isContainer(field) },
      ...flatten(field.fields ?? [], depth + 1, path),
    ];
  });
}

export const hasOwnSources = (f: ModelField): boolean =>
  Object.values(f.sources ?? {}).some((s) => s.paths.length > 0);

/**
 * The fields that are drawn and listed as mappings: every leaf, and a container that has sources of its own
 * (mapped as a whole). A container without its own sources only groups its children (coverage counts leaves).
 */
export function mappedFields(snap: ModelSnapshot): FlatField[] {
  return flatten(snap.fields).filter((x) => !x.container || hasOwnSources(x.field));
}

export const countLeaves = (snap: ModelSnapshot): number =>
  flatten(snap.fields).filter((x) => !x.container).length;

export const findField = (snap: ModelSnapshot, path: string): FlatField | undefined =>
  flatten(snap.fields).find((x) => x.path === path);

/** Gives every field its canonical path, for a server that does not send it (older models, mocks). */
export function withPaths(snap: ModelSnapshot): ModelSnapshot {
  const fill = (
    fields: ModelField[],
    parent: ModelField | null,
    parentPath: string,
  ): ModelField[] =>
    fields.map((f) => {
      const path =
        f.path ??
        (parent ? `${parentPath}${parent.type === 'array' ? '[].' : '.'}${f.name}` : f.name);
      return f.fields?.length ? { ...f, path, fields: fill(f.fields, f, path) } : { ...f, path };
    });
  return { ...snap, fields: fill(snap.fields, null, '') };
}
