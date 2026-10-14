// Cisco IOS/IOS XE to Aruba AOS-CX semantic mapping engine (Phase 3.3).

import type {
  NormalizedSwitchIntent,
  Finding,
  UnparsedLine,
  VlanConfig,
  LagConfig,
  SviConfig,
  AclConfig,
  VrfConfig,
  SystemConfig,
} from '../intent/types.ts'
import type { SwitchHardware, SwitchOsRelease } from '../types.ts'
import { evaluateCompatibility } from '../compatibility.ts'
import type {
  SemanticMappingResult,
  TargetAosCxIntent,
  TargetVlanConfig,
  TargetLagConfig,
  TargetSviConfig,
  TargetAclConfig,
  TargetVrfConfig,
  TargetSystemConfig,
  MissingDependency,
  TargetFeatureStatus,
} from './types.ts'
import { mapStp, mapVsf } from './topology.ts'
import { mapNac } from './nac.ts'
import { mapInterface } from './interface.ts'
import { calculateMappingCoverage } from './coverage.ts'

export interface MappingOptions {
  interfaceIdMapper?: (sourceId: string) => string
}

export function mapCiscoToAosCx(
  sourceIntent: NormalizedSwitchIntent,
  targetHardware: SwitchHardware,
  targetOs: SwitchOsRelease,
  options?: MappingOptions
): SemanticMappingResult {
  const platformCompat = evaluateCompatibility(targetHardware, targetOs)
  const isPlatformReady = platformCompat.status === 'READY'
  const isPlatformReview = platformCompat.status === 'REVIEW_REQUIRED'
  const defaultStatus: TargetFeatureStatus = isPlatformReady
    ? 'READY'
    : isPlatformReview
      ? 'REVIEW_REQUIRED'
      : platformCompat.status === 'BLOCKED'
        ? 'UNSUPPORTED'
        : 'UNKNOWN'

  const findings: Finding[] = [...sourceIntent.findings]
  const unparsedLines: UnparsedLine[] = [...sourceIntent.unparsedLines]
  const missingDependencies: MissingDependency[] = []

  if (platformCompat.status !== 'READY') {
    findings.push({
      code: platformCompat.status === 'UNKNOWN' ? 'MAPPING_UNKNOWN_COMPATIBILITY' : 'MAPPING_REVIEW_REQUIRED',
      severity: platformCompat.status === 'BLOCKED' ? 'error' : 'warning',
      message: `Target platform compatibility for ${targetHardware.marketingModel} on ${targetOs.product} ${targetOs.train} is ${platformCompat.status}: ${platformCompat.reason}`,
    })
  }
  for (const route of sourceIntent.routing?.staticRoutes ?? []) {
    findings.push({ code: 'MAPPING_REVIEW_REQUIRED', severity: 'warning', message: `Static route ${route.destinationPrefix} is preserved in source intent but has no AOS-CX target mapping contract.`, sourceRef: route.sourceRefs[0] })
  }
  if (sourceIntent.extensions && Object.keys(sourceIntent.extensions).length) {
    findings.push({ code: 'MAPPING_REVIEW_REQUIRED', severity: 'warning', message: `Source extensions (${Object.keys(sourceIntent.extensions).join(', ')}) have no AOS-CX target mapping contract.` })
  }

  const targetSystem = sourceIntent.system ? mapSystem(sourceIntent.system, defaultStatus) : undefined
  const targetVlans = sourceIntent.vlans.map((v) => mapVlan(v, defaultStatus))
  const targetSvis = sourceIntent.svis.map((s) => mapSvi(s, defaultStatus, sourceIntent.vlans.some((v) => v.vlanId === s.vlanId), findings))
  const targetLags = sourceIntent.lags.map((l) => mapLag(l, defaultStatus, sourceIntent.interfaces, findings))
  const targetAcls = sourceIntent.acls.map((a) => mapAcl(a, defaultStatus, findings))
  const targetVrfs = sourceIntent.vrfs.map((v) => mapVrf(v, targetHardware, defaultStatus, findings))
  const targetStp = sourceIntent.stp ? mapStp(sourceIntent.stp, defaultStatus, findings) : undefined
  const targetVsf = sourceIntent.vsf ? mapVsf(sourceIntent.vsf, targetHardware, findings) : undefined

  let nacResult: ReturnType<typeof mapNac> = {
    servers: [],
    groups: [],
    aaa: { sourceRefs: [], status: defaultStatus },
    global: { dot1xEnabled: false, macAuthEnabled: false, radiusDynAuthClients: [], sourceRefs: [], status: defaultStatus },
  }

  if (sourceIntent.nac) {
    nacResult = mapNac(sourceIntent.nac, defaultStatus, targetHardware, findings, missingDependencies)
  }

  const ifaceMap = options?.interfaceIdMapper ?? ((id: string) => id)
  const targetInterfaces = sourceIntent.interfaces.map((srcIface) =>
    mapInterface(srcIface, ifaceMap, defaultStatus, findings, missingDependencies)
  )

  const targetIntent: TargetAosCxIntent = {
    targetPlatform: {
      hardwareId: targetHardware.id,
      hardwareModel: targetHardware.marketingModel,
      productNumber: targetHardware.productNumber,
      osTrain: targetOs.train,
      osId: targetOs.id,
      compatibilityStatus: platformCompat.status,
    },
    system: targetSystem,
    vlans: targetVlans,
    interfaces: targetInterfaces,
    lags: targetLags,
    svis: targetSvis,
    acls: targetAcls,
    vrfs: targetVrfs,
    stp: targetStp,
    vsf: targetVsf,
    nac: sourceIntent.nac
      ? {
          radiusServers: nacResult.servers,
          radiusGroups: nacResult.groups,
          aaa: nacResult.aaa,
          global: nacResult.global,
        }
      : undefined,
  }

  const coverage = calculateMappingCoverage(targetIntent)

  return {
    targetIntent,
    findings,
    unparsedLines: unparsedLines.map(line => ({ ...line })),
    missingDependencies,
    coverage,
  }
}

function mapSystem(sys: SystemConfig, status: TargetFeatureStatus): TargetSystemConfig {
  return {
    hostname: sys.hostname,
    dnsServers: [...sys.dnsServers],
    ntpServers: [...sys.ntpServers],
    status,
    sourceRefs: sys.sourceRefs.map(ref => ({ ...ref })),
  }
}

function mapVlan(vlan: VlanConfig, status: TargetFeatureStatus): TargetVlanConfig {
  return {
    vlanId: vlan.vlanId,
    name: vlan.name,
    description: vlan.description,
    adminState: vlan.adminState,
    status,
    sourceRefs: vlan.sourceRefs.map(ref => ({ ...ref })),
  }
}

function mapSvi(svi: SviConfig, status: TargetFeatureStatus, vlanExists: boolean, findings: Finding[]): TargetSviConfig {
  const primary = svi.ipAddresses.find((ip) => ip.type === 'primary') || svi.ipAddresses[0]
  const ipAddress = primary ? `${primary.address}/${primary.prefixLength}` : undefined
  if (!vlanExists) {
    findings.push({ code: 'MAPPING_UNRESOLVED_REFERENCE', severity: 'warning', message: `SVI VLAN ${svi.vlanId} is not defined in the source VLAN intent.`, sourceRef: svi.sourceRefs[0] })
    status = 'REVIEW_REQUIRED'
  }
  return { vlanId: svi.vlanId, ipAddress, description: svi.description, status, sourceRefs: svi.sourceRefs.map(ref => ({ ...ref })) }
}

function mapLag(lag: LagConfig, status: TargetFeatureStatus, interfaces: NormalizedSwitchIntent['interfaces'], findings: Finding[]): TargetLagConfig {
  const members = [...lag.memberInterfaces]
  const duplicate = new Set(members).size !== members.length
  const missing = members.filter((member) => !interfaces.some((iface) => iface.sourceInterfaceId === member))
  let reason: string | undefined
  if (lag.lacpMode === 'static') reason = 'Cisco static EtherChannel is not LACP; target LACP equivalence is not established.'
  else if (lag.lacpMode === 'unknown') reason = 'Cisco LACP mode was not established from source configuration.'
  else if (lag.adminState === 'unknown') reason = 'Cisco Port-channel administrative state was not established from source configuration.'
  else if (duplicate) reason = 'Cisco LAG contains duplicate member references.'
  else if (missing.length) reason = `Cisco LAG references missing member interface(s): ${missing.join(', ')}.`
  if (reason) findings.push({ code: lag.lacpMode === 'static' ? 'MAPPING_UNSUPPORTED_FEATURE' : 'MAPPING_REVIEW_REQUIRED', severity: 'warning', message: `LAG ${lag.sourceInterfaceId}: ${reason}`, sourceRef: lag.sourceRefs[0] })
  return {
    lagId: lag.sourceInterfaceId, mode: lag.lacpMode, adminState: lag.adminState, memberInterfaces: members,
    trunkAllowedVlans: lag.trunkAllowedVlans?.map((range) => ({ ...range })),
    status: lag.lacpMode === 'static' ? 'UNSUPPORTED' : reason ? 'REVIEW_REQUIRED' : status,
    statusReason: reason, sourceRefs: lag.sourceRefs.map(ref => ({ ...ref })),
  }
}

function mapAcl(acl: AclConfig, status: TargetFeatureStatus, findings: Finding[]): TargetAclConfig {
  const hasUnnormalized = acl.entries.some((e) => !e.canNormalize)
  if (hasUnnormalized) {
    findings.push({
      code: 'MAPPING_REVIEW_REQUIRED',
      severity: 'warning',
      message: `ACL ${acl.name} contains syntax that could not be fully normalized. Review required.`,
      sourceRef: acl.sourceRefs[0],
    })
  }
  return {
    name: acl.name,
    aclType: acl.aclType ?? 'ipv4',
    canNormalize: !hasUnnormalized,
    rulesCount: acl.entries.length,
    entries: acl.entries.map((entry) => ({
      ...entry,
      sourceAddress: entry.sourceAddress ? { ...entry.sourceAddress } : undefined,
      destinationAddress: entry.destinationAddress ? { ...entry.destinationAddress } : undefined,
      sourcePorts: entry.sourcePorts?.map((port) => ({ ...port })),
      destinationPorts: entry.destinationPorts?.map((port) => ({ ...port })),
      flags: entry.flags ? [...entry.flags] : undefined,
      sourceRefs: entry.sourceRefs.map((ref) => ({ ...ref })),
    })),
    status: hasUnnormalized ? 'REVIEW_REQUIRED' : status,
    statusReason: hasUnnormalized ? 'Unnormalized ACL syntax requires review' : undefined,
    sourceRefs: acl.sourceRefs.map(ref => ({ ...ref })),
  }
}

function mapVrf(
  vrf: VrfConfig,
  targetHardware: SwitchHardware,
  defaultStatus: TargetFeatureStatus,
  findings: Finding[]
): TargetVrfConfig {
  let status = defaultStatus
  if (targetHardware.capabilities.vrf === 'UNKNOWN') {
    status = 'UNKNOWN'
    findings.push({
      code: 'MAPPING_UNKNOWN_COMPATIBILITY',
      severity: 'warning',
      message: `Target hardware ${targetHardware.productNumber} VRF capability is UNKNOWN. Official AOS-CX feature guide verification needed.`,
      sourceRef: vrf.sourceRefs[0],
    })
  }
  return {
    name: vrf.name,
    status,
    statusReason: `VRF mapped from Cisco vrf definition ${vrf.name}`,
    sourceRefs: vrf.sourceRefs.map(ref => ({ ...ref })),
    evidenceIds: [...targetHardware.evidenceIds],
  }
}
