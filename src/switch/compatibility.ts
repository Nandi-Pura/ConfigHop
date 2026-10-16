// Switch hardware ↔ OS compatibility evaluator.
// Computes status from data (floor, train, lifecycle, evidence). No static compatibilityRules.

import type { SwitchHardware, SwitchOsRelease, SwitchCompatibility, SwitchPlatformSelection, CompatibilityStatus } from './types.ts'
import { SWITCH_EVIDENCE } from './evidence.ts'

export function compareVersions(v1: string, v2: string): number {
  const p1 = v1.split('.').map((n) => parseInt(n, 10) || 0)
  const p2 = v2.split('.').map((n) => parseInt(n, 10) || 0)
  const len = Math.max(p1.length, p2.length)
  for (let i = 0; i < len; i++) {
    const a = p1[i] ?? 0
    const b = p2[i] ?? 0
    if (a !== b) return a - b
  }
  return 0
}

export function isVersionAtOrAboveFloor(version: string, minimumVersion: string): boolean {
  return compareVersions(version, minimumVersion) >= 0
}

function versionToTrain(version: string): string {
  const parts = version.split('.')
  return parts.slice(0, 2).join('.')
}

function hasOfficialFloorEvidence(hardware: SwitchHardware): boolean {
  return hardware.evidenceIds.some((id) => {
    const rec = SWITCH_EVIDENCE[id]
    return rec && (rec.sourceType === 'release-notes' || rec.sourceType === 'official-documentation')
  })
}

function isExpiringSoon(endOfSupportDate: string, ref: Date): boolean {
  const eos = new Date(endOfSupportDate).getTime()
  return eos > ref.getTime() && eos - ref.getTime() <= 180 * 24 * 60 * 60 * 1000
}

/**
 * Evaluate compatibility: computed from data, not static rules.
 * Rules: a=missing→UNKNOWN, b=UNVERIFIED floor→UNKNOWN, c=train<floor→BLOCKED,
 * d=same train: build<floor→BLOCKED/no build→REVIEW_REQUIRED,
 * e=lifecycle checks, f=evidence quality, g=READY.
 */
export function evaluateCompatibility(
  hardware: SwitchHardware | undefined,
  os: SwitchOsRelease | undefined,
  build?: string
): SwitchCompatibility {
  if (!hardware) {
    return { hardwareId: 'unknown', osId: os?.id ?? 'unknown', status: 'UNKNOWN',
      reason: 'Hardware is not in the Aruba catalog; compatibility cannot be evaluated.', evidenceIds: [] }
  }
  if (!os) {
    return { hardwareId: hardware.id, osId: 'unknown', status: 'UNKNOWN',
      reason: `OS release is not in the AOS-CX catalog for ${hardware.marketingModel}; compatibility cannot be evaluated.`, evidenceIds: [] }
  }
  const evIds = hardware.evidenceIds
  if (hardware.minimumVersionStatus === 'UNVERIFIED' || hardware.minimumVersion === 'UNVERIFIED') {
    return { hardwareId: hardware.id, osId: os.id, status: 'UNKNOWN',
      reason: `Minimum software version for ${hardware.marketingModel} is UNVERIFIED. Verify against official release notes before evaluating.`,
      evidenceIds: evIds }
  }
  if (!hardware.minimumVersion) {
    return { hardwareId: hardware.id, osId: os.id, status: 'UNKNOWN',
      reason: `No minimum software version recorded for ${hardware.marketingModel}.`, evidenceIds: evIds }
  }
  const floor = hardware.minimumVersion
  const floorTrain = versionToTrain(floor)
  const cmpTrain = compareVersions(os.train, floorTrain)
  if (cmpTrain < 0) {
    return { hardwareId: hardware.id, osId: os.id, status: 'BLOCKED',
      reason: `${hardware.marketingModel} requires AOS-CX >= ${floor}; train ${os.train} is below floor ${floorTrain}.`,
      minimumVersion: floor, evidenceIds: evIds }
  }
  if (cmpTrain === 0) {
    if (build) {
      if (compareVersions(build, floor) < 0) {
        return { hardwareId: hardware.id, osId: os.id, status: 'BLOCKED',
          reason: `Build ${build} < floor ${floor} for ${hardware.marketingModel}.`,
          minimumVersion: floor, evidenceIds: evIds }
      }
    } else {
      return { hardwareId: hardware.id, osId: os.id, status: 'REVIEW_REQUIRED',
        reason: `Train ${os.train} matches floor train; select build >= ${floor} for ${hardware.marketingModel}.`,
        minimumVersion: floor, evidenceIds: evIds }
    }
  }
  const today = new Date()
  const initDate = os.initialReleaseDate
  const eosDate = os.endOfSupportDate
  if (!initDate || initDate === 'UNVERIFIED') {
    return { hardwareId: hardware.id, osId: os.id, status: 'REVIEW_REQUIRED',
      reason: `Initial release date for AOS-CX ${os.train} is unverified; lifecycle cannot be confirmed for ${hardware.marketingModel}.`,
      minimumVersion: floor, evidenceIds: evIds }
  }
  if (eosDate && new Date(eosDate).getTime() <= today.getTime()) {
    return { hardwareId: hardware.id, osId: os.id, status: 'BLOCKED',
      reason: `AOS-CX ${os.train} reached End of Support on ${eosDate}; not qualified for ${hardware.marketingModel}.`,
      minimumVersion: floor, evidenceIds: evIds }
  }
  if (eosDate && isExpiringSoon(eosDate, today)) {
    return { hardwareId: hardware.id, osId: os.id, status: 'REVIEW_REQUIRED',
      reason: `AOS-CX ${os.train} End of Support (${eosDate}) is within 180 days; review lifecycle for ${hardware.marketingModel}.`,
      minimumVersion: floor, evidenceIds: evIds }
  }
  if (!hasOfficialFloorEvidence(hardware)) {
    return { hardwareId: hardware.id, osId: os.id, status: 'REVIEW_REQUIRED',
      reason: `Floor evidence for ${hardware.marketingModel} is not from release-notes/official-documentation; verify before production use.`,
      minimumVersion: floor, evidenceIds: evIds }
  }
  return { hardwareId: hardware.id, osId: os.id, status: 'READY',
    reason: `${hardware.marketingModel} floor ${floor} met by train ${os.train}; lifecycle active; evidence verified.`,
    minimumVersion: floor, evidenceIds: evIds }
}

export function compatibleOsReleases(hardware: SwitchHardware, allOs: SwitchOsRelease[], includeUnknown = false): SwitchOsRelease[] {
  return allOs.filter((os) => {
    const result = evaluateCompatibility(hardware, os)
    if (result.status === 'BLOCKED') return false
    if (result.status === 'UNKNOWN') return includeUnknown
    return true
  })
}

export function buildSelection(hardware: SwitchHardware, os: SwitchOsRelease): SwitchPlatformSelection {
  return { hardware, os, compatibility: evaluateCompatibility(hardware, os) }
}

export function compatibilityLabel(status: CompatibilityStatus): string {
  switch (status) {
    case 'READY': return '✓ Ready'
    case 'REVIEW_REQUIRED': return '⚠ Review Required'
    case 'BLOCKED': return '✕ Blocked'
    case 'UNKNOWN': return '? Unknown'
  }
}

export function compatibilityClass(status: CompatibilityStatus): string {
  switch (status) {
    case 'READY': return 'compat-ready'
    case 'REVIEW_REQUIRED': return 'compat-review'
    case 'BLOCKED': return 'compat-blocked'
    case 'UNKNOWN': return 'compat-unknown'
  }
}


