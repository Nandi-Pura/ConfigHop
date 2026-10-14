// Interface and port-access mapping (Phase 3.3).

import type { InterfaceConfig, Finding } from '../intent/types.ts'
import type {
  TargetInterfaceConfig,
  TargetPortAccessConfig,
  TargetFeatureStatus,
  MissingDependency,
} from './types.ts'

const statusPrecedence: Record<TargetFeatureStatus, number> = {
  READY: 0,
  UNKNOWN: 1,
  REVIEW_REQUIRED: 2,
  UNSUPPORTED: 3,
}

export function mapInterface(
  srcIface: InterfaceConfig,
  ifaceMap: (srcId: string) => string,
  defaultStatus: TargetFeatureStatus,
  findings: Finding[],
  missingDependencies: MissingDependency[]
): TargetInterfaceConfig {
  const targetId = ifaceMap(srcIface.sourceInterfaceId)

  let portAccess: TargetPortAccessConfig | undefined
  if (srcIface.authentication) {
    portAccess = mapPortAccess(
      srcIface.sourceInterfaceId,
      targetId,
      srcIface.authentication,
      defaultStatus,
      findings,
      missingDependencies
    )
  }

  let status = portAccess ? portAccess.status : defaultStatus
  let statusReason = portAccess?.statusReason
  if (srcIface.adminState === 'unknown' || srcIface.role === 'unknown') {
    const physicalStatusReason = `Cisco interface ${srcIface.sourceInterfaceId} has unknown ${srcIface.adminState === 'unknown' ? 'administrative state' : 'switchport role'}.`
    if (statusPrecedence.REVIEW_REQUIRED >= statusPrecedence[status]) {
      status = 'REVIEW_REQUIRED'
      statusReason = physicalStatusReason
    }
    findings.push({ code: 'MAPPING_REVIEW_REQUIRED', severity: 'warning', message: physicalStatusReason, sourceRef: srcIface.sourceRefs[0] })
  }

  return {
    targetInterfaceId: targetId,
    sourceInterfaceId: srcIface.sourceInterfaceId,
    description: srcIface.description,
    adminState: srcIface.adminState,
    role: srcIface.role,
    accessVlan: srcIface.accessVlan,
    voiceVlan: srcIface.voiceVlan,
    trunkNativeVlan: srcIface.trunkNativeVlan,
    trunkAllowedVlans: srcIface.trunkAllowedVlans?.map((range) => ({ ...range })),
    lagId: srcIface.lagId,
    portAccess,
    status,
    statusReason,
    sourceRefs: srcIface.sourceRefs.map(ref => ({ ...ref })),
  }
}

function mapPortAccess(
  sourceInterfaceId: string,
  targetInterfaceId: string,
  auth: NonNullable<InterfaceConfig['authentication']>,
  defaultStatus: TargetFeatureStatus,
  findings: Finding[],
  missingDependencies: MissingDependency[]
): TargetPortAccessConfig {
  let status: TargetFeatureStatus = defaultStatus
  let reason: string | undefined

  const dot1xEnabled = auth.dot1x?.enabled ?? false
  const macAuthEnabled = auth.mab?.enabled ?? false
  const openAuth = auth.openAuthentication === true

  if (openAuth) {
    findings.push({
      code: 'MAPPING_SEMANTIC_DIFFERENCE',
      severity: 'warning',
      message: `Interface ${sourceInterfaceId} uses 'authentication open'. On Cisco, this allows data before authentication completes. AOS-CX does not use 'authentication open'; migrate to ClearPass initial / pre-auth role or captive portal.`,
      sourceRef: auth.sourceRefs[0],
    })
    missingDependencies.push({
      id: `DEP-CLEARPASS-OPEN-AUTH-${sourceInterfaceId}`,
      domain: 'CLEARPASS',
      title: `Pre-Auth Open Policy: ${sourceInterfaceId}`,
      details: `Cisco 'authentication open' was configured. ClearPass Policy Manager must provide an initial pre-authentication role with equivalent access rules.`,
      sourceRef: auth.sourceRefs[0],
    })
  }

  let targetViolation: 'shutdown' | 'notify' | 'unknown' | undefined
  if (auth.violation) {
    if (auth.violation === 'shutdown') {
      targetViolation = 'shutdown'
    } else if (auth.violation === 'restrict' || auth.violation === 'protect') {
      targetViolation = 'notify'
      findings.push({
        code: 'MAPPING_SEMANTIC_DIFFERENCE',
        severity: 'info',
        message: `Cisco violation '${auth.violation}' maps to AOS-CX port-access security-violation notify.`,
        sourceRef: auth.sourceRefs[0],
      })
    }
  }

  const dynamicVlanAllowed = auth.authorizationAttributes?.dynamicVlan?.enabled ?? false

  let durConfigured = false
  let durPolicyDep: string | undefined

  if (auth.authorizationAttributes?.downloadableAcl?.enabled) {
    status = 'REVIEW_REQUIRED'
    reason = 'Cisco downloadable ACL (dACL) detected. dACL is Cisco proprietary and does not exist in AOS-CX; map to Aruba Downloadable User Role (DUR).'
    findings.push({
      code: 'MAPPING_SEMANTIC_DIFFERENCE',
      severity: 'warning',
      message: `Interface ${sourceInterfaceId} expects Cisco dACL. AOS-CX utilizes Downloadable User Roles (DUR) or Local User Roles (LUR). ClearPass DUR service must be configured.`,
      sourceRef: auth.authorizationAttributes.downloadableAcl.sourceRefs[0],
    })
    durConfigured = true
    durPolicyDep = `DEP-CLEARPASS-DUR-${sourceInterfaceId}`
    missingDependencies.push({
      id: durPolicyDep,
      domain: 'CLEARPASS',
      title: `ClearPass DUR Conversion for ${sourceInterfaceId}`,
      details: `Source port used Cisco dACL. ClearPass Policy Manager enforcement profile must be created with equivalent AOS-CX DUR policy syntax.`,
      sourceRef: auth.authorizationAttributes.downloadableAcl.sourceRefs[0],
    })
  }

  if (auth.authorizationAttributes?.filterId?.enabled) {
    status = 'REVIEW_REQUIRED'
    findings.push({
      code: 'MAPPING_SEMANTIC_DIFFERENCE',
      severity: 'warning',
      message: `Interface ${sourceInterfaceId} utilizes RADIUS Filter-ID. In AOS-CX, Filter-ID maps to a locally configured Local User Role (LUR) or ACL name on the switch. Ensure corresponding role exists.`,
      sourceRef: auth.authorizationAttributes.filterId.sourceRefs[0],
    })
    missingDependencies.push({
      id: `DEP-FILTER-ID-${sourceInterfaceId}`,
      domain: 'CLEARPASS',
      title: `Filter-ID LUR Mapping: ${sourceInterfaceId}`,
      details: `RADIUS Filter-ID attribute requires a matching Local User Role (LUR) or ACL defined on AOS-CX.`,
      sourceRef: auth.authorizationAttributes.filterId.sourceRefs[0],
    })
  }

  if (auth.authorizationAttributes?.downloadableUserRole?.enabled) {
    durConfigured = true
  }

  return {
    targetInterfaceId,
    sourceInterfaceId,
    dot1xEnabled,
    macAuthEnabled,
    securityViolationAction: targetViolation,
    clientLimit: auth.maxClients,
    reauthEnabled: auth.reauthentication?.enabled,
    reauthPeriod: auth.reauthentication?.period,
    openAuthentication: openAuth,
    dynamicVlanAllowed,
    durConfigured,
    durPolicyDependency: durPolicyDep,
    status,
    statusReason: reason,
    sourceRefs: auth.sourceRefs.map(ref => ({ ...ref })),
  }
}
