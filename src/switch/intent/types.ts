// Normalized Switch Intent — vendor-neutral configuration data model.
// Represents parsed switch configuration semantics independently of source CLI syntax.
// Schema version: 1.0.0

import type { SwitchVendor } from '../types.ts'

export const INTENT_SCHEMA_VERSION = '1.0.0'

// ===== ROOT INTENT CONTRACT =====

export interface NormalizedSwitchIntent {
  schemaVersion: string

  // Source platform information
  source: SourcePlatform

  // Parsed configuration semantics
  system?: SystemConfig
  vlans: VlanConfig[]
  interfaces: InterfaceConfig[]
  lags: LagConfig[]
  svis: SviConfig[]
  routing?: RoutingConfig
  acls: AclConfig[]
  vrfs: VrfConfig[]
  stp?: StpConfig
  vsf?: VsfConfig

  // NAC configuration
  nac?: NacConfig

  // Extension mechanism for features not yet modeled
  extensions?: Record<string, unknown>

  // Parse coverage and diagnostics
  coverage: ParseCoverage
  findings: Finding[]
  unparsedLines: UnparsedLine[]
}

// ===== SOURCE PLATFORM =====

export interface SourcePlatform {
  vendor: SwitchVendor
  osFamilyName?: string          // e.g. "AOS-CX", "IOS", "IOS XE"
  osVersion?: string              // e.g. "10.13.1000"
  hardwareModel?: string          // e.g. "CX 6300M"
  hardwareSku?: string            // e.g. "JL658A"
  deviceName?: string             // Hostname from configuration
  inputFileName?: string          // Original configuration file name
  metadata?: Record<string, string>
}

// ===== SYSTEM AND MANAGEMENT =====

export interface SystemConfig {
  hostname?: string
  managementInterface?: ManagementInterface
  defaultGateway?: string
  dnsServers: string[]
  ntpServers: string[]
  sourceRefs: SourceReference[]
}

export interface ManagementInterface {
  interfaceId: string             // Source interface identifier
  ipAddress?: string
  subnetMask?: string
  sourceRefs: SourceReference[]
}

// ===== VLANS =====

export interface VlanConfig {
  vlanId: number
  name?: string
  description?: string
  adminState?: AdminState
  sourceRefs: SourceReference[]
}

// ===== INTERFACES =====

export type InterfaceRole = 'access' | 'trunk' | 'routed' | 'unknown'
export type AdminState = 'up' | 'down' | 'unknown'
export type DuplexMode = 'full' | 'half' | 'auto' | 'unknown'

export interface InterfaceConfig {
  // Source interface identifier (NOT target interface identifier)
  sourceInterfaceId: string       // e.g. "1/1/1", "GigabitEthernet0/1"

  role: InterfaceRole
  adminState: AdminState
  description?: string

  // Layer 2 configuration
  accessVlan?: number
  voiceVlan?: number
  trunkNativeVlan?: number
  trunkAllowedVlans?: VlanRange[]

  // Physical attributes
  speed?: string                  // e.g. "1000", "10000", "auto"
  duplex?: DuplexMode
  mtu?: number

  // LAG membership
  lagId?: string                  // Reference to LAG sourceInterfaceId

  // Additional features
  lldpEnabled?: boolean
  dhcpRelay?: DhcpRelayConfig
  qos?: QosConfig
  poe?: PoeConfig

  // NAC/802.1X authentication
  authentication?: InterfaceAuthenticationConfig

  sourceRefs: SourceReference[]
}

export interface VlanRange {
  start: number
  end?: number                    // undefined = single VLAN
}

export interface DhcpRelayConfig {
  enabled: boolean
  servers: string[]
  sourceRefs: SourceReference[]
}

export interface QosConfig {
  trust?: string                  // e.g. "cos", "dscp"
  priority?: number
  sourceRefs: SourceReference[]
}

export interface PoeConfig {
  enabled: boolean
  priority?: string               // e.g. "low", "high", "critical"
  maxPower?: number               // Watts
  sourceRefs: SourceReference[]
}

// ===== LAG/LACP =====

export type LacpMode = 'active' | 'passive' | 'static' | 'unknown'

export interface LagConfig {
  sourceInterfaceId: string       // LAG identifier, e.g. "lag1", "Port-channel1"
  memberInterfaces: string[]      // Source interface IDs
  lacpMode: LacpMode
  description?: string
  adminState: AdminState

  // Layer 2 configuration (when LAG acts as trunk/access)
  role?: InterfaceRole
  accessVlan?: number
  trunkNativeVlan?: number
  trunkAllowedVlans?: VlanRange[]

  sourceRefs: SourceReference[]
}

// ===== SVI AND LAYER 3 INTERFACES =====

export interface SviConfig {
  vlanId: number
  ipAddresses: IpAddress[]
  adminState: AdminState
  description?: string
  vrfName?: string

  // Additional features
  dhcpRelay?: DhcpRelayConfig

  sourceRefs: SourceReference[]
}

export interface IpAddress {
  address: string
  prefixLength: number
  type?: 'primary' | 'secondary'
}

// ===== ROUTING =====

export interface RoutingConfig {
  staticRoutes: StaticRoute[]
  sourceRefs: SourceReference[]
}

export interface StaticRoute {
  destinationPrefix: string       // e.g. "0.0.0.0/0", "192.168.1.0/24"
  nextHop?: string                // Next hop IP or interface
  interface?: string              // Output interface
  adminDistance?: number
  metric?: number
  vrfName?: string
  description?: string
  sourceRefs: SourceReference[]
}

// ===== ACL AND POLICY =====

export type AclAction = 'permit' | 'deny' | 'remark'
export type AclProtocol = 'ip' | 'tcp' | 'udp' | 'icmp' | 'any' | string

export interface AclConfig {
  name: string
  aclType?: string                // e.g. "standard", "extended", "ipv4", "ipv6"
  entries: AclEntry[]             // ORDERED — preserve source ordering
  sourceRefs: SourceReference[]
}

export interface AclEntry {
  sequenceNumber?: number
  action: AclAction
  protocol?: AclProtocol
  sourceAddress?: AclAddress
  destinationAddress?: AclAddress
  sourcePorts?: PortRange[]
  destinationPorts?: PortRange[]
  flags?: string[]                // e.g. ["established", "syn", "ack"]
  remark?: string                 // For remark entries
  canNormalize: boolean           // false = entry cannot be safely normalized
  normalizationNote?: string      // Reason if canNormalize = false
  sourceRefs: SourceReference[]
}

export interface AclAddress {
  address: string                 // IP or prefix
  wildcardMask?: string           // For Cisco wildcard notation
  prefixLength?: number           // For CIDR notation
}

export interface PortRange {
  start: number
  end?: number                    // undefined = single port
}

// ===== VRF =====

export interface VrfConfig {
  name: string
  description?: string
  routeDistinguisher?: string
  interfaces: string[]            // Source interface IDs or VLAN IDs
  sourceRefs: SourceReference[]
}

// ===== STP =====

export type StpMode = 'pvst' | 'rapid-pvst' | 'mstp' | 'rstp' | 'stp' | 'unknown'

export interface StpConfig {
  mode: StpMode
  bridgePriority?: number
  instances?: StpInstance[]       // Per-VLAN or per-instance configuration
  sourceRefs: SourceReference[]
}

export interface StpInstance {
  instanceId?: number             // VLAN ID or MST instance ID
  vlans?: number[]                // VLANs in this instance
  priority?: number
  sourceRefs: SourceReference[]
}

// ===== VSF/STACKING =====

export type VsfMemberRole = 'primary' | 'secondary' | 'member' | 'unknown'

export interface VsfConfig {
  enabled: boolean
  members: VsfMember[]
  capability: VsfCapability       // Can this topology port to target?
  sourceRefs: SourceReference[]
}

export interface VsfMember {
  memberId: string
  role: VsfMemberRole
  priority?: number
  sourceRefs: SourceReference[]
}

export type VsfCapability = 'portable' | 'review-required' | 'unsupported' | 'unknown'

// ===== NAC (Network Access Control) =====

export interface NacConfig {
  radiusServers: RadiusServerConfig[]
  radiusServerGroups: RadiusServerGroupConfig[]
  aaa?: AaaConfig
  dot1x?: Dot1xGlobalConfig
  mab?: MabGlobalConfig
  coa?: CoaConfig
  sourceRefs: SourceReference[]
}

// ----- RADIUS Servers -----

export interface RadiusServerConfig {
  id: string                          // Unique identifier for references
  name?: string                       // Configured server name
  address?: string                    // IP address or hostname (undefined if missing/unresolved)
  authPort?: number                   // Authentication port (default 1812)
  acctPort?: number                   // Accounting port (default 1813)
  key: RadiusKeyStatus                // Secret status, never plaintext
  timeout?: number
  retransmit?: number
  sourceRefs: SourceReference[]
}

export interface RadiusKeyStatus {
  configured: boolean                 // true = secret exists in source config
  keyReference?: string               // Reference identifier if available (e.g., key name)
  // NEVER include plaintext secret
}

// ----- RADIUS Server Groups -----

export interface RadiusServerGroupConfig {
  name: string
  serverIds: string[]                 // References to RadiusServerConfig.id
  sourceRefs: SourceReference[]
}

// ----- AAA Configuration -----

export interface AaaConfig {
  authentication?: AaaAuthenticationConfig
  authorization?: AaaAuthorizationConfig
  accounting?: AaaAccountingConfig
  sourceRefs: SourceReference[]
}

export interface AaaAuthenticationConfig {
  defaultMethodList?: AaaMethodList
  defaultMethodLists?: Record<string, AaaMethodList>
  namedMethodLists: Record<string, AaaMethodList>
  methodLists?: AaaMethodList[]
  sourceRefs: SourceReference[]
}

export interface AaaAuthorizationConfig {
  defaultMethodList?: AaaMethodList
  defaultMethodLists?: Record<string, AaaMethodList>
  namedMethodLists: Record<string, AaaMethodList>
  methodLists?: AaaMethodList[]
  sourceRefs: SourceReference[]
}

export interface AaaAccountingConfig {
  defaultMethodList?: AaaMethodList
  defaultMethodLists?: Record<string, AaaMethodList>
  namedMethodLists: Record<string, AaaMethodList>
  methodLists?: AaaMethodList[]
  sourceRefs: SourceReference[]
}

export interface AaaMethodList {
  name?: string                       // undefined for default method list
  type?: string                       // AAA feature/type: 'login' | 'dot1x' | 'network' | 'exec' | etc.
  action?: string                     // For accounting: 'start-stop' | 'stop-only' | etc.
  methods: AaaMethod[]                // Ordered list
  sourceRefs: SourceReference[]
}

export type AaaMethod =
  | { type: 'group'; groupName: string }
  | { type: 'local' }
  | { type: 'none' }
  | { type: 'unknown'; raw: string }

// ----- 802.1X Global Configuration -----

export interface Dot1xGlobalConfig {
  enabled: boolean
  systemAuthControl?: boolean
  sourceRefs: SourceReference[]
}

// ----- MAC Authentication Bypass Global -----

export interface MabGlobalConfig {
  enabled: boolean
  sourceRefs: SourceReference[]
}

// ----- Interface Authentication -----

export interface InterfaceAuthenticationConfig {
  dot1x?: InterfaceDot1xConfig
  mab?: InterfaceMabConfig
  openAuthentication?: boolean
  portControl?: PortControlMode
  hostMode?: HostMode
  authenticationOrder?: AuthenticationMethod[]
  authenticationPriority?: AuthenticationMethod[]
  reauthentication?: ReauthenticationConfig
  violation?: ViolationAction
  maxClients?: number
  authorizationAttributes?: AuthorizationAttributes
  sourceRefs: SourceReference[]
}

export interface InterfaceDot1xConfig {
  enabled: boolean
  pae?: 'authenticator' | 'supplicant' | 'both'
  timeout?: Dot1xTimeouts
  sourceRefs: SourceReference[]
}

export interface Dot1xTimeouts {
  txPeriod?: number
  quietPeriod?: number
  serverTimeout?: number
  suppTimeout?: number
  reauthPeriod?: number
  sourceRefs: SourceReference[]
}

export interface InterfaceMabConfig {
  enabled: boolean
  sourceRefs: SourceReference[]
}

export type PortControlMode = 'auto' | 'force-authorized' | 'force-unauthorized' | 'unknown'
export type HostMode = 'single-host' | 'multi-host' | 'multi-auth' | 'multi-domain' | 'unknown'
export type AuthenticationMethod = 'dot1x' | 'mab' | 'unknown'
export type ViolationAction = 'shutdown' | 'restrict' | 'protect' | 'replace' | 'unknown'

export interface ReauthenticationConfig {
  enabled: boolean
  period?: number                     // Seconds
  sourceRefs: SourceReference[]
}

// ----- RADIUS Authorization Attributes -----

export interface AuthorizationAttributes {
  dynamicVlan?: DynamicVlanConfig
  downloadableAcl?: DownloadableAclConfig
  filterId?: FilterIdConfig
  downloadableUserRole?: DownloadableUserRoleConfig
  sourceRefs: SourceReference[]
}

export interface DynamicVlanConfig {
  enabled: boolean
  sourceRefs: SourceReference[]
}

export interface DownloadableAclConfig {
  // Cisco dACL - references ACL name returned by RADIUS
  enabled: boolean
  sourceRefs: SourceReference[]
}

export interface FilterIdConfig {
  // Filter-ID RADIUS attribute
  enabled: boolean
  sourceRefs: SourceReference[]
}

export interface DownloadableUserRoleConfig {
  // Aruba ClearPass DUR - NOT equivalent to Cisco dACL
  // Preserved as distinct semantic for migration review
  enabled: boolean
  sourceRefs: SourceReference[]
}

// ----- Change of Authorization (CoA) -----

export interface CoaConfig {
  enabled: boolean
  clientConfig?: CoaClientConfig
  serverConfig?: CoaServerConfig
  sourceRefs: SourceReference[]
}

export interface CoaClientConfig {
  serverAddresses: string[]
  port?: number
  sourceRefs: SourceReference[]
}

export interface CoaServerConfig {
  enabled: boolean
  port?: number
  clientAddresses?: string[]          // Allowed CoA clients
  sourceRefs: SourceReference[]
}


// ===== SOURCE TRACEABILITY =====

export interface SourceReference {
  configId?: string               // Input configuration identifier
  startLine: number               // One-based line number
  endLine?: number                // One-based line number (inclusive)
  originalText?: string           // Original command(s)
  context?: string                // Section name or configuration context
}

// ===== PARSE COVERAGE AND FINDINGS =====

export interface ParseCoverage {
  totalLines: number
  parsedLines: number
  unparsedLines: number
  partiallyParsedLines?: number
  coveragePercent: number         // 0-100
}

export type FindingSeverity = 'error' | 'warning' | 'info'
export type FindingCode =
  | 'UNKNOWN_COMMAND'
  | 'AMBIGUOUS_SYNTAX'
  | 'UNSUPPORTED_FEATURE'
  | 'PARSER_NOT_IMPLEMENTED'
  | 'INVALID_VALUE'
  | 'MISSING_REFERENCE'
  | 'NORMALIZATION_FAILED'
  | 'REVIEW_REQUIRED'
  | 'NAC_UNRESOLVED_RADIUS_SERVER'
  | 'NAC_UNRESOLVED_SERVER_GROUP'
  | 'NAC_SECRET_REDACTED'
  | 'NAC_MIGRATION_REVIEW_REQUIRED'
  | 'NAC_MISSING_SERVER_ADDRESS'
  | 'MAPPING_UNSUPPORTED_FEATURE'
  | 'MAPPING_SEMANTIC_DIFFERENCE'
  | 'MAPPING_DEPENDENCY_MISSING'
  | 'MAPPING_REVIEW_REQUIRED'
  | 'MAPPING_UNRESOLVED_REFERENCE'
  | 'MAPPING_UNKNOWN_COMPATIBILITY'


export interface Finding {
  code: FindingCode
  severity: FindingSeverity
  message: string
  sourceRef?: SourceReference
}

export interface UnparsedLine {
  lineNumber: number              // One-based
  text: string
  reason?: string                 // Why this line was not parsed
}

// ===== UTILITIES =====

/**
 * Create an empty normalized intent with default structure.
 */
export function createEmptyIntent(source: Partial<SourcePlatform> = {}): NormalizedSwitchIntent {
  return {
    schemaVersion: INTENT_SCHEMA_VERSION,
    source: {
      vendor: source.vendor ?? 'hpe_aruba',
      ...source,
    },
    vlans: [],
    interfaces: [],
    lags: [],
    svis: [],
    acls: [],
    vrfs: [],
    coverage: {
      totalLines: 0,
      parsedLines: 0,
      unparsedLines: 0,
      coveragePercent: 0,
    },
    findings: [],
    unparsedLines: [],
  }
}

/**
 * Create a finding with consistent structure.
 */
export function createFinding(
  code: FindingCode,
  severity: FindingSeverity,
  message: string,
  sourceRef?: SourceReference
): Finding {
  return { code, severity, message, sourceRef }
}

/**
 * Create a source reference from line number(s).
 */
export function createSourceRef(
  startLine: number,
  endLine?: number,
  originalText?: string,
  context?: string
): SourceReference {
  const ref: SourceReference = { startLine }
  if (endLine !== undefined) ref.endLine = endLine
  if (originalText !== undefined) ref.originalText = originalText
  if (context !== undefined) ref.context = context
  return ref
}

/**
 * Type guard: check if intent has valid schema version.
 */
export function isValidIntent(obj: unknown): obj is NormalizedSwitchIntent {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    'schemaVersion' in obj &&
    'source' in obj &&
    'vlans' in obj &&
    'interfaces' in obj &&
    'coverage' in obj &&
    'findings' in obj
  )
}
