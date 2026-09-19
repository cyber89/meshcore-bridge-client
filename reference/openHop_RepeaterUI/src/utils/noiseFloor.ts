interface NoiseFloorLike {
  noise_floor_dbm?: number | null;
  noise_floor?: number | null;
}

export function mapNoiseFloorValue(item: NoiseFloorLike): number | null {
  return item.noise_floor_dbm ?? item.noise_floor ?? null;
}
