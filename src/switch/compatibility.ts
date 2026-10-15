// Switch hardware ↔ OS compatibility evaluator.
// Mirrors backend confighop_core/compatibility.py pattern.
// Hardware compatibility rules are explicit — no implicit "10.x works on everything" assumption.

import type { SwitchHardware, SwitchOsRelease, SwitchCompatibility, SwitchPlatformSelection, CompatibilityStatus } from './types.ts'

/**
 * Evaluate compatibility between a hardware model and an OS release.
 * Returns the matching explicit rule, or a synthetic UNKNOWN result if no rule exists.
 * Never fabricates READY status without an explicit compatibility rule.
 */
export function evaluateCompatibility(hardware: SwitchHardware | undefined, os: SwitchOsRelease | undefined): SwitchCompatibility {
  if (!hardware) {
    return {
      hardwareId: 'unknown',
      osId: os?.id ?? 'unknown',
      status: 'UNKNOWN',
      reason: 'Hardware is not in the Aruba catalog; compatibility cannot be evaluated.',
      evidenceIds: [],
    }
  }
  if (!os) {
    return {
      hardwareId: hardware.id,
      osId: 'unknown',
      status: 'UNKNOWN',
      reason: `OS release is not in the AOS-CX catalog for ${hardware.marketingModel}; compatibility cannot be evaluated.`,
      evidenceIds: [],
    }
  }
  if (hardware.minimumVersionStatus === 'UNVERIFIED' || hardware.minimumVersion === 'UNVERIFIED') {
    return {
      hardwareId: hardware.id,
      osId: os.id,
      status: 'UNKNOWN',
      reason: `Hardware minimum software version for ${hardware.marketingModel} is unverified. Compatibility cannot be evaluated until verified against official release notes.`,
      evidenceIds: hardware.evidenceIds,
    }
  }
  const rule = hardware.compatibilityRules.find((r) => r.osId === os.id)
  if (rule) return rule
  // No explicit rule → UNKNOWN, not READY
  return {
    hardwareId: hardware.id,
    osId: os.id,
    status: 'UNKNOWN',
    reason: `No compatibility rule recorded for ${hardware.marketingModel} with ${os.product} ${os.train}. Verify against HPE Aruba official compatibility matrix.`,
    evidenceIds: [],
  }
}

/**
 * Filter OS releases to only those with a defined compatibility rule for this hardware.
 * OS releases with no rule are excluded unless includeUnknown is true.
 */
export function compatibleOsReleases(hardware: SwitchHardware, allOs: SwitchOsRelease[], includeUnknown = false): SwitchOsRelease[] {
  return allOs.filter((os) => {
    const rule = hardware.compatibilityRules.find((r) => r.osId === os.id)
    if (!rule) return includeUnknown
    return rule.status !== 'BLOCKED'
  })
}

/**
 * Build a full SwitchPlatformSelection from hardware + OS.
 */
export function buildSelection(hardware: SwitchHardware, os: SwitchOsRelease): SwitchPlatformSelection {
  return { hardware, os, compatibility: evaluateCompatibility(hardware, os) }
}

/** UI badge label for compatibility status */
export function compatibilityLabel(status: CompatibilityStatus): string {
  switch (status) {
    case 'READY': return '✓ Ready'
    case 'REVIEW_REQUIRED': return '⚠ Review Required'
    case 'BLOCKED': return '✕ Blocked'
    case 'UNKNOWN': return '? Unknown'
  }
}

/** CSS class hint for compatibility badge */
export function compatibilityClass(status: CompatibilityStatus): string {
  switch (status) {
    case 'READY': return 'compat-ready'
    case 'REVIEW_REQUIRED': return 'compat-review'
    case 'BLOCKED': return 'compat-blocked'
    case 'UNKNOWN': return 'compat-unknown'
  }
}

/**
 * Compare two dot-separated version strings (e.g. "10.04.3000" vs "10.04.2999").
 * Returns negative if v1 < v2, 0 if v1 === v2, positive if v1 > v2.
 */
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

/** Check if a candidate software version meets or exceeds a hardware minimum version floor */
export function isVersionAtOrAboveFloor(version: string, minimumVersion: string): boolean {
  return compareVersions(version, minimumVersion) >= 0
}
