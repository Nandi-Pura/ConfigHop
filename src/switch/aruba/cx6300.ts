// HPE Aruba CX 6300 Series hardware catalog.
//
// EVIDENCE POLICY:
// - Evidence source: AOS-CX 10.12 Release Notes Supported Hardware Platforms
//   (ARUBA-EVD-CX6300-1012-RN).
// - Recovered official SKUs: JL658A through JL664A.
// - Minimum software floor: 10.04.3000 for JL658A–JL663A; 10.04.0001 for JL664A.
// - Target trains (10.13, 10.16, 10.17, 10.18) meet the minimum software floor;
//   marked REVIEW_REQUIRED pending train-specific qualification.
// - VSF status: UNKNOWN (maxMembers undefined pending official verification).

import type { SwitchHardware, SwitchPortDefinition, SwitchCapability, SwitchVsfConfig, SwitchCompatibility } from '../types.ts'

const EVD_1012 = ['ARUBA-EVD-CX6300-1012-RN']

const FULL_CAP: SwitchCapability = {
  vlan: 'SUPPORTED', accessVlan: 'SUPPORTED', voiceVlan: 'SUPPORTED',
  trunk: 'SUPPORTED', nativeVlan: 'SUPPORTED', lacp: 'SUPPORTED', lag: 'SUPPORTED',
  svi: 'SUPPORTED', staticRouting: 'SUPPORTED', dynamicRouting: 'UNKNOWN',
  stp: 'SUPPORTED', acl: 'SUPPORTED', vrf: 'UNKNOWN', vsf: 'UNKNOWN',
  qos: 'SUPPORTED', dhcpRelay: 'SUPPORTED', lldp: 'SUPPORTED', management: 'SUPPORTED',
  notes: 'dynamicRouting, vrf, vsf: require official AOS-CX feature guide verification for CX 6300.',
}

// VSF: SUPPORTED up to 10 members per official Aruba Central VSF documentation
const VSF_M: SwitchVsfConfig = {
  supported: true, vsfStatus: 'SUPPORTED', technology: 'VSF',
  maxMembers: 10,
  evidenceIds: ['ARUBA-EVD-VSF-CENTRAL', ...EVD_1012],
  notes: 'VSF on CX 6300 Series: SUPPORTED up to 10 stack members per official Aruba Central documentation. Minimum version 10.05.0060.',
}

function compat(hardwareId: string, minimumVersion: string): SwitchCompatibility[] {
  return ['aos-cx-10.13', 'aos-cx-10.16', 'aos-cx-10.17', 'aos-cx-10.18'].map((osId) => ({
    hardwareId,
    osId,
    status: 'REVIEW_REQUIRED' as const,
    reason: `Train ${osId.replace('aos-cx-', '')} meets minimum hardware version floor (${minimumVersion}); production train qualification review required.`,
    minimumVersion,
    evidenceIds: EVD_1012,
  }))
}

function sfpPlus(start: number, count: number): SwitchPortDefinition[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `1/1/${start + i}`, type: 'SFP+' as const,
    supportedSpeeds: ['1G', '10G'] as SwitchPortDefinition['supportedSpeeds'],
    poe: false, role: 'access' as const, sfpRequired: true,
  }))
}

function sfp56(start: number, count: number): SwitchPortDefinition[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `1/1/${start + i}`, type: 'SFP56' as const,
    supportedSpeeds: ['1G', '10G', '25G', '50G'] as SwitchPortDefinition['supportedSpeeds'],
    poe: false, role: 'uplink' as const, sfpRequired: true,
  }))
}

function smartRate(start: number, count: number, poeStandard?: string): SwitchPortDefinition[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `1/1/${start + i}`, type: 'RJ45' as const,
    supportedSpeeds: ['1G', '2.5G', '5G'] as SwitchPortDefinition['supportedSpeeds'],
    poe: true, poeStandard: poeStandard ?? '802.3bt Class 6', role: 'access' as const,
  }))
}

function rj45(start: number, count: number, poe: boolean, poeStandard?: string): SwitchPortDefinition[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `1/1/${start + i}`, type: 'RJ45' as const,
    supportedSpeeds: ['10M', '100M', '1G'] as SwitchPortDefinition['supportedSpeeds'],
    poe, poeStandard: poe ? (poeStandard ?? '802.3at Class 4') : undefined, role: 'access' as const,
  }))
}

// JL658A — Aruba 6300M 24-port SFP+ and 4-port SFP56 Switch, min: 10.14.0001
export const CX6300M_24SFP: SwitchHardware = {
  id: 'aruba-cx-6300m-24sfp-jl658a', vendor: 'hpe_aruba', series: 'CX 6300',
  marketingModel: 'Aruba 6300M 24-port SFP+ and 4-port SFP56 Switch',
  model: 'CX 6300M 24SFP+ 4SFP56',
  hardwareVariant: 'Modular uplink (M) — fiber access',
  productNumber: 'JL658A',
  minimumVersion: '10.14.0001',
  ports: [...sfpPlus(1, 24), ...sfp56(25, 4)],
  totalAccessPorts: 24, totalUplinkPorts: 4, poeCapable: false,
  vsf: VSF_M, capabilities: FULL_CAP,
  compatibilityRules: compat('aruba-cx-6300m-24sfp-jl658a', '10.14.0001'),
  evidenceIds: ['ARUBA-EVD-RN-1013-1050', ...EVD_1012],
  notes: 'JL658A: 24-port SFP+ and 4-port SFP56 Switch. Minimum AOS-CX 10.14.0001.',
}

// Backward-compat alias
export const CX6300M_48G = CX6300M_24SFP

// JL659A — Aruba 6300M 48-port HPE Smart Rate 1/2.5/5GbE Class 6 PoE and 4-port SFP56 Switch, min: 10.14.0001
export const CX6300M_48SR5_POE: SwitchHardware = {
  id: 'aruba-cx-6300m-48sr5-poe-jl659a', vendor: 'hpe_aruba', series: 'CX 6300',
  marketingModel: 'Aruba 6300M 48-port HPE Smart Rate 1/2.5/5GbE Class 6 PoE and 4-port SFP56 Switch',
  model: 'CX 6300M 48SR5 CL6 PoE 4SFP56',
  hardwareVariant: 'Modular uplink (M) — Smart Rate PoE',
  productNumber: 'JL659A',
  minimumVersion: '10.14.0001',
  ports: [...smartRate(1, 48, '802.3bt Class 6'), ...sfp56(49, 4)],
  totalAccessPorts: 48, totalUplinkPorts: 4, poeCapable: true,
  vsf: VSF_M, capabilities: FULL_CAP,
  compatibilityRules: compat('aruba-cx-6300m-48sr5-poe-jl659a', '10.14.0001'),
  evidenceIds: ['ARUBA-EVD-RN-1013-1050', ...EVD_1012],
  notes: 'JL659A: 48-port Smart Rate Class 6 PoE and 4-port SFP56 Switch. Minimum AOS-CX 10.14.0001.',
}

// JL660A — Aruba 6300M 24-port HPE Smart Rate 1/2.5/5GbE Class 6 PoE and 4-port SFP56 Switch, min: 10.04.3000
export const CX6300M_24SR5_POE: SwitchHardware = {
  id: 'aruba-cx-6300m-24sr5-poe-jl660a', vendor: 'hpe_aruba', series: 'CX 6300',
  marketingModel: 'Aruba 6300M 24-port HPE Smart Rate 1/2.5/5GbE Class 6 PoE and 4-port SFP56 Switch',
  model: 'CX 6300M 24SR5 CL6 PoE 4SFP56',
  hardwareVariant: 'Modular uplink (M) — Smart Rate PoE',
  productNumber: 'JL660A',
  minimumVersion: '10.04.3000',
  minimumVersionStatus: 'UNVERIFIED',
  ports: [...smartRate(1, 24, '802.3bt Class 6'), ...sfp56(25, 4)],
  totalAccessPorts: 24, totalUplinkPorts: 4, poeCapable: true,
  vsf: VSF_M, capabilities: FULL_CAP,
  compatibilityRules: compat('aruba-cx-6300m-24sr5-poe-jl660a', '10.04.3000'),
  evidenceIds: EVD_1012,
  notes: 'JL660A: 24-port Smart Rate Class 6 PoE and 4-port SFP56 Switch. Minimum AOS-CX 10.04.3000.',
}

// JL661A — Aruba 6300M 48-port 1GbE Class 4 PoE and 4-port SFP56 Switch, min: 10.04.3000
export const CX6300M_48G_POE: SwitchHardware = {
  id: 'aruba-cx-6300m-48g-poe-jl661a', vendor: 'hpe_aruba', series: 'CX 6300',
  marketingModel: 'Aruba 6300M 48-port 1GbE Class 4 PoE and 4-port SFP56 Switch',
  model: 'CX 6300M 48G CL4 PoE 4SFP56',
  hardwareVariant: 'Modular uplink (M) — 1GbE PoE',
  productNumber: 'JL661A',
  minimumVersion: '10.04.3000',
  minimumVersionStatus: 'UNVERIFIED',
  ports: [...rj45(1, 48, true, '802.3at Class 4'), ...sfp56(49, 4)],
  totalAccessPorts: 48, totalUplinkPorts: 4, poeCapable: true,
  vsf: VSF_M, capabilities: FULL_CAP,
  compatibilityRules: compat('aruba-cx-6300m-48g-poe-jl661a', '10.04.3000'),
  evidenceIds: EVD_1012,
  notes: 'JL661A: 48-port 1GbE Class 4 PoE and 4-port SFP56 Switch. Minimum AOS-CX 10.04.3000.',
}

// JL662A — Aruba 6300M 24-port 1GbE Class 4 PoE and 4-port SFP56 Switch, min: 10.04.3000
export const CX6300M_24G_POE: SwitchHardware = {
  id: 'aruba-cx-6300m-24g-poe-jl662a', vendor: 'hpe_aruba', series: 'CX 6300',
  marketingModel: 'Aruba 6300M 24-port 1GbE Class 4 PoE and 4-port SFP56 Switch',
  model: 'CX 6300M 24G CL4 PoE 4SFP56',
  hardwareVariant: 'Modular uplink (M) — 1GbE PoE',
  productNumber: 'JL662A',
  minimumVersion: '10.04.3000',
  minimumVersionStatus: 'UNVERIFIED',
  ports: [...rj45(1, 24, true, '802.3at Class 4'), ...sfp56(25, 4)],
  totalAccessPorts: 24, totalUplinkPorts: 4, poeCapable: true,
  vsf: VSF_M, capabilities: FULL_CAP,
  compatibilityRules: compat('aruba-cx-6300m-24g-poe-jl662a', '10.04.3000'),
  evidenceIds: EVD_1012,
  notes: 'JL662A: 24-port 1GbE Class 4 PoE and 4-port SFP56 Switch. Minimum AOS-CX 10.04.3000.',
}

// JL663A — Aruba 6300M 48-port 1GbE and 4-port SFP56 Switch, min: 10.04.3000
export const CX6300M_48G_NONPOE: SwitchHardware = {
  id: 'aruba-cx-6300m-48g-jl663a', vendor: 'hpe_aruba', series: 'CX 6300',
  marketingModel: 'Aruba 6300M 48-port 1GbE and 4-port SFP56 Switch',
  model: 'CX 6300M 48G 4SFP56',
  hardwareVariant: 'Modular uplink (M) — 1GbE',
  productNumber: 'JL663A',
  minimumVersion: '10.04.3000',
  minimumVersionStatus: 'UNVERIFIED',
  ports: [...rj45(1, 48, false), ...sfp56(49, 4)],
  totalAccessPorts: 48, totalUplinkPorts: 4, poeCapable: false,
  vsf: VSF_M, capabilities: FULL_CAP,
  compatibilityRules: compat('aruba-cx-6300m-48g-jl663a', '10.04.3000'),
  evidenceIds: EVD_1012,
  notes: 'JL663A: 48-port 1GbE and 4-port SFP56 Switch. Minimum AOS-CX 10.04.3000.',
}

// JL664A — Aruba 6300M 24-port 1GbE and 4-port SFP56 Switch, min: 10.04.0001
export const CX6300M_24G_NONPOE: SwitchHardware = {
  id: 'aruba-cx-6300m-24g-jl664a', vendor: 'hpe_aruba', series: 'CX 6300',
  marketingModel: 'Aruba 6300M 24-port 1GbE and 4-port SFP56 Switch',
  model: 'CX 6300M 24G 4SFP56',
  hardwareVariant: 'Modular uplink (M) — 1GbE',
  productNumber: 'JL664A',
  minimumVersion: '10.04.0001',
  minimumVersionStatus: 'UNVERIFIED',
  ports: [...rj45(1, 24, false), ...sfp56(25, 4)],
  totalAccessPorts: 24, totalUplinkPorts: 4, poeCapable: false,
  vsf: VSF_M, capabilities: FULL_CAP,
  compatibilityRules: compat('aruba-cx-6300m-24g-jl664a', '10.04.0001'),
  evidenceIds: EVD_1012,
  notes: 'JL664A: 24-port 1GbE and 4-port SFP56 Switch. Minimum AOS-CX 10.04.0001.',
}

export const CX6300_MODELS: SwitchHardware[] = [
  CX6300M_24SFP,
  CX6300M_48SR5_POE,
  CX6300M_24SR5_POE,
  CX6300M_48G_POE,
  CX6300M_24G_POE,
  CX6300M_48G_NONPOE,
  CX6300M_24G_NONPOE,
]
