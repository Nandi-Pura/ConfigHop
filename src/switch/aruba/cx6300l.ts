// HPE Aruba CX 6300L Series hardware catalog.
// Recovered SKUs from official Aruba product documentation: S3L75A, S3L76A, S3L77A.
// Detailed port layouts, minimum software versions, and VSF capability
// remain UNKNOWN pending official HPE Aruba documentation.
// Hardware ports: ports array left empty until official specs verified.

import type { SwitchHardware, SwitchCapability, SwitchVsfConfig } from '../types.ts'

const EVIDENCE = ['ARUBA-EVD-RN-1013-1050', 'ARUBA-EVD-CX6300-1012-RN']
const MIN_VER = '10.14.0006'

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

export const CX6300L_S3L75A: SwitchHardware = {
  id: 'aruba-cx-6300l-s3l75a', vendor: 'hpe_aruba', series: 'CX 6300L',
  marketingModel: 'Aruba CX 6300L Switch (S3L75A)', productNumber: 'S3L75A',
  minimumVersion: MIN_VER,
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF, capabilities: CAP, compatibilityRules: [],
  evidenceIds: EVIDENCE, notes: `S3L75A: Aruba CX 6300L switch SKU. Minimum AOS-CX ${MIN_VER}.`,
}

export const CX6300L_S3L76A: SwitchHardware = {
  id: 'aruba-cx-6300l-s3l76a', vendor: 'hpe_aruba', series: 'CX 6300L',
  marketingModel: 'Aruba CX 6300L Switch (S3L76A)', productNumber: 'S3L76A',
  minimumVersion: MIN_VER,
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: true,
  vsf: VSF, capabilities: CAP, compatibilityRules: [],
  evidenceIds: EVIDENCE, notes: `S3L76A: Aruba CX 6300L switch SKU. Minimum AOS-CX ${MIN_VER}.`,
}

export const CX6300L_S3L77A: SwitchHardware = {
  id: 'aruba-cx-6300l-s3l77a', vendor: 'hpe_aruba', series: 'CX 6300L',
  marketingModel: 'Aruba CX 6300L Switch (S3L77A)', productNumber: 'S3L77A',
  minimumVersion: MIN_VER,
  ports: [], totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF, capabilities: CAP, compatibilityRules: [],
  evidenceIds: EVIDENCE, notes: `S3L77A: Aruba CX 6300L switch SKU. Minimum AOS-CX ${MIN_VER}.`,
}

export const CX6300L_MODELS: SwitchHardware[] = [
  CX6300L_S3L75A, CX6300L_S3L76A, CX6300L_S3L77A,
]
