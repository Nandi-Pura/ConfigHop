// Switch catalog data model — vendor-neutral, strongly typed.
// Mirror of backend confighop_core patterns adapted for frontend TypeScript.

export type SwitchVendor = 'cisco' | 'hpe_aruba' | 'juniper'

export type HardwareRole = 'fixed-switch' | 'chassis' | 'management-module' | 'line-card'

export type PortType = 'RJ45' | 'SFP' | 'SFP+' | 'SFP28' | 'SFP56' | 'QSFP+' | 'QSFP28' | 'QSFP-DD' | 'UNKNOWN'
export type PortRole = 'access' | 'uplink' | 'flexible' | 'management' | 'stacking'
export type PortSpeed = '10M' | '100M' | '1G' | '2.5G' | '5G' | '10G' | '25G' | '40G' | '100G' | '400G'

export interface SwitchPortDefinition {
  id: string          // e.g. "1/1/1", "1/1/49"
  type: PortType
  supportedSpeeds: PortSpeed[]
  poe: boolean        // true = PoE capable on this port
  poeStandard?: string // e.g. "802.3at", "802.3bt", UNKNOWN if unverified
  role: PortRole
  sfpRequired?: boolean
  notes?: string
}

export type OsReleaseType = 'LSR' | 'SSR' | 'UNKNOWN'
export type LifecycleStatus = 'ACTIVE' | 'EXPIRING_SOON' | 'END_OF_SUPPORT' | 'UNKNOWN'

/**
 * Evidence tier for lifecycle purposes.
 * 'official' = release-notes or official-documentation → can drive ACTIVE.
 * 'vendor-forum' = Airheads/community announcements → max REVIEW_REQUIRED for lifecycle.
 */
export type EvidenceTier = 'official' | 'vendor-forum' | 'unverified'

export interface OsReleaseBound {
  /** ISO date (YYYY-MM-DD) of this bound */
  date: string
  /** Evidence IDs that establish this bound */
  evidenceIds: string[]
  /** Reason/derivation for this bound value */
  reason: string
  /** Tier of the strongest evidence behind this bound */
  tier: EvidenceTier
}

export interface SwitchOsRelease {
  id: string              // e.g. "aos-cx-10.13"
  vendor: SwitchVendor
  product: string         // e.g. "AOS-CX"
  train: string           // e.g. "10.13"
  exactVersion?: string   // e.g. "10.13.1000" if known
  releaseType: OsReleaseType
  /** Earliest confirmed release date with evidence. Absent = unverified. */
  initialReleaseEarliest?: OsReleaseBound
  /** Latest confirmed release date with evidence. Absent = no upper bound known. */
  initialReleaseLatest?: OsReleaseBound
  endOfSupportDate?: string    // ISO date if known
  lifecycleStatus: LifecycleStatus
  evidenceIds: string[]
  notes?: string
}

export type CompatibilityStatus = 'READY' | 'REVIEW_REQUIRED' | 'BLOCKED' | 'UNKNOWN'

export interface SwitchCompatibility {
  hardwareId: string
  osId: string
  status: CompatibilityStatus
  reason: string
  minimumVersion?: string  // e.g. "10.16.1006" — if a floor exists within the train
  evidenceIds: string[]
}

export type CapabilitySupport = 'SUPPORTED' | 'UNSUPPORTED' | 'UNKNOWN' | 'VERSION_DEPENDENT'

export interface SwitchCapability {
  vlan: CapabilitySupport
  accessVlan: CapabilitySupport
  voiceVlan: CapabilitySupport
  trunk: CapabilitySupport
  nativeVlan: CapabilitySupport
  lacp: CapabilitySupport
  lag: CapabilitySupport
  svi: CapabilitySupport
  staticRouting: CapabilitySupport
  dynamicRouting: CapabilitySupport  // e.g. OSPF, BGP
  stp: CapabilitySupport
  acl: CapabilitySupport
  vrf: CapabilitySupport
  vsf: CapabilitySupport
  qos: CapabilitySupport
  dhcpRelay: CapabilitySupport
  lldp: CapabilitySupport
  management: CapabilitySupport
  notes?: string
}

export interface SwitchVsfConfig {
  /** Use vsfStatus for semantic clarity; supported is derived from it for backward compat */
  supported: boolean
  /** Semantic status — UNKNOWN ≠ UNSUPPORTED */
  vsfStatus: CapabilitySupport
  technology?: 'VSF' | 'IRF' | 'STACK' | 'UNKNOWN'
  maxMembers?: number         // omit if not verified from docs
  stackingPorts?: string[]    // port IDs used for stacking, if applicable
  supportedOsTrains?: string[] // trains that support VSF on this hardware
  evidenceIds: string[]
  notes?: string
}

export interface SwitchHardware {
  id: string               // e.g. "aruba-cx-6300m-48g-jl658a"
  vendor: SwitchVendor
  series: string           // e.g. "CX 6300"
  marketingModel: string   // e.g. "Aruba CX 6300M 48G"
  model?: string           // marketingModel alias for backward compatibility with SwitchPlatform
  hardwareVariant?: string // e.g. "Modular uplink (M)" vs "Fixed (F)"
  hardwareRole?: HardwareRole // 'fixed-switch' | 'chassis' | 'management-module' | 'line-card'
  productNumber: string    // e.g. "JL658A" — UNKNOWN if unverified
  minimumVersion?: string | null  // e.g. "10.04.3000" — minimum supported AOS-CX version from release notes; null if no floor according to source, 'UNVERIFIED' if unknown
  minimumVersionStatus?: 'VERIFIED' | 'UNVERIFIED'
  ports: SwitchPortDefinition[]
  totalAccessPorts: number
  totalUplinkPorts: number
  poeCapable: boolean
  poeBudgetWatts?: number   // total PoE budget, UNKNOWN if unverified
  vsf: SwitchVsfConfig
  capabilities: SwitchCapability
  /** Explicit compatibility rules for OS releases. Only listed OS IDs are considered. */
  compatibilityRules: SwitchCompatibility[]
  evidenceIds: string[]
  notes?: string
}

// What the UI works with after hardware + OS selection
export interface SwitchPlatformSelection {
  hardware: SwitchHardware
  os: SwitchOsRelease
  compatibility: SwitchCompatibility
}

// Lightweight evidence — mirrors backend EvidenceRecord
export interface SwitchEvidence {
  id: string
  vendor: SwitchVendor | 'generic'
  sourceType: 'official-documentation' | 'release-notes' | 'product-bulletin' | 'datasheet' | 'compatibility-matrix' | 'vendor-forum' | 'unverified'
  url: string
  title: string
  checkedAt: string  // ISO date
  claims: string[]
}
