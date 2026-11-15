import { act, renderHook } from '@testing-library/react';
import {
  collectionLink,
  forgetCollection,
  parseCollectionRef,
  readCollectionId,
  saveCollectionId,
  useCollectionId,
} from './collection';

const ID = 'c-AbCdEfGhIjKlMnOpQrStUv';

beforeEach(() => localStorage.clear());

describe('parseCollectionRef', () => {
  it('takes the bare id and the link, absolute or relative, with a query or a trailing slash', () => {
    expect(parseCollectionRef(ID)).toBe(ID);
    expect(parseCollectionRef(`  ${ID}\n`)).toBe(ID);
    expect(parseCollectionRef(`https://plume.example/mine/${ID}`)).toBe(ID);
    expect(parseCollectionRef(`http://127.0.0.1:18493/mine/${ID}/`)).toBe(ID);
    expect(parseCollectionRef(`/mine/${ID}?x=1#top`)).toBe(ID);
  });
  it('refuses everything else, without throwing', () => {
    for (const bad of [
      '',
      'c-',
      'c-short',
      'ok-old-owner-key-3f9a0c71',
      `https://plume.example/models/${ID}`,
      `https://plume.example/mine/${ID}extra stuff`,
      'two words',
      `javascript:alert(1)//mine/${ID}x y`,
      '<script>',
    ])
      expect(parseCollectionRef(bad), bad).toBeNull();
  });
});

describe('the stored id', () => {
  it('is kept, read back, and forgotten', () => {
    expect(readCollectionId()).toBeNull();
    saveCollectionId(ID);
    expect(readCollectionId()).toBe(ID);
    forgetCollection();
    expect(readCollectionId()).toBeNull();
  });
  it('only a well-formed id is kept (what is read from storage is not trusted either)', () => {
    saveCollectionId('not-an-id');
    expect(readCollectionId()).toBeNull();
    localStorage.setItem('plume-collection', 'garbage');
    expect(readCollectionId()).toBeNull();
  });
  it('is kept in step across components in this tab', () => {
    const { result } = renderHook(() => useCollectionId());
    expect(result.current).toBeNull();
    act(() => saveCollectionId(ID));
    expect(result.current).toBe(ID);
    act(() => forgetCollection());
    expect(result.current).toBeNull();
  });
  it('quietly does nothing when storage is blocked', () => {
    const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readCollectionId()).toBeNull();
    expect(() => saveCollectionId(ID)).not.toThrow();
    expect(() => forgetCollection()).not.toThrow();
    get.mockRestore();
    set.mockRestore();
  });
});

describe('collectionLink', () => {
  it("is this site's /mine/<id>", () => {
    expect(collectionLink(ID)).toBe(`${window.location.origin}/mine/${ID}`);
  });
});
