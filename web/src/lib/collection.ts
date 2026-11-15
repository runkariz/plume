import { useSyncExternalStore } from 'react';
import type { CollectionRef } from '@/api/types';

/**
 * "My models": one link per person, no accounts: the link is the identity. A collection lists the models and model
 * sets someone saved (it is a list, not a key: it changes nothing). The server hands one out on the first save
 * (`collection: {id, url}`), and this browser keeps its id in localStorage so later saves join it and /models lists it.
 * Storage can be unavailable (private window, blocked data): everything here then quietly does nothing.
 */
const KEY = 'plume-collection';
const EVENT = 'plume-collection-changed';

/** "c-" and the server's 22-character token (letters, digits, "-" and "_"). */
export const COLLECTION_ID = /^c-[A-Za-z0-9_-]{8,128}$/;

export function readCollectionId(): string | null {
  try {
    const v = localStorage.getItem(KEY);
    return v && COLLECTION_ID.test(v) ? v : null;
  } catch {
    return null;
  }
}

function notify() {
  try {
    window.dispatchEvent(new Event(EVENT));
  } catch {
    /* no window */
  }
}

export function saveCollectionId(id: string): void {
  if (!COLLECTION_ID.test(id)) return;
  try {
    if (localStorage.getItem(KEY) !== id) localStorage.setItem(KEY, id);
  } catch {
    /* storage unavailable */
  }
  notify();
}

export function forgetCollection(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable */
  }
  notify();
}

/**
 * The id inside what a person pastes: the link ("https://host/mine/c-abc..." or "/mine/c-abc...", with a query or a
 * trailing slash) or the bare id. Null when it is neither. Never throws.
 */
export function parseCollectionRef(text: string): string | null {
  const t = text.trim();
  if (COLLECTION_ID.test(t)) return t;
  const m = /\/mine\/(c-[A-Za-z0-9_-]{8,128})(?=[/?#]|$)/.exec(t);
  return m?.[1] ?? null;
}

/** The link to a collection on this site (the server may not know the web's public address). */
export function collectionLink(id: string): string {
  return `${window.location.origin}/mine/${id}`;
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener('storage', onChange); // another tab
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener('storage', onChange);
  };
}

/** This browser's My models id (null: none yet), kept in step across components and tabs. */
export function useCollectionId(): string | null {
  return useSyncExternalStore(subscribe, readCollectionId, () => null);
}

/**
 * A save answered with a collection: keep its id here, so later saves join it and /models lists it. Only a link this
 * browser MADE (`created`) or SENT (`sent`) is kept: saving a new version of someone else's unlisted model can be
 * answered with the link of the model's lineage, which this browser never held and must not adopt (it would list
 * the other person's models and put this person's next saves into them).
 */
export function rememberCollection(
  ref: CollectionRef | null | undefined,
  sent?: string | null,
): void {
  if (ref?.id && (ref.created || ref.id === sent)) saveCollectionId(ref.id);
}

/**
 * The navigation options for opening what was just saved: the link is shown once, on arrival, when the save started a
 * new collection (or the server has something to say about it). A save into the link already held shows nothing new.
 */
export function collectionArrival(
  ref: CollectionRef | null | undefined,
): { state: { collection: CollectionRef } } | undefined {
  return ref && (ref.created || ref.note) ? { state: { collection: ref } } : undefined;
}
