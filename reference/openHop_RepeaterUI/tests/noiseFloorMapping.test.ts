import { describe, expect, it } from 'vitest'

import { mapNoiseFloorValue } from '@/utils/noiseFloor'

describe('mapNoiseFloorValue', () => {
  it('preserves zero instead of falling back', () => {
    expect(mapNoiseFloorValue({ noise_floor_dbm: 0 })).toBe(0)
    expect(mapNoiseFloorValue({ noise_floor: 0 })).toBe(0)
  })

  it('returns null for missing values', () => {
    expect(mapNoiseFloorValue({ noise_floor_dbm: null, noise_floor: null })).toBeNull()
    expect(mapNoiseFloorValue({})).toBeNull()
  })

  it('preserves genuine minus 120 readings', () => {
    expect(mapNoiseFloorValue({ noise_floor_dbm: -120 })).toBe(-120)
    expect(mapNoiseFloorValue({ noise_floor: -120 })).toBe(-120)
  })

  it('preserves normal negative readings', () => {
    expect(mapNoiseFloorValue({ noise_floor_dbm: -101.5 })).toBe(-101.5)
    expect(mapNoiseFloorValue({ noise_floor: -101.5 })).toBe(-101.5)
  })
})
