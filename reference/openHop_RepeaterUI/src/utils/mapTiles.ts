export interface MapTileUrls {
  baseUrl: string;
  labelsUrl: string | null;
}

export function getMapTileUrls(darkMode: boolean, apiKey: string | null | undefined): MapTileUrls {
  const key = apiKey?.trim();
  if (!key) {
    return {
      baseUrl: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      labelsUrl: null,
    };
  }

  const style = darkMode ? 'dark' : 'light';
  const encodedKey = encodeURIComponent(key);
  const root = `https://{s}.basemaps.cartocdn.com/${style}`;

  return {
    baseUrl: `${root}_nolabels/{z}/{x}/{y}{r}.png?key=${encodedKey}`,
    labelsUrl: `${root}_only_labels/{z}/{x}/{y}{r}.png?key=${encodedKey}`,
  };
}
