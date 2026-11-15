import { act, renderHook } from '@testing-library/react';
import {
  collectionLink,
  rememberCollection,
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

describe('rememberCollection: only a link this browser made or sent is kept', () => {
  const ref = (over: object = {}) => ({ id: ID, url: `/mine/${ID}`, created: false, ...over });
  it('keeps a link the save created', () => {
    rememberCollection(ref({ created: true }));
    expect(readCollectionId()).toBe(ID);
  });
  it('keeps the link this browser sent (the save joined it)', () => {
    rememberCollection(ref(), ID);
    expect(readCollectionId()).toBe(ID);
  });
  it("does NOT adopt a link it never held: saving a version of someone else's model can answer that model's link", () => {
    rememberCollection(ref());
    expect(readCollectionId()).toBeNull();
    rememberCollection(ref(), null);
    expect(readCollectionId()).toBeNull();
    rememberCollection(ref(), 'c-SomethingElse0123456789');
    expect(readCollectionId()).toBeNull();
  });
  it('a link the server made to replace an unknown one is kept (created), and nothing changes without a link', () => {
    saveCollectionId('c-Mistyped0123456789ab');
    rememberCollection(
      ref({ id: 'c-BrandNewLink0123456789', created: true }),
      'c-Mistyped0123456789ab',
    );
    expect(readCollectionId()).toBe('c-BrandNewLink0123456789');
    rememberCollection(null);
    rememberCollection(undefined);
    expect(readCollectionId()).toBe('c-BrandNewLink0123456789');
  });
});
