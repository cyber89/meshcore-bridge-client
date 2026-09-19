export type MeshCoreContactType = 1 | 2 | 3 | 4;

const PUBKEY_HEX_REGEX = /^[0-9a-fA-F]{64}$/;

export function isValidMeshCorePublicKey(publicKey?: string | null): boolean {
  if (!publicKey) {
    return false;
  }
  return PUBKEY_HEX_REGEX.test(publicKey.trim());
}

export function buildMeshCoreAddContactUrl(params: {
  name: string;
  publicKey: string;
  type: MeshCoreContactType;
}): string {
  const normalizedName = (params.name || '').trim() || 'MeshCore Contact';
  const normalizedKey = params.publicKey.trim();

  if (!isValidMeshCorePublicKey(normalizedKey)) {
    throw new Error('Public key must be a 64-character hex string.');
  }

  const query = new URLSearchParams({
    name: normalizedName,
    public_key: normalizedKey,
    type: String(params.type),
  });

  return `meshcore://contact/add?${query.toString()}`;
}