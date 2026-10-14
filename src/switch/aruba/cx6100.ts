// HPE Aruba CX 6100 Series hardware catalog.
// Evidence source: AOS-CX 10.12 Release Notes (rn_6000-6100_10-12-1020/1030), Phase 2.3 Section 4.
//
// Recovered SKUs (official marketing names from release notes):
//   JL675A — Aruba 6100 48G Class4 PoE 4SFP+ 370W  — min 10.06.0001
//   JL676A — Aruba 6100 48G 4SFP+                  — min 10.06.0001
//   JL677A — Aruba 6100 24G Class4 PoE 4SFP+ 370W  — min 10.06.0001
//   JL678A — Aruba 6100 24G 4SFP+                  — min 10.06.0001
//   JL679A — Aruba 6100 12G Class4 PoE 2G/2SFP+ 139W — min 10.06.0001
//
// CORRECTION: Previous file had JL675A=24G non-PoE, JL677A=48G non-PoE — both WRONG.
// JL675A is 48G PoE; JL677A is 24G PoE. Fixed per official release note data.
//
// VSF: CX 6100 NOT listed in Aruba Central AOS-CX VSF stacking support table.
// vsfStatus: UNSUPPORTED. Evidence: ARUBA-EVD-VSF-CENTRAL.

import type { SwitchHardware, SwitchPortDefinition, SwitchCapability, SwitchVsfConfig, SwitchCompatibility } from '../types.ts'

const EVD = ['ARUBA-EVD-CX6100-1012-RN']
const MIN_VER = '10.06.0001'

const CAP: SwitchCapability = {
  vlan: 'SUPPORTED', accessVlan: 'SUPPORTED', voiceVlan: 'SUPPORTED',
  trunk: 'SUPPORTED', nativeVlan: 'SUPPORTED', lacp: 'SUPPORTED', lag: 'SUPPORTED',
  svi: 'SUPPORTED', staticRouting: 'UNKNOWN', dynamicRouting: 'UNKNOWN',
  stp: 'SUPPORTED', acl: 'UNKNOWN', vrf: 'UNKNOWN', vsf: 'UNKNOWN',
  qos: 'UNKNOWN', dhcpRelay: 'UNKNOWN', lldp: 'SUPPORTED', management: 'SUPPORTED',
  notes: 'CX 6100 access-layer. VSF UNKNOWN (absent from VSF platform table). Routing/ACL/VRF/QoS require feature guide verification.',
}

const NO_VSF: SwitchVsfConfig = {
  supported: false, vsfStatus: 'UNKNOWN',
  evidenceIds: ['ARUBA-EVD-VSF-CENTRAL'],
  notes: 'CX 6100: UNKNOWN (absent from Aruba Central AOS-CX switch stacking support table; absence does not prove non-support).',
}

function compat(id: string): SwitchCompatibility[] {
  return ['aos-cx-10.13', 'aos-cx-10.16', 'aos-cx-10.17', 'aos-cx-10.18'].map((osId) => ({
    hardwareId: id, osId, status: 'REVIEW_REQUIRED' as const,
    reason: `CX 6100 min software ${MIN_VER} satisfies ${osId.replace('aos-cx-', '')} floor; train qualification review required.`,
    minimumVersion: MIN_VER, evidenceIds: EVD,
  }))
}

function rj45(start: number, count: number, poe: boolean): SwitchPortDefinition[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `1/1/${start + i}`, type: 'RJ45' as const,
    supportedSpeeds: ['10M', '100M', '1G'] as SwitchPortDefinition['supportedSpeeds'],
    poe, poeStandard: poe ? '802.3at Class 4' : undefined, role: 'access' as const,
  }))
}

function sfpPlus(start: number, count: number): SwitchPortDefinition[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `1/1/${start + i}`, type: 'SFP+' as const,
    supportedSpeeds: ['1G', '10G'] as SwitchPortDefinition['supportedSpeeds'],
    poe: false, role: 'uplink' as const, sfpRequired: true,
  }))
}

function rj45Uplink(start: number, count: number): SwitchPortDefinition[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `1/1/${start + i}`, type: 'RJ45' as const,
    supportedSpeeds: ['10M', '100M', '1G'] as SwitchPortDefinition['supportedSpeeds'],
    poe: false, role: 'uplink' as const,
  }))
}

// JL675A — Aruba 6100 48G Class4 PoE 4SFP+ 370W
export const CX6100_48G_POE: SwitchHardware = {
  id: 'aruba-cx-6100-48g-poe-jl675a', vendor: 'hpe_aruba', series: 'CX 6100',
  marketingModel: 'Aruba 6100 48G Class4 PoE 4SFP+ 370W',
  model: 'CX 6100 48G CL4 PoE 4SFP+', productNumber: 'JL675A', minimumVersion: MIN_VER,
  ports: [...rj45(1, 48, true), ...sfpPlus(49, 4)],
  totalAccessPorts: 48, totalUplinkPorts: 4, poeCapable: true, poeBudgetWatts: 370,
  vsf: NO_VSF, capabilities: CAP,
  compatibilityRules: compat('aruba-cx-6100-48g-poe-jl675a'), evidenceIds: EVD,
  notes: 'JL675A: 48x1G RJ45 PoE (802.3at Class 4) + 4x SFP+. 370W budget. Min AOS-CX 10.06.0001.',
}

// JL676A — Aruba 6100 48G 4SFP+
export const CX6100_48G: SwitchHardware = {
  id: 'aruba-cx-6100-48g-jl676a', vendor: 'hpe_aruba', series: 'CX 6100',
  marketingModel: 'Aruba 6100 48G 4SFP+',
  model: 'CX 6100 48G 4SFP+', productNumber: 'JL676A', minimumVersion: MIN_VER,
  ports: [...rj45(1, 48, false), ...sfpPlus(49, 4)],
  totalAccessPorts: 48, totalUplinkPorts: 4, poeCapable: false,
  vsf: NO_VSF, capabilities: CAP,
  compatibilityRules: compat('aruba-cx-6100-48g-jl676a'), evidenceIds: EVD,
  notes: 'JL676A: 48x1G RJ45 (no PoE) + 4x SFP+. Min AOS-CX 10.06.0001.',
}

// JL677A — Aruba 6100 24G Class4 PoE 4SFP+ 370W
export const CX6100_24G_POE: SwitchHardware = {
  id: 'aruba-cx-6100-24g-poe-jl677a', vendor: 'hpe_aruba', series: 'CX 6100',
  marketingModel: 'Aruba 6100 24G Class4 PoE 4SFP+ 370W',
  model: 'CX 6100 24G CL4 PoE 4SFP+', productNumber: 'JL677A', minimumVersion: MIN_VER,
  ports: [...rj45(1, 24, true), ...sfpPlus(25, 4)],
  totalAccessPorts: 24, totalUplinkPorts: 4, poeCapable: true, poeBudgetWatts: 370,
  vsf: NO_VSF, capabilities: CAP,
  compatibilityRules: compat('aruba-cx-6100-24g-poe-jl677a'), evidenceIds: EVD,
  notes: 'JL677A: 24x1G RJ45 PoE (802.3at Class 4) + 4x SFP+. 370W budget. Min AOS-CX 10.06.0001.',
}

// JL678A — Aruba 6100 24G 4SFP+
export const CX6100_24G: SwitchHardware = {
  id: 'aruba-cx-6100-24g-jl678a', vendor: 'hpe_aruba', series: 'CX 6100',
  marketingModel: 'Aruba 6100 24G 4SFP+',
  model: 'CX 6100 24G 4SFP+', productNumber: 'JL678A', minimumVersion: MIN_VER,
  ports: [...rj45(1, 24, false), ...sfpPlus(25, 4)],
  totalAccessPorts: 24, totalUplinkPorts: 4, poeCapable: false,
  vsf: NO_VSF, capabilities: CAP,
  compatibilityRules: compat('aruba-cx-6100-24g-jl678a'), evidenceIds: EVD,
  notes: 'JL678A: 24x1G RJ45 (no PoE) + 4x SFP+. Min AOS-CX 10.06.0001.',
}

// JL679A — Aruba 6100 12G Class4 PoE 2G/2SFP+ 139W
// 12x RJ45 PoE access + 2x RJ45 uplink + 2x SFP+ uplink, 139W budget
export const CX6100_12G_POE: SwitchHardware = {
  id: 'aruba-cx-6100-12g-poe-jl679a', vendor: 'hpe_aruba', series: 'CX 6100',
  marketingModel: 'Aruba 6100 12G Class4 PoE 2G/2SFP+ 139W',
  model: 'CX 6100 12G CL4 PoE 2G/2SFP+', productNumber: 'JL679A', minimumVersion: MIN_VER,
  ports: [...rj45(1, 12, true), ...rj45Uplink(13, 2), ...sfpPlus(15, 2)],
  totalAccessPorts: 12, totalUplinkPorts: 4, poeCapable: true, poeBudgetWatts: 139,
  vsf: NO_VSF, capabilities: CAP,
  compatibilityRules: compat('aruba-cx-6100-12g-poe-jl679a'), evidenceIds: EVD,
  notes: 'JL679A: 12x1G RJ45 PoE + 2x1G RJ45 uplinks + 2x SFP+ uplinks. 139W budget. Min AOS-CX 10.06.0001.',
}
export const CX6100_JL675A = CX6100_48G_POE
export const CX6100_JL676A = CX6100_48G
export const CX6100_JL677A = CX6100_24G_POE
export const CX6100_JL678A = CX6100_24G
export const CX6100_JL679A = CX6100_12G_POE


export const CX6100_MODELS: SwitchHardware[] = [
  CX6100_48G_POE, CX6100_48G, CX6100_24G_POE, CX6100_24G, CX6100_12G_POE,
]
