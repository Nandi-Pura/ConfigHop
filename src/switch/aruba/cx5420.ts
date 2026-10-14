// HPE Aruba CX 5420 Series hardware catalog.
// Product topology and SKUs unverified pending official HPE Aruba documentation.
// Hardware ports are NOT fabricated with Array.from; ports array left empty until official specs verified.

import type { SwitchHardware, SwitchCapability, SwitchVsfConfig, SwitchCompatibility } from '../types.ts'

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

function compat(id: string): SwitchCompatibility[] {
  return ['aos-cx-10.13', 'aos-cx-10.16', 'aos-cx-10.17', 'aos-cx-10.18'].map((osId) => ({
    hardwareId: id, osId, status: 'UNKNOWN' as const,
    reason: `CX 5420 ↔ AOS-CX ${osId.replace('aos-cx-', '')} requires official HPE Aruba compatibility matrix confirmation.`,
    evidenceIds: EVIDENCE,
  }))
}

export const CX5420F: SwitchHardware = {
  id: 'aruba-cx-5420f-sku-unknown', vendor: 'hpe_aruba', series: 'CX 5420',
  marketingModel: 'Aruba CX 5420F', productNumber: 'UNKNOWN',
  ports: [],
  totalAccessPorts: 0, totalUplinkPorts: 0, poeCapable: false,
  vsf: VSF, capabilities: CAP,
  compatibilityRules: compat('aruba-cx-5420f-sku-unknown'),
  evidenceIds: EVIDENCE,
  notes: 'CX 5420F port layout and SKU unverified pending official HPE Aruba datasheet. Ports not fabricated.',
}

export const CX5420_MODELS: SwitchHardware[] = [CX5420F]
