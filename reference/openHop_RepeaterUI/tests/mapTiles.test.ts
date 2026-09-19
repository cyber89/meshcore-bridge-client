import { describe, expect, it } from 'vitest';
import { getMapTileUrls } from '@/utils/mapTiles';

describe('map tile URLs', () => {
  it('adds an encoded API key to both dark tile layers', () => {
    expect(getMapTileUrls(true, 'key with/+symbols')).toEqual({
      baseUrl:
        'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png?key=key%20with%2F%2Bsymbols',
      labelsUrl:
        'https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png?key=key%20with%2F%2Bsymbols',
    });
  });

  it('uses light tile layers when light mode is active', () => {
    expect(getMapTileUrls(false, 'carto-key')).toEqual({
      baseUrl: 'https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png?key=carto-key',
      labelsUrl:
        'https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png?key=carto-key',
    });
  });

  it('falls back to light OpenStreetMap tiles without a CARTO key', () => {
    expect(getMapTileUrls(true, '   ')).toEqual({
      baseUrl: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      labelsUrl: null,
    });
  });
});
