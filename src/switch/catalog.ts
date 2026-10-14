// Vendor-neutral switch catalog.
// Cisco and Juniper entries are kept as before (model + software stubs for UI continuity).
// Aruba entries now come from the hardware catalog — not from models × versions expansion.

import type { SwitchVendor, SwitchHardware } from './types.ts'
import type { SwitchOsRelease } from './types.ts'
import { ALL_ARUBA_MODELS } from './aruba/index.ts'
import { AOS_CX_RELEASES } from './aosCxOs.ts'
import { evaluateCompatibility, compatibleOsReleases } from './compatibility.ts'

// ─── Cisco IOS-XE stub catalog (unchanged from original behavior) ───────────────
// These are NOT using the new hardware model — Cisco migration is not yet modeled.
// Kept for UI backward compatibility only.
export const CISCO_IOS_XE_VERSIONS = ['17.9', '17.10', '17.11', '17.12']
export const CISCO_MODELS: Record<string, string[]> = {
  'Catalyst 9200 Series': ['C9200-24P', 'C9200-48P', 'C9200L-24P-4G', 'C9200L-48P-4G'],
  'Catalyst 9300 Series': ['C9300-24P', 'C9300-48P', 'C9300-24T', 'C9300-48T', 'C9300X-24Y', 'C9300X-48HX'],
  'Catalyst 9400 Series': ['C9404R', 'C9407R', 'C9410R'],
}

// ─── Juniper Junos stub catalog (unchanged from original behavior) ───────────────
export const JUNIPER_JUNOS_VERSIONS = ['21.4R3', '22.4R3', '23.2R2', '23.4R1']
export const JUNIPER_MODELS: Record<string, string[]> = {
  'EX3400 Series': ['EX3400-24P', 'EX3400-48P'],
  'EX4100 Series': ['EX4100-24P', 'EX4100-48P'],
  'EX4400 Series': ['EX4400-24P', 'EX4400-48P'],
  'EX4650 Series': ['EX4650-48Y'],
}

// ─── Aruba hardware catalog (new architecture) ───────────────────────────────────
export const ARUBA_HARDWARE: SwitchHardware[] = ALL_ARUBA_MODELS

/** Get all Aruba series names (for series selector UI) */
export function getArubaSeries(): string[] {
  return [...new Set(ARUBA_HARDWARE.map((hw) => hw.series))]
}

/** Get hardware models for a given Aruba series */
export function getArubaHardwareBySeries(series: string): SwitchHardware[] {
  return ARUBA_HARDWARE.filter((hw) => hw.series === series)
}

/** Get a specific Aruba hardware model by ID */
export function getArubaHardwareById(id: string): SwitchHardware | undefined {
  return ARUBA_HARDWARE.find((hw) => hw.id === id)
}

/** Get OS releases compatible with (or UNKNOWN for) a given Aruba hardware model */
export function getCompatibleOs(hardware: SwitchHardware, includeUnknown = true): SwitchOsRelease[] {
  return compatibleOsReleases(hardware, AOS_CX_RELEASES, includeUnknown)
}

/** Evaluate compatibility between hardware and OS — never returns implicit READY */
export { evaluateCompatibility }

export { compareVersions, isVersionAtOrAboveFloor } from './compatibility.ts'

/** All Aruba OS releases */
export { AOS_CX_RELEASES }

/** Vendor list for UI */
export const SWITCH_VENDORS: { id: SwitchVendor; label: string }[] = [
  { id: 'cisco', label: 'Cisco' },
  { id: 'hpe_aruba', label: 'HPE Aruba Networking' },
  { id: 'juniper', label: 'Juniper Networks' },
]
