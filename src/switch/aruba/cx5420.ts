// HPE Aruba CX 5420 Series hardware catalog.
// Product topology and SKUs unverified pending official HPE Aruba documentation.
// Hardware ports are NOT fabricated with Array.from; ports array left empty until official specs verified.

import type { SwitchHardware, SwitchCapability, SwitchVsfConfig } from '../types.ts'

const EVIDENCE = ['ARUBA-CX5420-DATASHEET-TODO']

const CAP: SwitchCapability = {
  vlan: 'SUPPORTED', accessVlan: 'SUPPORTED', voiceVlan: 'SUPPORTED',
  trunk: 'SUPPORTED', nativeVlan: 'SUPPORTED', lacp: 'SUPPORTED', lag: 'SUPPORTED',
  svi: 'SUPPORTED', staticRouting: 'SUPPORTED', dynamicRouting: 'UNKNOWN',
  stp: 'SUPPORTED', acl: 'SUPPORTED', vrf: 'UNKNOWN', vsf: 'UNKNOWN',
  qos: 'UNKNOWN', dhcpRelay: 'SUPPORTED', lldp: 'SUPPORTED', management: 'SUPPORTED',
  notes: 'CX 5420 capabilities require official AOS-CX feature guide verification.',
}

const VSF: SwitchVsfConfig = {
  supported: false, vsfStatus: 'UNKNOWN', technology: 'UNKNOWN',
  evidenceIds: EVIDENCE,
  notes: 'VSF on CX 5420: vsfStatus UNKNOWN. Requires official documentation.',
}

export const CX5420F: SwitchHardware = {
  id: 'aruba-cx-5420f-sku-unknown', vendor: 'hpe_aruba', series: 'CX 5420',
  marketingModel: 'Aruba CX 5420F', productNumber: 'UNKNOWN',
  minimumVersion: 'UNVERIFIED',
  minimumVersionStatus: 'UNVERIFIED',
  ports: [],
  totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF, capabilities: CAP,
  compatibilityRules: [],
  evidenceIds: EVIDENCE,
  notes: 'CX 5420F port layout and SKU unverified pending official HPE Aruba datasheet. Ports not fabricated.',
}

export const CX5420_MODELS: SwitchHardware[] = [CX5420F]
