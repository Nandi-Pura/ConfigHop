export type Domain = 'Firewall' | 'Switch'
export type DataMode = 'BACKEND' | 'MOCK'
export type ConversionState = 'EXACT' | 'EQUIVALENT' | 'TRANSFORMED' | 'MANUAL_ACTION_REQUIRED' | 'UNSUPPORTED'
export type MigrationStatus = 'READY' | 'REVIEW_REQUIRED' | 'BLOCKED'
export type PlatformSelection = { domain: Domain; vendor: string; family: string; model: string; softwareProduct: string; softwareVersion: string; dataMode: DataMode }

const firewall = {
  'Palo Alto Networks': { family: 'PA Series', models: ['PA-3410', 'PA-5220', 'PA-5410'], softwareProduct: 'PAN-OS', versions: ['10.2', '11.0', '11.1'] },
  Fortinet: { family: 'FortiGate', models: ['FortiGate 100F', 'FortiGate 200F', 'FortiGate 600F'], softwareProduct: 'FortiOS', versions: ['7.2', '7.4'] },
  'Juniper Networks': { family: 'SRX', models: ['SRX345', 'SRX1500', 'SRX4100'], softwareProduct: 'Junos OS', versions: ['22.4R3', '23.4R1'] },
}
const sw = {
  Cisco: { family: 'Catalyst 9300 Series', models: ['C9200-48P', 'C9300-48P', 'C9407R'], softwareProduct: 'IOS-XE', versions: ['17.9', '17.12'] },
  'HPE Aruba Networking': { family: 'CX 6300 Series', models: ['CX 6100 48G', 'CX 6200F 48G', 'CX 6300M 48G', 'CX 6405'], softwareProduct: 'AOS-CX', versions: ['10.13', '10.15'] },
  'Juniper Networks': { family: 'EX Series', models: ['EX3400-48P', 'EX4100-48P', 'EX4400-48P', 'EX4650-48Y'], softwareProduct: 'Junos OS', versions: ['22.4R3', '23.4R1'] },
  Huawei: { family: 'CloudEngine', models: ['CloudEngine S5735', 'CloudEngine S6730-H', 'CloudEngine S12700E'], softwareProduct: 'VRP', versions: ['V200R023', 'V600R023'] },
}
export const platformCatalog = { Firewall: firewall, Switch: sw }
export const vendors = (domain: Domain) => Object.keys(platformCatalog[domain])
export function platform(domain: Domain, vendor: string, model?: string, version?: string): PlatformSelection {
  const entry = (platformCatalog[domain] as Record<string, { family: string; models: string[]; softwareProduct: string; versions: string[] }>)[vendor]
  if (!entry) throw new Error(`Unknown ${domain} vendor: ${vendor}`)
  return { domain, vendor, family: entry.family, model: model && entry.models.includes(model) ? model : entry.models[0], softwareProduct: entry.softwareProduct, softwareVersion: version && entry.versions.includes(version) ? version : entry.versions[0], dataMode: 'MOCK' }
}
export function dataMode(source: PlatformSelection, target: PlatformSelection): DataMode { return source.domain === 'Firewall' && target.domain === 'Firewall' && source.vendor === 'Palo Alto Networks' && target.vendor === 'Palo Alto Networks' ? 'BACKEND' : 'MOCK' }
export const migrationMode = (source: PlatformSelection, target: PlatformSelection) => source.vendor === target.vendor ? 'SAME_VENDOR' : 'CROSS_VENDOR'
export const firewallSource = platform('Firewall', 'Palo Alto Networks', 'PA-5220', '11.1')
export const firewallTarget = platform('Firewall', 'Fortinet', 'FortiGate 200F', '7.4')
export const switchSourcePlatform = platform('Switch', 'Cisco', 'C9300-48P', '17.12')
export const switchTargetPlatform = platform('Switch', 'HPE Aruba Networking', 'CX 6300M 48G', '10.15')
export const semanticTabs = { Firewall: ['Objects', 'Policies', 'NAT', 'Routing', 'Security Services', 'Unsupported'], Switch: ['VLANs', 'LAGs', 'Layer 2', 'STP', 'SVIs / Layer 3', 'Routing', 'ACLs', 'Unsupported'] } as const
export const resultTabs = ['Overview', 'Semantic Changes', 'Resource Mapping', 'Migration Plan', 'Candidate Configuration', 'Raw Comparison', 'Findings', 'Evidence'] as const
