// HPE Aruba CX 6000 Series hardware catalog.
// Entry-level Layer 2 switch family.
// Evidence source: AOS-CX 10.12 Release Notes (ARUBA-EVD-CX6000-1012-RN).
// Recovered SKUs from official release notes: R8N85A, R8N86A, R8N87A, R8N88A, R8N89A, R9Y03A.
// VSF stacking: UNSUPPORTED (absent from official Aruba Central VSF support table).
// Hardware ports: left empty until exact port topologies per SKU are verified.

import type { SwitchHardware, SwitchCapability, SwitchVsfConfig, SwitchCompatibility } from '../types.ts'

const EVIDENCE = ['ARUBA-EVD-RN-1017-6000-6100', 'ARUBA-EVD-CX6000-1012-RN']

const CAP: SwitchCapability = {
  vlan: 'SUPPORTED', accessVlan: 'SUPPORTED', voiceVlan: 'SUPPORTED',
  trunk: 'SUPPORTED', nativeVlan: 'SUPPORTED', lacp: 'SUPPORTED', lag: 'SUPPORTED',
  svi: 'UNKNOWN', staticRouting: 'UNSUPPORTED', dynamicRouting: 'UNSUPPORTED',
  stp: 'SUPPORTED', acl: 'UNKNOWN', vrf: 'UNSUPPORTED', vsf: 'UNKNOWN',
  qos: 'UNKNOWN', dhcpRelay: 'UNKNOWN', lldp: 'SUPPORTED', management: 'SUPPORTED',
  notes: 'CX 6000 is entry-level Layer 2. Advanced routing, VRF are UNSUPPORTED. VSF is UNKNOWN (not in support table).',
}

const NO_VSF: SwitchVsfConfig = {
  supported: false, vsfStatus: 'UNKNOWN', evidenceIds: ['ARUBA-EVD-VSF-CENTRAL', ...EVIDENCE],
  notes: 'VSF on CX 6000: UNKNOWN (absent from Aruba Central AOS-CX switch stacking support table; absence does not prove non-support).',
}

function compat(id: string): SwitchCompatibility[] {
  return ['aos-cx-10.13', 'aos-cx-10.16', 'aos-cx-10.17', 'aos-cx-10.18'].map((osId) => ({
    hardwareId: id, osId, status: 'UNKNOWN' as const,
    reason: `CX 6000 entry-level platform requires official HPE Aruba train compatibility confirmation.`,
    evidenceIds: EVIDENCE,
  }))
}

export const CX6000_R8N85A: SwitchHardware = {
  id: 'aruba-cx-6000-r8n85a', vendor: 'hpe_aruba', series: 'CX 6000',
  marketingModel: 'Aruba CX 6000 Switch (R8N85A)', productNumber: 'R8N85A',
  minimumVersion: '10.11.1011',
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: NO_VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6000-r8n85a'),
  evidenceIds: EVIDENCE, notes: 'R8N85A: CX 6000 Series entry-level switch. Minimum AOS-CX 10.11.1011 (serial-dependent: 10.08.1010 untuk rentang seri lama).',
}

export const CX6000_R8N86A: SwitchHardware = {
  id: 'aruba-cx-6000-r8n86a', vendor: 'hpe_aruba', series: 'CX 6000',
  marketingModel: 'Aruba CX 6000 Switch (R8N86A)', productNumber: 'R8N86A',
  minimumVersion: '10.11.1011',
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: NO_VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6000-r8n86a'),
  evidenceIds: EVIDENCE, notes: 'R8N86A: CX 6000 Series entry-level switch. Minimum AOS-CX 10.11.1011 (serial-dependent: 10.08.1010 untuk rentang seri lama).',
}

export const CX6000_R8N87A: SwitchHardware = {
  id: 'aruba-cx-6000-r8n87a', vendor: 'hpe_aruba', series: 'CX 6000',
  marketingModel: 'Aruba CX 6000 Switch (R8N87A)', productNumber: 'R8N87A',
  minimumVersion: '10.11.1011',
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: NO_VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6000-r8n87a'),
  evidenceIds: EVIDENCE, notes: 'R8N87A: CX 6000 Series entry-level switch. Minimum AOS-CX 10.11.1011 (serial-dependent: 10.08.1010 untuk rentang seri lama).',
}

export const CX6000_R8N88A: SwitchHardware = {
  id: 'aruba-cx-6000-r8n88a', vendor: 'hpe_aruba', series: 'CX 6000',
  marketingModel: 'Aruba CX 6000 Switch (R8N88A)', productNumber: 'R8N88A',
  minimumVersion: '10.11.1011',
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: NO_VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6000-r8n88a'),
  evidenceIds: EVIDENCE, notes: 'R8N88A: CX 6000 Series entry-level switch. Minimum AOS-CX 10.11.1011 (serial-dependent: 10.08.1010 untuk rentang seri lama).',
}

export const CX6000_R8N89A: SwitchHardware = {
  id: 'aruba-cx-6000-r8n89a', vendor: 'hpe_aruba', series: 'CX 6000',
  marketingModel: 'Aruba CX 6000 Switch (R8N89A)', productNumber: 'R8N89A',
  minimumVersion: '10.11.1011',
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: true,
  vsf: NO_VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6000-r8n89a'),
  evidenceIds: EVIDENCE, notes: 'R8N89A: CX 6000 Series entry-level switch. Minimum AOS-CX 10.11.1011 (serial-dependent: 10.08.1010 untuk rentang seri lama).',
}

export const CX6000_R9Y03A: SwitchHardware = {
  id: 'aruba-cx-6000-r9y03a', vendor: 'hpe_aruba', series: 'CX 6000',
  marketingModel: 'Aruba CX 6000 Switch (R9Y03A)', productNumber: 'R9Y03A',
  minimumVersion: '10.11.1001',
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: NO_VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6000-r9y03a'),
  evidenceIds: EVIDENCE, notes: 'R9Y03A: CX 6000 Series entry-level switch. Minimum AOS-CX 10.11.1001.',
}

export const CX6000_MODELS: SwitchHardware[] = [
  CX6000_R8N85A, CX6000_R8N86A, CX6000_R8N87A,
  CX6000_R8N88A, CX6000_R8N89A, CX6000_R9Y03A,
]
