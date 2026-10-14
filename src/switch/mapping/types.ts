// Types for Cisco IOS/IOS XE to Aruba AOS-CX semantic mapping (Phase 3.3).

import type {
  SourceReference,
  Finding,
  UnparsedLine,
  AdminState,
  InterfaceRole,
  VlanRange,
  LacpMode,
  AclEntry,
} from '../intent/types.ts'
import type { SwitchHardware, SwitchOsRelease, CompatibilityStatus } from '../types.ts'

export type TargetFeatureStatus = 'READY' | 'REVIEW_REQUIRED' | 'UNSUPPORTED' | 'UNKNOWN'

export interface TraceableTargetItem {
  sourceRefs: SourceReference[]
  status: TargetFeatureStatus
  statusReason?: string
  evidenceIds?: string[]
}

// Target RADIUS server
export interface TargetRadiusServer extends TraceableTargetItem {
  id: string
  name: string
  host?: string // IPv4 / IPv6 / FQDN (omitted if unresolved)
  authPort: number
  acctPort: number
  hasSecretConfigured: boolean
  secretDeploymentRequired: boolean
  timeout?: number
  retransmit?: number
}

// Target RADIUS server group
export interface TargetRadiusGroup extends TraceableTargetItem {
  name: string
  serverNames: string[]
}

// Target AAA authentication / accounting
export interface TargetAaaConfig extends TraceableTargetItem {
  dot1xAuthenticationGroup?: string
  macAuthenticationGroup?: string
  dot1xAccounting?: {
    groupName: string
    action: string
  }
}

// Target 802.1X / MAC auth global
export interface TargetNacGlobal extends TraceableTargetItem {
  dot1xEnabled: boolean
  macAuthEnabled: boolean
  radiusDynAuthEnabled?: boolean
  radiusDynAuthClients: string[]
  radiusDynAuthPort?: number
}

// Target Interface Port Access
export interface TargetPortAccessConfig extends TraceableTargetItem {
  targetInterfaceId: string
  sourceInterfaceId: string
  dot1xEnabled: boolean
  macAuthEnabled: boolean
  securityViolationAction?: 'shutdown' | 'notify' | 'unknown'
  clientLimit?: number
  reauthEnabled?: boolean
  reauthPeriod?: number
  cachedReauthEnabled?: boolean
  openAuthentication?: boolean
  dynamicVlanAllowed: boolean
  durConfigured: boolean
  durPolicyDependency?: string
  staticAclApplied?: string
}

// Target VLAN
export interface TargetVlanConfig extends TraceableTargetItem {
  vlanId: number
  name?: string
  description?: string
  adminState?: AdminState
}

// Target Interface
export interface TargetInterfaceConfig extends TraceableTargetItem {
  targetInterfaceId: string
  sourceInterfaceId: string
  description?: string
  adminState: AdminState
  role: InterfaceRole
  accessVlan?: number
  voiceVlan?: number
  trunkNativeVlan?: number
  trunkAllowedVlans?: VlanRange[]
  lagId?: string
  edgePort?: boolean
  portAccess?: TargetPortAccessConfig
}

// Target LAG
export interface TargetLagConfig extends TraceableTargetItem {
  lagId: string
  mode: LacpMode
  adminState: AdminState
  memberInterfaces: string[]
  trunkAllowedVlans?: VlanRange[]
}

// Target SVI
export interface TargetSviConfig extends TraceableTargetItem {
  vlanId: number
  ipAddress?: string
  description?: string
}

// Target ACL
export interface TargetAclConfig extends TraceableTargetItem {
  name: string
  aclType: string
  canNormalize: boolean
  rulesCount: number
  entries: AclEntry[]
}

// Target VRF
export interface TargetVrfConfig extends TraceableTargetItem {
  name: string
}

// Target STP
export interface TargetStpConfig extends TraceableTargetItem {
  mode: 'mstp' | 'rpvst' | 'unknown'
}

// Target VSF
export interface TargetVsfConfig extends TraceableTargetItem {
  enabled: boolean
  topologySupport: CompatibilityStatus
  notes?: string
}

// Target System / Management
export interface TargetSystemConfig extends TraceableTargetItem {
  hostname?: string
  dnsServers: string[]
  ntpServers: string[]
}

export interface TargetAosCxIntent {
  targetPlatform: {
    hardwareId: string
    hardwareModel: string
    productNumber: string
    osTrain: string
    osId: string
    compatibilityStatus: CompatibilityStatus
  }
  system?: TargetSystemConfig
  vlans: TargetVlanConfig[]
  interfaces: TargetInterfaceConfig[]
  lags: TargetLagConfig[]
  svis: TargetSviConfig[]
  acls: TargetAclConfig[]
  vrfs: TargetVrfConfig[]
  stp?: TargetStpConfig
  vsf?: TargetVsfConfig
  nac?: {
    radiusServers: TargetRadiusServer[]
    radiusGroups: TargetRadiusGroup[]
    aaa: TargetAaaConfig
    global: TargetNacGlobal
  }
}

export interface MissingDependency {
  id: string
  domain: 'CLEARPASS' | 'NETWORK' | 'CREDENTIAL' | 'TOPOLOGY'
  title: string
  details: string
  sourceRef?: SourceReference
}

export interface MappingCoverageSummary {
  totalSourceItems: number
  mappedItems: number
  readyCount: number
  reviewRequiredCount: number
  unsupportedCount: number
  unknownCount: number
  coveragePercent: number
}

export interface SemanticMappingResult {
  targetIntent: TargetAosCxIntent
  findings: Finding[]
  unparsedLines: UnparsedLine[]
  missingDependencies: MissingDependency[]
  coverage: MappingCoverageSummary
}
