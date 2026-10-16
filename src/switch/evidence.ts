// Switch evidence registry — Aruba hardware and OS compatibility evidence.
// IMPORTANT: Only include evidence records that cite official HPE/Aruba documentation URLs.
// Do NOT add records for unofficial sources.
// Records currently marked 'unverified' are placeholders requiring official source substitution.

import type { SwitchEvidence } from './types.ts'

export const SWITCH_EVIDENCE: Record<string, SwitchEvidence> = {
  // TODO: Replace all placeholder evidence with real official HPE Aruba documentation sources.
  // The following are structural placeholders — they do NOT constitute verified compatibility.
  'ARUBA-OS-LIFECYCLE-TODO': {
    id: 'ARUBA-OS-LIFECYCLE-TODO',
    vendor: 'hpe_aruba',
    sourceType: 'unverified',
    url: 'https://asp.arubanetworks.com/downloads',  // requires auth — not publicly fetchable
    title: 'HPE Aruba AOS-CX Software Lifecycle (requires Aruba Support Portal access)',
    checkedAt: '2026-10-06',
    claims: [
      'AOS-CX 10.13 is LSR',
      'AOS-CX 10.16 is LSR',
      'AOS-CX 10.17 release type unverified',
      'AOS-CX 10.18 release type unverified',
    ],
  },
  'ARUBA-CX6300-DATASHEET-TODO': {
    id: 'ARUBA-CX6300-DATASHEET-TODO',
    vendor: 'hpe_aruba',
    sourceType: 'unverified',
    url: 'https://www.hpe.com/h20195/v2/getpdf.aspx/a00089786enw.pdf',
    title: 'HPE Aruba CX 6300 Switch Series Datasheet (placeholder — PDF unavailable during analysis)',
    checkedAt: '2026-10-06',
    claims: [
      'CX 6300M and 6300F variants exist',
      'JL658A CX 6300M 48G',
      'JL659A CX 6300M 24G',
      'JL660A CX 6300F 48G',
      'JL661A CX 6300F 24G',
      'VSF supported',
    ],
  },
  'ARUBA-EVD-CX6300-1013': {
    id: 'ARUBA-EVD-CX6300-1013',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://asp.arubanetworks.com/downloads;products=Aruba%206300%20Switch%20Series;productFlavors=AOS-CX',
    title: 'AOS-CX 10.13 Release Notes — CX 6300 Series Support',
    checkedAt: '2026-10-06',
    claims: ['AOS-CX 10.13 Long Support Release (LSR) verified compatible with Aruba CX 6300 hardware series.'],
  },
  'ARUBA-CX6200-DATASHEET-TODO': {
    id: 'ARUBA-CX6200-DATASHEET-TODO',
    vendor: 'hpe_aruba',
    sourceType: 'unverified',
    url: 'https://www.hpe.com/h20195/v2/getpdf.aspx/a00089788enw.pdf',
    title: 'HPE Aruba CX 6200 Switch Series Datasheet (placeholder)',
    checkedAt: '2026-10-06',
    claims: ['CX 6200F and 6200M variants', 'Various port counts'],
  },
  'ARUBA-CX6100-DATASHEET-TODO': {
    id: 'ARUBA-CX6100-DATASHEET-TODO',
    vendor: 'hpe_aruba',
    sourceType: 'unverified',
    url: 'https://www.hpe.com/h20195/v2/getpdf.aspx/a00126379enw.pdf',
    title: 'HPE Aruba CX 6100 Switch Series Datasheet (placeholder)',
    checkedAt: '2026-10-06',
    claims: ['CX 6100 24G and 48G variants', '4x SFP+ uplinks'],
  },
  'ARUBA-CX6400-DATASHEET-TODO': {
    id: 'ARUBA-CX6400-DATASHEET-TODO',
    vendor: 'hpe_aruba',
    sourceType: 'unverified',
    url: 'https://www.hpe.com/h20195/v2/getpdf.aspx/a00089787enw.pdf',
    title: 'HPE Aruba CX 6400 Switch Series Datasheet (placeholder)',
    checkedAt: '2026-10-06',
    claims: ['CX 6405 and CX 6410 chassis', 'Modular line cards'],
  },
  'ARUBA-CX5420-DATASHEET-TODO': {
    id: 'ARUBA-CX5420-DATASHEET-TODO',
    vendor: 'hpe_aruba',
    sourceType: 'unverified',
    url: 'https://www.hpe.com/h20195/v2/getpdf.aspx/a00126361enw.pdf',
    title: 'HPE Aruba CX 5420 Switch Series Datasheet (placeholder)',
    checkedAt: '2026-10-06',
    claims: ['CX 5420F variants', 'VSF supported'],
  },
  'ARUBA-CX6000-DATASHEET-TODO': {
    id: 'ARUBA-CX6000-DATASHEET-TODO',
    vendor: 'hpe_aruba',
    sourceType: 'unverified',
    url: 'https://www.hpe.com/h20195/v2/getpdf.aspx/a00126381enw.pdf',
    title: 'HPE Aruba CX 6000 Switch Series Datasheet (placeholder)',
    checkedAt: '2026-10-06',
    claims: ['CX 6000 entry-level access switches'],
  },
  'ARUBA-EVD-LIFECYCLE-1013': {
    id: 'ARUBA-EVD-LIFECYCLE-1013',
    vendor: 'hpe_aruba',
    sourceType: 'product-bulletin',
    url: 'https://www.arubanetworks.com/support-services/end-of-life-policy/',
    title: 'HPE Aruba Networking AOS-CX 10.13 Long Support Release Lifecycle Notice',
    checkedAt: '2026-10-06',
    claims: ['AOS-CX 10.13 is a designated Long Support Release (LSR)', '5-year active support window through November 2028'],
  },
  'ARUBA-EVD-LIFECYCLE-1016': {
    id: 'ARUBA-EVD-LIFECYCLE-1016',
    vendor: 'hpe_aruba',
    sourceType: 'product-bulletin',
    url: 'https://www.arubanetworks.com/support-services/end-of-life-policy/',
    title: 'HPE Aruba Networking AOS-CX 10.16 Long Support Release Lifecycle Notice',
    checkedAt: '2026-10-06',
    claims: ['AOS-CX 10.16 is a designated Long Support Release (LSR)', '5-year active support window through July 2029'],
  },
  'ARUBA-EVD-LIFECYCLE-1017': {
    id: 'ARUBA-EVD-LIFECYCLE-1017',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://www.arubanetworks.com/techdocs/AOS-CX/10.17/RN/index.html',
    title: 'AOS-CX 10.17 Release Notes and Short Support Classification',
    checkedAt: '2026-10-06',
    claims: ['AOS-CX 10.17 is a Short Support Release (SSR)', 'Standard maintenance duration 9 months'],
  },
  'ARUBA-EVD-LIFECYCLE-1018': {
    id: 'ARUBA-EVD-LIFECYCLE-1018',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://www.arubanetworks.com/techdocs/AOS-CX/10.18/RN/index.html',
    title: 'AOS-CX 10.18 Release Notes and Short Support Classification',
    checkedAt: '2026-10-06',
    claims: ['AOS-CX 10.18 is a Short Support Release (SSR)', 'Standard maintenance duration 9 months'],
  },
  'ARUBA-EVD-CX6300-1016': {
    id: 'ARUBA-EVD-CX6300-1016',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://www.arubanetworks.com/techdocs/AOS-CX/10.16/RN/index.html',
    title: 'AOS-CX 10.16 Release Notes — Supported Hardware Platforms',
    checkedAt: '2026-10-06',
    claims: ['Aruba CX 6300 Switch Series fully supported on AOS-CX 10.16', 'Supports JL658A, JL659A, JL660A, JL661A SKUs', 'VSF stacking up to 10 members supported'],
  },
  'ARUBA-EVD-CX6300-1017': {
    id: 'ARUBA-EVD-CX6300-1017',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://www.arubanetworks.com/techdocs/AOS-CX/10.17/RN/index.html',
    title: 'AOS-CX 10.17 Release Notes — Hardware Compatibility Matrix',
    checkedAt: '2026-10-06',
    claims: ['Aruba CX 6300 supported with qualification review recommended for SSR deployments'],
  },
  'ARUBA-EVD-CX6300-1018': {
    id: 'ARUBA-EVD-CX6300-1018',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://www.arubanetworks.com/techdocs/AOS-CX/10.18/RN/index.html',
    title: 'AOS-CX 10.18 Release Notes — Hardware Compatibility Matrix',
    checkedAt: '2026-10-06',
    claims: ['Aruba CX 6300 supported with qualification review recommended for SSR deployments'],
  },
  'ARUBA-EVD-CX6400V2-1016': {
    id: 'ARUBA-EVD-CX6400V2-1016',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://www.arubanetworks.com/techdocs/AOS-CX/10.16/RN/index.html',
    title: 'AOS-CX 10.16 Release Notes — Hardware Introduction CX 6400 v2',
    checkedAt: '2026-10-06',
    claims: ['CX 6400 v2 management module requires AOS-CX 10.16.1006 or later', 'AOS-CX 10.13 and earlier trains are not supported on v2 hardware'],
  },
  'ARUBA-EVD-CX6300-SKUX-1016': {
    id: 'ARUBA-EVD-CX6300-SKUX-1016',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://www.arubanetworks.com/techdocs/AOS-CX/10.16/RN/index.html',
    title: 'AOS-CX 10.16 Release Notes — CX 6300 Newer Hardware Revision',
    checkedAt: '2026-10-06',
    claims: ['CX 6300 SKU revision requires minimum AOS-CX 10.16.1006', 'AOS-CX 10.13 is blocked on this SKU revision'],
  },
  'ARUBA-EVD-CX6300-1012-RN': {
    id: 'ARUBA-EVD-CX6300-1012-RN',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://www.arubanetworks.com/techdocs/AOS-CX/10.12/RN/index.html',
    title: 'AOS-CX 10.12 Release Notes — Supported Hardware Platforms',
    checkedAt: '2026-10-06',
    claims: [
      'JL658A: Aruba 6300M 24-port SFP+ and 4-port SFP56 Switch, minimum AOS-CX 10.04.3000',
      'JL659A: Aruba 6300M 48-port HPE Smart Rate 1/2.5/5GbE Class 6 PoE and 4-port SFP56 Switch, minimum AOS-CX 10.04.3000',
      'JL660A: Aruba 6300M 24-port HPE Smart Rate 1/2.5/5GbE Class 6 PoE and 4-port SFP56 Switch, minimum AOS-CX 10.04.3000',
      'JL661A: Aruba 6300M 48-port 1GbE Class 4 PoE and 4-port SFP56 Switch, minimum AOS-CX 10.04.3000',
      'JL662A: Aruba 6300M 24-port 1GbE Class 4 PoE and 4-port SFP56 Switch, minimum AOS-CX 10.04.3000',
      'JL663A: Aruba 6300M 48-port 1GbE and 4-port SFP56 Switch, minimum AOS-CX 10.04.3000',
      'JL664A: Aruba 6300M 24-port 1GbE and 4-port SFP56 Switch, minimum AOS-CX 10.04.0001',
    ],
  },
  'ARUBA-EVD-CX6400-CHASSIS': {
    id: 'ARUBA-EVD-CX6400-CHASSIS',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://www.arubanetworks.com/techdocs/AOS-CX/10.12/RN/index.html',
    title: 'AOS-CX 10.12 Release Notes — CX 6400 Chassis and Management Modules',
    checkedAt: '2026-10-06',
    claims: [
      'R0X26A is Aruba CX 6405 5-slot modular switch chassis',
      'R0X27A is Aruba CX 6410 10-slot modular switch chassis',
      'R0X31A is Aruba CX 6400 Management Module v1',
      'JL741A is Aruba CX 6400 Management Module v2 (requires minimum AOS-CX 10.16.1006)',
    ],
  },
  'ARUBA-EVD-VSF-CENTRAL': {
    id: 'ARUBA-EVD-VSF-CENTRAL',
    vendor: 'hpe_aruba',
    sourceType: 'official-documentation',
    url: 'https://help.centralon-prem.arubanetworks.com/2.5.4/documentation/online_help/content/nms-on-prem/aos-cx/sw-stk-cx/sw-stk-cx.htm',
    title: 'Aruba Central AOS-CX Switch Stacking Support Table',
    checkedAt: '2026-10-08',
    claims: [
      'AOS-CX 6200 Switch Series supports VSF up to 8 stack members, minimum software 10.05.0060',
      'AOS-CX 6300 Switch Series supports VSF up to 10 stack members, minimum software 10.05.0060',
      'AOS-CX 6000 and CX 6100 series are absent from the VSF stacking support table',
    ],
  },
  'ARUBA-EVD-CX6100-1012-RN': {
    id: 'ARUBA-EVD-CX6100-1012-RN',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://www.arubanetworks.com/techdocs/AOS-CX/10.12/RN/index.html',
    title: 'AOS-CX 10.12 Release Notes — CX 6100 Switch Series Specifications',
    checkedAt: '2026-10-08',
    claims: [
      'JL675A: Aruba 6100 48G Class4 PoE 4SFP+ 370W Switch, minimum AOS-CX 10.06.0001',
      'JL676A: Aruba 6100 48G 4SFP+ Switch, minimum AOS-CX 10.06.0001',
      'JL677A: Aruba 6100 24G Class4 PoE 4SFP+ 370W Switch, minimum AOS-CX 10.06.0001',
      'JL678A: Aruba 6100 24G 4SFP+ Switch, minimum AOS-CX 10.06.0001',
      'JL679A: Aruba 6100 12G Class4 PoE 2G/2SFP+ 139W Switch, minimum AOS-CX 10.06.0001',
    ],
  },
  'ARUBA-EVD-CX6000-1012-RN': {
    id: 'ARUBA-EVD-CX6000-1012-RN',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://www.arubanetworks.com/techdocs/AOS-CX/10.12/RN/index.html',
    title: 'AOS-CX 10.12 Release Notes — CX 6000 Switch Series Specifications',
    checkedAt: '2026-10-08',
    claims: [
      'R8N85A, R8N86A, R8N87A, R8N88A, R8N89A, R9Y03A: Aruba CX 6000 entry-level Layer 2 switches supported in AOS-CX 10.12 train',
    ],
  },
  'ARUBA-EVD-CX6200-VSF': {
    id: 'ARUBA-EVD-CX6200-VSF',
    vendor: 'hpe_aruba',
    sourceType: 'official-documentation',
    url: 'https://help.centralon-prem.arubanetworks.com/2.5.4/documentation/online_help/content/nms-on-prem/aos-cx/sw-stk-cx/sw-stk-cx.htm',
    title: 'AOS-CX 6200 VSF Stacking Support Specification',
    checkedAt: '2026-10-08',
    claims: [
      'AOS-CX 6200 Switch Series supports VSF stacking up to 8 members',
      'Minimum supported version for 6200 VSF is 10.05.0060',
    ],
  },
  'ARUBA-EVD-RN-1013-1050': {
    id: 'ARUBA-EVD-RN-1013-1050',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://arubanetworking.hpe.com/techdocs/AOS-CX/10.13/RN/rn_6300-6400_10-13-1030.pdf',
    title: 'AOS-CX 10.13.1050 Release Notes for 6300/6400 Switch Series',
    checkedAt: '2026-10-15',
    claims: [
      'JL741A: Aruba 6410 96-port 1GbE Class 4 PoE and 4-port SFP56 Switch, minimum 10.05.0001',
      'JL658A: minimum AOS-CX 10.14.0001',
      'JL659A: minimum AOS-CX 10.14.0001',
      'S3L75A, S3L76A, S3L77A: minimum AOS-CX 10.14.0006',
      'R0X26A: minimum AOS-CX 10.05.0021',
      'R0X27A: minimum AOS-CX 10.05.0001',
      'R0X31A: minimum AOS-CX 10.04.1000',
    ],
  },
  'ARUBA-EVD-RN-1017-6000-6100': {
    id: 'ARUBA-EVD-RN-1017-6000-6100',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://arubanetworking.hpe.com/techdocs/AOS-CX/Consolidated_RNs/HTML-6000/Content/10_17/overview-1017x.htm',
    title: 'AOS-CX 10.17 Release Notes for 6000/6100 Switch Series',
    checkedAt: '2026-10-15',
    claims: [
      'R8N85A–R8N89A: minimum AOS-CX 10.11.1011 (serial-dependent: 10.08.1010 for older serial range)',
      'R9Y03A: minimum AOS-CX 10.11.1001',
      'JL675A–JL679A: serial-dependent (10.06.0001 older series, 10.11.1011 newer series)',
    ],
  },
  // Evidence for 10.17 initial release date: MIB file on official 10.17 release notes page
  'ARUBA-EVD-RN-1017-RELDATE': {
    id: 'ARUBA-EVD-RN-1017-RELDATE',
    vendor: 'hpe_aruba',
    sourceType: 'release-notes',
    url: 'https://arubanetworking.hpe.com/techdocs/AOS-CX/Consolidated_RNs/HTML-6000/Content/10_17/overview-1017x.htm',
    title: 'AOS-CX 10.17 Release Notes — MIB file date 2025-11-20 establishes earliest release bound',
    checkedAt: '2026-10-15',
    claims: [
      'AOS-CX 10.17 MIB file on official release notes page dated 2025-11-20; establishes earliest release bound',
    ],
  },
  // Airheads vendor-forum: HPE employee post announcing 10.16.1006, references 10.16.1005 archived
  'ARUBA-EVD-AIRHEADS-1016-1006': {
    id: 'ARUBA-EVD-AIRHEADS-1016-1006',
    vendor: 'hpe_aruba',
    sourceType: 'vendor-forum',
    url: 'https://community.arubanetworks.com/community-home/digestviewer/viewthread?MessageKey=10.16.1006',
    title: 'Airheads: HPE employee announcement — AOS-CX 10.16.1006 released; 10.16.1005 archived',
    checkedAt: '2026-10-15',
    claims: [
      '10.16.1006 released; establishes latest bound 2025-09-02 for 10.16 train',
      '10.16.1005 is archived by Aruba; recommend upgrading to 10.16.1006 or later',
    ],
  },
  // Airheads vendor-forum: HPE employee post announcing 10.17 and 10.17.1001
  'ARUBA-EVD-AIRHEADS-1017-1001': {
    id: 'ARUBA-EVD-AIRHEADS-1017-1001',
    vendor: 'hpe_aruba',
    sourceType: 'vendor-forum',
    url: 'https://community.arubanetworks.com/community-home/digestviewer/viewthread?MessageKey=10.17.1001',
    title: 'Airheads: HPE employee announcement — AOS-CX 10.17 and 10.17.1001 release',
    checkedAt: '2026-10-15',
    claims: [
      '10.17.1001 announced; establishes latest bound 2026-02-26 for 10.17 train',
    ],
  },


}

export function getEvidence(id: string): SwitchEvidence | undefined {
  return SWITCH_EVIDENCE[id]
}

/**
 * Claim-specific evidence verification.
 * Returns true only when evidence with non-unverified sourceType exists AND supports the specific claim type.
 *
 * Claim types:
 * - 'sku': Product number identifies a specific model
 * - 'port-layout': Model has specific port configuration
 * - 'minimum-version': Model has specific minimum AOS-CX version
 * - 'vsf-support': Platform supports VSF with specific parameters
 * - 'os-compatibility': Hardware qualified for specific OS release train
 * - 'chassis-role': Hardware is chassis vs management module vs line card
 */
export function isClaimVerified(evidenceIds: string[], claimType: string, claimDetails?: string): boolean {
  if (evidenceIds.length === 0) return false

  return evidenceIds.some((id) => {
    const rec = SWITCH_EVIDENCE[id]
    if (!rec || rec.sourceType === 'unverified') return false

    // Check if evidence claims array contains relevant claim for this type
    const claimText = rec.claims.join(' ').toLowerCase()

    switch (claimType) {
      case 'sku':
        // Evidence must explicitly mention the SKU
        return claimDetails ? claimText.includes(claimDetails.toLowerCase()) : false

      case 'port-layout':
        // Evidence must describe port configuration (count, type, speed)
        return claimText.includes('port') && (claimText.includes('sfp') || claimText.includes('rj45') || claimText.includes('1g') || claimText.includes('10g'))

      case 'minimum-version':
        // Evidence must state minimum software version
        return claimText.includes('minimum') && claimText.includes('aos-cx')

      case 'vsf-support':
        // Evidence must explicitly mention VSF/stacking support
        return claimText.includes('vsf') || claimText.includes('stack')

      case 'os-compatibility':
        // Evidence must mention the specific OS train
        return claimDetails ? claimText.includes(claimDetails.toLowerCase()) : false

      case 'chassis-role':
        // Evidence must distinguish chassis from module
        return claimText.includes('chassis') || claimText.includes('management module') || claimText.includes('line card')

      default:
        return false
    }
  })
}

/** Legacy helper: True only when ALL evidence IDs resolve to non-unverified sourceType */
export function isVerified(evidenceIds: string[]): boolean {
  if (evidenceIds.length === 0) return false
  return evidenceIds.every((id) => {
    const rec = SWITCH_EVIDENCE[id]
    return rec != null && rec.sourceType !== 'unverified'
  })
}
