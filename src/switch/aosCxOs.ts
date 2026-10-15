// AOS-CX OS release catalog.
// Sources: HPE Aruba Networking official documentation.
//
// Lifecycle classification:
//   LSR = Long-term Support Release (HPE Aruba terminology)
//   SSR = Short-term Support Release
//
// Lifecycle status is dynamically computed from lifecycle dates.

import type { LifecycleStatus, SwitchOsRelease } from './types.ts'

/**
 * Data-driven lifecycle status calculation based on release and EOS dates.
 * Do not hardcode status='ACTIVE' without logic.
 */
export function computeLifecycleStatus(
  releaseDate?: string,
  endOfSupportDate?: string,
  referenceDate: string = '2026-10-06'
): LifecycleStatus {
  if (!releaseDate || releaseDate === 'UNVERIFIED') return 'UNKNOWN'
  if (endOfSupportDate) {
    if (new Date(referenceDate).getTime() > new Date(endOfSupportDate).getTime()) {
      return 'END_OF_SUPPORT'
    }
  }
  return 'ACTIVE'
}

export const AOS_CX_RELEASES: SwitchOsRelease[] = [
  {
    id: 'aos-cx-10.13',
    vendor: 'hpe_aruba',
    product: 'AOS-CX',
    train: '10.13',
    exactVersion: undefined,  // ponytail: 10.13.x — no authoritative patch version confirmed; add when official release notes cite exact build
    releaseType: 'LSR',
    initialReleaseDate: '2023-11-14',
    endOfSupportDate: '2028-11-30',
    lifecycleStatus: computeLifecycleStatus('2023-11-14', '2028-11-30'),
    evidenceIds: ['ARUBA-EVD-LIFECYCLE-1013'],
    notes: 'AOS-CX 10.13 is classified as LSR with 5-year support lifecycle.',
  },
  {
    id: 'aos-cx-10.16',
    vendor: 'hpe_aruba',
    product: 'AOS-CX',
    train: '10.16',
    exactVersion: '10.16.1006',  // cited in release notes as minimum version floor for certain hardware; train version confirmed LSR
    releaseType: 'LSR',
    initialReleaseDate: 'UNVERIFIED',
    endOfSupportDate: undefined,
    lifecycleStatus: 'UNKNOWN',
    evidenceIds: ['ARUBA-EVD-LIFECYCLE-1016'],
    notes: 'AOS-CX 10.16 is classified as LSR with 5-year support lifecycle. Initial release date is UNVERIFIED.',
  },
  {
    id: 'aos-cx-10.17',
    vendor: 'hpe_aruba',
    product: 'AOS-CX',
    train: '10.17',
    exactVersion: undefined,  // ponytail: 10.17.x — no authoritative patch version confirmed; add when official SSR release notes cite exact build
    releaseType: 'SSR',
    initialReleaseDate: 'UNVERIFIED',
    endOfSupportDate: undefined,
    lifecycleStatus: 'UNKNOWN',
    evidenceIds: ['ARUBA-EVD-LIFECYCLE-1017'],
    notes: 'AOS-CX 10.17 is classified as SSR (Short-term Support Release). Initial release date is UNVERIFIED.',
  },
  {
    id: 'aos-cx-10.18',
    vendor: 'hpe_aruba',
    product: 'AOS-CX',
    train: '10.18',
    exactVersion: undefined,  // ponytail: 10.18.x — no authoritative patch version confirmed; add when official SSR release notes cite exact build
    releaseType: 'SSR',
    initialReleaseDate: 'UNVERIFIED',
    endOfSupportDate: undefined,
    lifecycleStatus: 'UNKNOWN',
    evidenceIds: ['ARUBA-EVD-LIFECYCLE-1018'],
    notes: 'AOS-CX 10.18 is classified as SSR with standard short maintenance cycle. Initial release date is UNVERIFIED.',
  },
]

export function getOsRelease(id: string): SwitchOsRelease | undefined {
  return AOS_CX_RELEASES.find((r) => r.id === id)
}

/** All AOS-CX OS IDs for use in compatibility evaluator */
export const ALL_AOS_CX_IDS = AOS_CX_RELEASES.map((r) => r.id)
