// HPE Aruba CX 6300L Series hardware catalog.
// Recovered SKUs from official Aruba product documentation: S3L75A, S3L76A, S3L77A.
// Detailed port layouts, minimum software versions, and VSF capability
// remain UNKNOWN pending official HPE Aruba documentation.
// Hardware ports: ports array left empty until official specs verified.

import type { SwitchHardware, SwitchCapability, SwitchVsfConfig, SwitchCompatibility } from '../types.ts'

const EVIDENCE = ['ARUBA-EVD-CX6300-1012-RN']

const CAP: SwitchCapability = {
  vlan: 'SUPPORTED', accessVlan: 'SUPPORTED', voiceVlan: 'UNKNOWN',
  trunk: 'SUPPORTED', nativeVlan: 'SUPPORTED', lacp: 'UNKNOWN', lag: 'UNKNOWN',
  svi: 'UNKNOWN', staticRouting: 'UNKNOWN', dynamicRouting: 'UNKNOWN',
  stp: 'SUPPORTED', acl: 'UNKNOWN', vrf: 'UNKNOWN', vsf: 'UNKNOWN',
  qos: 'UNKNOWN', dhcpRelay: 'UNKNOWN', lldp: 'SUPPORTED', management: 'SUPPORTED',
  notes: 'CX 6300L capabilities require official AOS-CX feature guide verification.',
}

const VSF: SwitchVsfConfig = {
  supported: false, vsfStatus: 'UNKNOWN', evidenceIds: EVIDENCE,
  notes: 'VSF on CX 6300L: vsfStatus UNKNOWN. Cannot confirm UNSUPPORTED without official docs.',
}

function compat(id: string): SwitchCompatibility[] {
  return ['aos-cx-10.13', 'aos-cx-10.16', 'aos-cx-10.17', 'aos-cx-10.18'].map((osId) => ({
    hardwareId: id, osId, status: 'UNKNOWN' as const,
    reason: `CX 6300L ↔ AOS-CX ${osId.replace('aos-cx-', '')} requires official HPE Aruba compatibility matrix confirmation.`,
    evidenceIds: EVIDENCE,
  }))
}

export const CX6300L_S3L75A: SwitchHardware = {
  id: 'aruba-cx-6300l-s3l75a', vendor: 'hpe_aruba', series: 'CX 6300L',
  marketingModel: 'Aruba CX 6300L Switch (S3L75A)', productNumber: 'S3L75A',
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6300l-s3l75a'),
  evidenceIds: EVIDENCE, notes: 'S3L75A: Aruba CX 6300L switch SKU.',
}

export const CX6300L_S3L76A: SwitchHardware = {
  id: 'aruba-cx-6300l-s3l76a', vendor: 'hpe_aruba', series: 'CX 6300L',
  marketingModel: 'Aruba CX 6300L Switch (S3L76A)', productNumber: 'S3L76A',
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: true,
  vsf: VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6300l-s3l76a'),
  evidenceIds: EVIDENCE, notes: 'S3L76A: Aruba CX 6300L switch SKU.',
}

export const CX6300L_S3L77A: SwitchHardware = {
  id: 'aruba-cx-6300l-s3l77a', vendor: 'hpe_aruba', series: 'CX 6300L',
  marketingModel: 'Aruba CX 6300L Switch (S3L77A)', productNumber: 'S3L77A',
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF, capabilities: CAP, compatibilityRules: compat('aruba-cx-6300l-s3l77a'),
  evidenceIds: EVIDENCE, notes: 'S3L77A: Aruba CX 6300L switch SKU.',
}

export const CX6300L_MODELS: SwitchHardware[] = [
  CX6300L_S3L75A, CX6300L_S3L76A, CX6300L_S3L77A,
]
