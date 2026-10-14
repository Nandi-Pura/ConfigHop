// HPE Aruba CX 6200 Series hardware catalog.
// Evidence source: Aruba Central AOS-CX Switch Stacking Support Table (ARUBA-EVD-VSF-CENTRAL / ARUBA-EVD-CX6200-VSF).
//
// Recovered SKUs from official Aruba documentation:
//   JL724A, JL725A, JL726A, JL727A, JL728A
//
// VSF stacking: SUPPORTED up to 8 stack members (maxMembers: 8), minimum AOS-CX 10.05.0060.
// Hardware ports: ports array empty / totalAccessPorts: 0 (not fabricated) until official datasheet specs per SKU verified.

import type { SwitchHardware, SwitchCapability, SwitchVsfConfig, SwitchCompatibility } from '../types.ts'

const EVIDENCE = ['ARUBA-EVD-CX6200-VSF', 'ARUBA-EVD-VSF-CENTRAL']
const MIN_VER = '10.05.0060'

const CAP: SwitchCapability = {
  vlan: 'SUPPORTED', accessVlan: 'SUPPORTED', voiceVlan: 'SUPPORTED',
  trunk: 'SUPPORTED', nativeVlan: 'SUPPORTED', lacp: 'SUPPORTED', lag: 'SUPPORTED',
  svi: 'SUPPORTED', staticRouting: 'SUPPORTED', dynamicRouting: 'UNKNOWN',
  stp: 'SUPPORTED', acl: 'SUPPORTED', vrf: 'UNKNOWN', vsf: 'SUPPORTED',
  qos: 'UNKNOWN', dhcpRelay: 'SUPPORTED', lldp: 'SUPPORTED', management: 'SUPPORTED',
  notes: 'CX 6200 campus access switch. VSF SUPPORTED up to 8 members. Dynamic routing, VRF, QoS require feature guide verification.',
}

// VSF: SUPPORTED up to 8 members per official Aruba Central VSF documentation
const VSF: SwitchVsfConfig = {
  supported: true,
  vsfStatus: 'SUPPORTED',
  technology: 'VSF',
  maxMembers: 8,
  evidenceIds: EVIDENCE,
  notes: 'VSF on CX 6200 Series: SUPPORTED up to 8 stack members per official Aruba documentation. Minimum version 10.05.0060.',
}

function compat(id: string): SwitchCompatibility[] {
  return ['aos-cx-10.13', 'aos-cx-10.16', 'aos-cx-10.17', 'aos-cx-10.18'].map((osId) => ({
    hardwareId: id, osId, status: 'REVIEW_REQUIRED' as const,
    reason: `CX 6200 minimum software ${MIN_VER} satisfies ${osId.replace('aos-cx-', '')} floor; train qualification review required.`,
    minimumVersion: MIN_VER, evidenceIds: EVIDENCE,
  }))
}

export const CX6200_JL724A: SwitchHardware = {
  id: 'aruba-cx-6200f-jl724a', vendor: 'hpe_aruba', series: 'CX 6200',
  marketingModel: 'Aruba CX 6200F Switch (JL724A)', model: 'CX 6200F JL724A', productNumber: 'JL724A',
  minimumVersion: MIN_VER, ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6200f-jl724a'),
  evidenceIds: EVIDENCE, notes: 'JL724A: Aruba CX 6200F fixed-configuration switch. VSF SUPPORTED max 8 members. Minimum version 10.05.0060.',
}

export const CX6200_JL725A: SwitchHardware = {
  id: 'aruba-cx-6200f-jl725a', vendor: 'hpe_aruba', series: 'CX 6200',
  marketingModel: 'Aruba CX 6200F Switch (JL725A)', model: 'CX 6200F JL725A', productNumber: 'JL725A',
  minimumVersion: MIN_VER, ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: true,
  vsf: VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6200f-jl725a'),
  evidenceIds: EVIDENCE, notes: 'JL725A: Aruba CX 6200F PoE switch. VSF SUPPORTED max 8 members. Minimum version 10.05.0060.',
}

export const CX6200_JL726A: SwitchHardware = {
  id: 'aruba-cx-6200f-jl726a', vendor: 'hpe_aruba', series: 'CX 6200',
  marketingModel: 'Aruba CX 6200F Switch (JL726A)', model: 'CX 6200F JL726A', productNumber: 'JL726A',
  minimumVersion: MIN_VER, ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6200f-jl726a'),
  evidenceIds: EVIDENCE, notes: 'JL726A: Aruba CX 6200F switch. VSF SUPPORTED max 8 members. Minimum version 10.05.0060.',
}

export const CX6200_JL727A: SwitchHardware = {
  id: 'aruba-cx-6200f-jl727a', vendor: 'hpe_aruba', series: 'CX 6200',
  marketingModel: 'Aruba CX 6200F Switch (JL727A)', model: 'CX 6200F JL727A', productNumber: 'JL727A',
  minimumVersion: MIN_VER, ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: true,
  vsf: VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6200f-jl727a'),
  evidenceIds: EVIDENCE, notes: 'JL727A: Aruba CX 6200F PoE switch. VSF SUPPORTED max 8 members. Minimum version 10.05.0060.',
}

export const CX6200_JL728A: SwitchHardware = {
  id: 'aruba-cx-6200m-jl728a', vendor: 'hpe_aruba', series: 'CX 6200',
  marketingModel: 'Aruba CX 6200M Switch (JL728A)', model: 'CX 6200M JL728A', productNumber: 'JL728A',
  minimumVersion: MIN_VER, ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6200m-jl728a'),
  evidenceIds: EVIDENCE, notes: 'JL728A: Aruba CX 6200M modular-uplink switch. VSF SUPPORTED max 8 members. Minimum version 10.05.0060.',
}

export const CX6200_MODELS: SwitchHardware[] = [
  CX6200_JL724A, CX6200_JL725A, CX6200_JL726A, CX6200_JL727A, CX6200_JL728A,
]
