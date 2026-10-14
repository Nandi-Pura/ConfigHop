// NAC mapping: RADIUS servers, AAA method lists, Global NAC, and CoA (Phase 3.3).

import type { NormalizedSwitchIntent, Finding } from '../intent/types.ts'
import type { SwitchHardware } from '../types.ts'
import type {
  TargetRadiusServer,
  TargetRadiusGroup,
  TargetAaaConfig,
  TargetNacGlobal,
  TargetFeatureStatus,
  MissingDependency,
} from './types.ts'

export function mapNac(
  nac: NormalizedSwitchIntent['nac'],
  defaultStatus: TargetFeatureStatus,
  targetHw: SwitchHardware,
  findings: Finding[],
  missingDependencies: MissingDependency[]
): {
  servers: TargetRadiusServer[]
  groups: TargetRadiusGroup[]
  aaa: TargetAaaConfig
  global: TargetNacGlobal
} {
  if (!nac) {
    return {
      servers: [],
      groups: [],
      aaa: { sourceRefs: [], status: defaultStatus },
      global: { dot1xEnabled: false, macAuthEnabled: false, radiusDynAuthClients: [], sourceRefs: [], status: defaultStatus },
    }
  }

  const servers = mapRadiusServers(nac.radiusServers, defaultStatus, findings, missingDependencies)
function mapRadiusServers(
  radiusServers: NonNullable<NormalizedSwitchIntent['nac']>['radiusServers'],
  defaultStatus: TargetFeatureStatus,
  findings: Finding[],
  missingDependencies: MissingDependency[]
): TargetRadiusServer[] {
  return radiusServers.map((srv) => {
    let srvStatus = defaultStatus
    let srvReason: string | undefined

    if (!srv.address) {
      srvStatus = 'REVIEW_REQUIRED'
      srvReason = `RADIUS server ${srv.name || srv.id} has no resolved network address. IP must be configured.`
      missingDependencies.push({
        id: `DEP-RADIUS-ADDR-${srv.id}`,
        domain: 'NETWORK',
        title: `Unresolved RADIUS Server Address: ${srv.name || srv.id}`,
        details: `The Cisco configuration defined RADIUS server ${srv.name || srv.id} without an IPv4/IPv6 address. Target AOS-CX radius-server host requires an IP address or FQDN.`,
        sourceRef: srv.sourceRefs[0],
      })
      findings.push({
        code: 'MAPPING_DEPENDENCY_MISSING',
        severity: 'warning',
        message: srvReason,
        sourceRef: srv.sourceRefs[0],
      })
    }

    if (srv.key.configured) {
      missingDependencies.push({
        id: `DEP-RADIUS-KEY-${srv.id}`,
        domain: 'CREDENTIAL',
        title: `RADIUS Shared Secret Required: ${srv.name || srv.id}`,
        details: `Shared secret for server ${srv.name || srv.id} was configured in source Cisco CLI but cannot be copied in plaintext. Must be provisioned securely during AOS-CX deployment.`,
        sourceRef: srv.sourceRefs[0],
      })
    }

    return {
      id: srv.id,
      name: srv.name || srv.id,
      host: srv.address,
      authPort: srv.authPort ?? 1812,
      acctPort: srv.acctPort ?? 1813,
      hasSecretConfigured: srv.key.configured,
      secretDeploymentRequired: srv.key.configured,
      timeout: srv.timeout,
      retransmit: srv.retransmit,
      status: srvStatus,
      statusReason: srvReason,
      sourceRefs: srv.sourceRefs.map(ref => ({ ...ref })),
    }
  })
}

function mapRadiusGroups(
  serverGroups: NonNullable<NormalizedSwitchIntent['nac']>['radiusServerGroups'],
  servers: TargetRadiusServer[],
  defaultStatus: TargetFeatureStatus
): TargetRadiusGroup[] {
  return serverGroups.map((grp) => {
    const srvNames = grp.serverIds.map((id) => {
      const match = servers.find((s) => s.id === id)
      return match ? match.name : id
    })
    return {
      name: grp.name,
      serverNames: srvNames,
      status: defaultStatus,
      sourceRefs: grp.sourceRefs.map(ref => ({ ...ref })),
    }
  })
}

  const groups = mapRadiusGroups(nac.radiusServerGroups, servers, defaultStatus)
function mapAaaConfig(
  aaa: NonNullable<NormalizedSwitchIntent['nac']>['aaa'],
  groups: TargetRadiusGroup[],
  defaultStatus: TargetFeatureStatus,
  findings: Finding[]
): TargetAaaConfig {
  const targetAaa: TargetAaaConfig = {
    sourceRefs: aaa ? [...aaa.sourceRefs] : [],
    status: defaultStatus,
  }

  if (aaa?.authentication) {
    const dot1xList =
      aaa.authentication.defaultMethodLists?.['dot1x'] ||
      Object.values(aaa.authentication.namedMethodLists).find((l) => l.type === 'dot1x') ||
      aaa.authentication.defaultMethodList

    if (dot1xList) {
      const radiusGroup = dot1xList.methods.find((m) => m.type === 'group')
      if (radiusGroup && radiusGroup.type === 'group') {
        targetAaa.dot1xAuthenticationGroup = radiusGroup.groupName
        if (
          radiusGroup.groupName.toLowerCase() !== 'radius' &&
          !groups.some((g) => g.name.toLowerCase() === radiusGroup.groupName.toLowerCase())
        ) {
          findings.push({
            code: 'MAPPING_UNRESOLVED_REFERENCE',
            severity: 'warning',
            message: `AAA dot1x authentication references group '${radiusGroup.groupName}', which is not defined in server groups.`,
            sourceRef: dot1xList.sourceRefs[0],
          })
        }
      }

      const hasLocalFallback = dot1xList.methods.some((m) => m.type === 'local')
      if (hasLocalFallback) {
        findings.push({
          code: 'MAPPING_SEMANTIC_DIFFERENCE',
          severity: 'warning',
          message: 'Cisco AAA dot1x includes fallback to local. AOS-CX port-access 802.1X does not support local fallback passwords; authentication requires RADIUS / ClearPass.',
          sourceRef: dot1xList.sourceRefs[0],
        })
      }
    }
  }

  if (aaa?.accounting) {
    const acctDot1x =
      aaa.accounting.defaultMethodLists?.['dot1x'] ||
      Object.values(aaa.accounting.namedMethodLists).find((l) => l.type === 'dot1x') ||
      aaa.accounting.defaultMethodList

    if (acctDot1x) {
      const radiusGroup = acctDot1x.methods.find((m) => m.type === 'group')
      if (radiusGroup && radiusGroup.type === 'group') {
        targetAaa.dot1xAccounting = {
          groupName: radiusGroup.groupName,
          action: acctDot1x.action || 'start-stop',
        }
      }
      if (acctDot1x.action && acctDot1x.action !== 'start-stop') {
        findings.push({
          code: 'MAPPING_SEMANTIC_DIFFERENCE',
          severity: 'info',
          message: `Cisco accounting action '${acctDot1x.action}' maps to AOS-CX interim-accounting / accounting interval standard models.`,
          sourceRef: acctDot1x.sourceRefs[0],
        })
      }
    }
  }

  return targetAaa
}

function mapGlobalNac(
  nac: NonNullable<NormalizedSwitchIntent['nac']>,
  defaultStatus: TargetFeatureStatus
): TargetNacGlobal {
  const targetNacGlobal: TargetNacGlobal = {
    dot1xEnabled: nac.dot1x?.systemAuthControl ?? nac.dot1x?.enabled ?? false,
    macAuthEnabled: nac.mab?.enabled ?? false,
    radiusDynAuthClients: [],
    sourceRefs: [],
    status: defaultStatus,
  }

  if (nac.coa) {
    targetNacGlobal.radiusDynAuthEnabled = nac.coa.enabled
    targetNacGlobal.radiusDynAuthPort = nac.coa.serverConfig?.port ?? 3799
    if (nac.coa.serverConfig?.clientAddresses) {
      targetNacGlobal.radiusDynAuthClients = [...nac.coa.serverConfig.clientAddresses]
    } else if (nac.coa.clientConfig?.serverAddresses) {
      targetNacGlobal.radiusDynAuthClients = [...nac.coa.clientConfig.serverAddresses]
    }
    targetNacGlobal.sourceRefs = [...nac.coa.sourceRefs]
  }

  return targetNacGlobal
}

  const aaa = mapAaaConfig(nac.aaa, groups, defaultStatus, findings)
  const global = mapGlobalNac(nac, defaultStatus)

  return { servers, groups, aaa, global }
}
