// AOS-CX OS release catalog.
// Sources: HPE Aruba Networking official documentation.
//
// Lifecycle classification:
//   LSR = Long-term Support Release (HPE Aruba terminology)
//   SSR = Short-term Support Release
//
// Release dates modeled as verified bounds (earliest/latest), not single guessed dates.
// Lifecycle status is computed from the most conservative interpretation of bounds.

import type { LifecycleStatus, OsReleaseBound, SwitchOsRelease } from './types.ts'

const MS_PER_DAY = 86_400_000

/**
 * Compute lifecycle status from release bounds and end-of-support date.
 *
 * Rules (applied against asOf):
 *  1. No earliest bound → UNKNOWN.
 *  2. EOS known:
 *     - both-EOS <= ref → END_OF_SUPPORT.
 *     - earliest-EOS <= ref (latest-EOS > ref) → UNKNOWN (straddling).
 *     - latest-EOS within 180d → EXPIRING_SOON.
 *     - earliest-EOS > 180d away AND earliest.tier=official → ACTIVE.
 *  3. No EOS: derive EOS = release + supportYears. Same rules apply.
 *  4. 10.18 pattern: earliest.tier=unverified → never ACTIVE.
 */
export function computeLifecycleStatus(
  earliest: OsReleaseBound | undefined,
  latest: OsReleaseBound | undefined,
  endOfSupportDate: string | undefined,
  supportYears: number,
  asOf: string = new Date().toISOString().slice(0, 10)
): LifecycleStatus {
  if (!earliest) return 'UNKNOWN'

  const ref = new Date(asOf).getTime()
  const EXPIRING = 180 * MS_PER_DAY
  const supportMs = supportYears * 365.25 * MS_PER_DAY

  const earliestRel = new Date(earliest.date).getTime()
  const latestRel = latest ? new Date(latest.date).getTime() : undefined

  const earliestEos = endOfSupportDate
    ? new Date(endOfSupportDate).getTime()
    : earliestRel + supportMs
  const latestEos = endOfSupportDate
    ? new Date(endOfSupportDate).getTime()
    : (latestRel !== undefined ? latestRel + supportMs : undefined)

  // Both bounds confirm EOS passed
  if (earliestEos <= ref && (latestEos === undefined || latestEos <= ref)) return 'END_OF_SUPPORT'
  // Straddling EOS — uncertain
  if (earliestEos <= ref) return 'UNKNOWN'

  // Check EXPIRING_SOON from latest-EOS (most permissive bound)
  const eosForExpiry = latestEos ?? earliestEos
  if (eosForExpiry > ref && eosForExpiry - ref <= EXPIRING) return 'EXPIRING_SOON'

  // ACTIVE only if earliest bound is official tier and earliest-EOS > 180d away
  if (earliest.tier === 'official' && earliestEos - ref > EXPIRING) return 'ACTIVE'

  return 'UNKNOWN'
}

export const AOS_CX_RELEASES: SwitchOsRelease[] = [
  {
    id: 'aos-cx-10.13',
    vendor: 'hpe_aruba',
    product: 'AOS-CX',
    train: '10.13',
    exactVersion: undefined,
    releaseType: 'LSR',
    initialReleaseEarliest: {
      date: '2023-11-14',
      evidenceIds: ['ARUBA-EVD-LIFECYCLE-1013'],
      reason: 'Official AOS-CX 10.13 RN (build 10.13.1030) dated 2023-11-14; version history confirms same date.',
      tier: 'official',
    },
    initialReleaseLatest: {
      date: '2023-11-14',
      evidenceIds: ['ARUBA-EVD-LIFECYCLE-1013'],
      reason: 'Same source; earliest = latest.',
      tier: 'official',
    },
    endOfSupportDate: '2028-11-30',
    lifecycleStatus: computeLifecycleStatus(
      { date: '2023-11-14', evidenceIds: ['ARUBA-EVD-LIFECYCLE-1013'], reason: 'RN 10.13.1030', tier: 'official' },
      { date: '2023-11-14', evidenceIds: ['ARUBA-EVD-LIFECYCLE-1013'], reason: 'Same source', tier: 'official' },
      '2028-11-30', 5
    ),
    evidenceIds: ['ARUBA-EVD-LIFECYCLE-1013'],
    notes: 'AOS-CX 10.13 LSR; 5-year support; EOS 2028-11-30.',
  },
  {
    id: 'aos-cx-10.16',
    vendor: 'hpe_aruba',
    product: 'AOS-CX',
    train: '10.16',
    exactVersion: '10.16.1006',
    releaseType: 'LSR',
    initialReleaseEarliest: {
      date: '2024-05-21',
      evidenceIds: ['ARUBA-EVD-LIFECYCLE-1016'],
      reason: 'AOS-CX 10.14.0001 RN dated 2024-05-21 (official); 10.16 released after 10.14, so 2024-05-21 is conservative lower bound.',
      tier: 'official',
    },
    initialReleaseLatest: {
      date: '2025-09-02',
      evidenceIds: ['ARUBA-EVD-AIRHEADS-1016-1006'],
      reason: 'Airheads HPE employee post: 10.16.1006 released, 10.16.1005 archived; upper bound for train first availability.',
      tier: 'vendor-forum',
    },
    endOfSupportDate: undefined,
    lifecycleStatus: computeLifecycleStatus(
      { date: '2024-05-21', evidenceIds: ['ARUBA-EVD-LIFECYCLE-1016'], reason: 'After 10.14.0001 RN date (official)', tier: 'official' },
      { date: '2025-09-02', evidenceIds: ['ARUBA-EVD-AIRHEADS-1016-1006'], reason: 'Airheads 10.16.1006 announcement', tier: 'vendor-forum' },
      undefined, 5
    ),
    evidenceIds: ['ARUBA-EVD-LIFECYCLE-1016', 'ARUBA-EVD-AIRHEADS-1016-1006'],
    notes: 'AOS-CX 10.16 LSR. Earliest from official 10.14.0001 RN date; latest from Airheads 10.16.1006 post.',
  },
  {
    id: 'aos-cx-10.17',
    vendor: 'hpe_aruba',
    product: 'AOS-CX',
    train: '10.17',
    exactVersion: undefined,
    releaseType: 'SSR',
    initialReleaseEarliest: {
      date: '2025-11-20',
      evidenceIds: ['ARUBA-EVD-RN-1017-RELDATE'],
      reason: 'MIB file on official AOS-CX 10.17 RN page dated 2025-11-20.',
      tier: 'official',
    },
    initialReleaseLatest: {
      date: '2026-02-26',
      evidenceIds: ['ARUBA-EVD-AIRHEADS-1017-1001'],
      reason: 'Airheads HPE employee post: 10.17 and 10.17.1001 announced 2026-02-26.',
      tier: 'vendor-forum',
    },
    endOfSupportDate: undefined,
    lifecycleStatus: computeLifecycleStatus(
      { date: '2025-11-20', evidenceIds: ['ARUBA-EVD-RN-1017-RELDATE'], reason: 'MIB date on official RN page', tier: 'official' },
      { date: '2026-02-26', evidenceIds: ['ARUBA-EVD-AIRHEADS-1017-1001'], reason: 'Airheads 10.17.1001 announcement', tier: 'vendor-forum' },
      undefined, 1.5
    ),
    evidenceIds: ['ARUBA-EVD-LIFECYCLE-1017', 'ARUBA-EVD-RN-1017-RELDATE', 'ARUBA-EVD-AIRHEADS-1017-1001'],
    notes: 'AOS-CX 10.17 SSR. Earliest from MIB date on official RN; latest from Airheads post.',
  },
  {
    id: 'aos-cx-10.18',
    vendor: 'hpe_aruba',
    product: 'AOS-CX',
    train: '10.18',
    exactVersion: undefined,
    releaseType: 'SSR',
    initialReleaseEarliest: {
      date: '2025-12-08',
      evidenceIds: ['ARUBA-EVD-LIFECYCLE-1018'],
      reason: 'Released after 10.17 (earliest 2025-11-20); 2025-12-08 lower bound from third-party changelog only.',
      tier: 'unverified',
    },
    initialReleaseLatest: undefined,
    endOfSupportDate: undefined,
    lifecycleStatus: computeLifecycleStatus(
      { date: '2025-12-08', evidenceIds: ['ARUBA-EVD-LIFECYCLE-1018'], reason: 'Third-party only', tier: 'unverified' },
      undefined, undefined, 1.5
    ),
    evidenceIds: ['ARUBA-EVD-LIFECYCLE-1018'],
    notes: 'AOS-CX 10.18 SSR. Earliest bound from third-party source only (unverified); not ACTIVE until official source confirms.',
  },
]

export function getOsRelease(id: string): SwitchOsRelease | undefined {
  return AOS_CX_RELEASES.find((r) => r.id === id)
}

/** All AOS-CX OS IDs for use in compatibility evaluator */
export const ALL_AOS_CX_IDS = AOS_CX_RELEASES.map((r) => r.id)

