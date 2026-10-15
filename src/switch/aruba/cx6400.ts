// HPE Aruba CX 6400 Series hardware catalog.
// Modular chassis switches. Core/aggregation tier.
// Known variants: CX 6405 (5-slot chassis), CX 6410 (10-slot chassis)
// Line cards are modular — port counts depend on installed modules.
// TODO: Exact SKUs and line card options require official CX 6400 datasheet verification.
// ponytail: line card models, slot counts, speed options — add from official datasheet

import type { SwitchHardware, SwitchPortDefinition, SwitchCapability, SwitchVsfConfig, SwitchCompatibility } from '../types.ts'

const RN_1013_1050 = 'ARUBA-EVD-RN-1013-1050'
const EVIDENCE = [RN_1013_1050, 'ARUBA-EVD-CX6400-CHASSIS']

const CAP: SwitchCapability = {
  vlan: 'SUPPORTED', accessVlan: 'SUPPORTED', voiceVlan: 'SUPPORTED',
  trunk: 'SUPPORTED', nativeVlan: 'SUPPORTED', lacp: 'SUPPORTED', lag: 'SUPPORTED',
  svi: 'SUPPORTED', staticRouting: 'SUPPORTED', dynamicRouting: 'UNKNOWN',
  stp: 'SUPPORTED', acl: 'SUPPORTED', vrf: 'UNKNOWN', vsf: 'UNKNOWN',
  qos: 'UNKNOWN', dhcpRelay: 'SUPPORTED', lldp: 'SUPPORTED', management: 'SUPPORTED',
  notes: 'CX 6400 is a modular chassis. Capabilities vary by line card. Dynamic routing, VRF, QoS require official feature guide verification.',
}

// CX 6400 is a chassis — VSF applicability is UNKNOWN pending official docs
const VSF_CHASSIS: SwitchVsfConfig = {
  supported: false, vsfStatus: 'UNKNOWN', evidenceIds: EVIDENCE,
  notes: 'VSF on CX 6400 chassis: vsfStatus UNKNOWN. Verify applicability from official docs.',
}

function compat(id: string, minVersion: string): SwitchCompatibility[] {
  return [
    {
      hardwareId: id,
      osId: 'aos-cx-10.13',
      status: 'REVIEW_REQUIRED' as const,
      reason: `Train 10.13 meets minimum hardware version floor (${minVersion}); production train qualification review required.`,
      minimumVersion: minVersion,
      evidenceIds: [RN_1013_1050],
    },
    {
      hardwareId: id,
      osId: 'aos-cx-10.16',
      status: 'READY' as const,
      reason: `Supported on AOS-CX 10.16; train meets minimum floor (${minVersion}).`,
      minimumVersion: minVersion,
      evidenceIds: [RN_1013_1050],
    },
    {
      hardwareId: id,
      osId: 'aos-cx-10.17',
      status: 'REVIEW_REQUIRED' as const,
      reason: 'SSR release requires qualification review',
      minimumVersion: minVersion,
      evidenceIds: [RN_1013_1050],
    },
    {
      hardwareId: id,
      osId: 'aos-cx-10.18',
      status: 'REVIEW_REQUIRED' as const,
      reason: 'SSR release requires qualification review',
      minimumVersion: minVersion,
      evidenceIds: [RN_1013_1050],
    },
  ]
}

// CX 6400 chassis ports are defined by installed line cards.
// Placeholder: management port only — actual data ports UNKNOWN pending module selection.
const CHASSIS_MGMT_PORT: SwitchPortDefinition = {
  id: 'mgmt', type: 'RJ45', supportedSpeeds: ['100M', '1G'],
  poe: false, role: 'management',
  notes: 'Management port only. Data ports depend on installed line cards — not modelable without line card selection.',
}

export const CX6405: SwitchHardware = {
  id: 'aruba-cx-6405-r0x26a', vendor: 'hpe_aruba', series: 'CX 6400',
  marketingModel: 'Aruba CX 6405 5-Slot Chassis', model: 'CX 6405', productNumber: 'R0X26A',
  hardwareRole: 'chassis',
  minimumVersion: '10.05.0021',
  ports: [CHASSIS_MGMT_PORT],
  totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF_CHASSIS, capabilities: CAP,
  compatibilityRules: compat('aruba-cx-6405-r0x26a', '10.05.0021'),
  evidenceIds: EVIDENCE,
  notes: 'R0X26A: Aruba 6405 5-slot modular chassis. Modular line card architecture; fixed data ports: 0. Minimum AOS-CX 10.05.0021. Requires management module (R0X31A v1).',
}

export const CX6410: SwitchHardware = {
  id: 'aruba-cx-6410-r0x27a', vendor: 'hpe_aruba', series: 'CX 6400',
  marketingModel: 'Aruba CX 6410 10-Slot Chassis', model: 'CX 6410', productNumber: 'R0X27A',
  hardwareRole: 'chassis',
  minimumVersion: '10.05.0001',
  ports: [CHASSIS_MGMT_PORT],
  totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF_CHASSIS, capabilities: CAP,
  compatibilityRules: compat('aruba-cx-6410-r0x27a', '10.05.0001'),
  evidenceIds: EVIDENCE,
  notes: 'R0X27A: Aruba 6410 10-slot modular chassis. Modular line card architecture; fixed data ports: 0. Minimum AOS-CX 10.05.0001. Requires management module (R0X31A v1).',
}

export const CX6400_V2: SwitchHardware = {
  id: 'aruba-cx-6400-mgmt-v2-jl741a', vendor: 'hpe_aruba', series: 'CX 6400',
  marketingModel: 'Aruba 6410 96-port 1GbE Class 4 PoE and 4-port SFP56 Switch',
  model: 'Aruba 6410 96-port 1GbE Class 4 PoE and 4-port SFP56 Switch',
  productNumber: 'JL741A',
  hardwareRole: 'chassis',
  minimumVersion: '10.05.0001',
  ports: [CHASSIS_MGMT_PORT],
  totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF_CHASSIS, capabilities: CAP,
  compatibilityRules: compat('aruba-cx-6400-mgmt-v2-jl741a', '10.05.0001'),
  evidenceIds: EVIDENCE,
  notes: 'JL741A: Aruba 6410 96-port 1GbE Class 4 PoE and 4-port SFP56 Switch chassis bundle. Minimum AOS-CX 10.05.0001.',
}

export const CX6400_MGMT_V1: SwitchHardware = {
  id: 'aruba-cx-6400-mgmt-v1-r0x31a', vendor: 'hpe_aruba', series: 'CX 6400',
  marketingModel: 'Aruba CX 6400 Management Module v1 (R0X31A)', model: 'Aruba CX 6400 Management Module v1', productNumber: 'R0X31A',
  hardwareRole: 'management-module',
  minimumVersion: '10.04.1000',
  ports: [CHASSIS_MGMT_PORT],
  totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF_CHASSIS, capabilities: CAP,
  compatibilityRules: compat('aruba-cx-6400-mgmt-v1-r0x31a', '10.04.1000'),
  evidenceIds: EVIDENCE,
  notes: 'R0X31A: Aruba CX 6400 Management Module v1 for CX 6405/6410 modular chassis. Minimum AOS-CX 10.04.1000. NOT A STANDALONE SWITCH.',
}

export const CX6400_MODELS: SwitchHardware[] = [CX6405, CX6410, CX6400_MGMT_V1, CX6400_V2]
