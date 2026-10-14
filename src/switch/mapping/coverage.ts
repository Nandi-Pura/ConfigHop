// Mapping coverage summary calculation (Phase 3.3).

import type { TargetAosCxIntent, TargetFeatureStatus, MappingCoverageSummary } from './types.ts'

export function calculateMappingCoverage(intent: TargetAosCxIntent): MappingCoverageSummary {
  let readyCount = 0
  let reviewRequiredCount = 0
  let unsupportedCount = 0
  let unknownCount = 0

  const inspect = (status: TargetFeatureStatus) => {
    switch (status) {
      case 'READY':
        readyCount++
        break
      case 'REVIEW_REQUIRED':
        reviewRequiredCount++
        break
      case 'UNSUPPORTED':
        unsupportedCount++
        break
      case 'UNKNOWN':
        unknownCount++
        break
    }
  }

  if (intent.system) inspect(intent.system.status)
  intent.vlans.forEach((v) => inspect(v.status))
  intent.interfaces.forEach((i) => {
    inspect(i.status)
    if (i.portAccess) inspect(i.portAccess.status)
  })
  intent.lags.forEach((l) => inspect(l.status))
  intent.svis.forEach((s) => inspect(s.status))
  intent.acls.forEach((a) => inspect(a.status))
  intent.vrfs.forEach((v) => inspect(v.status))
  if (intent.stp) inspect(intent.stp.status)
  if (intent.vsf) inspect(intent.vsf.status)

  if (intent.nac) {
    intent.nac.radiusServers.forEach((s) => inspect(s.status))
    intent.nac.radiusGroups.forEach((g) => inspect(g.status))
    inspect(intent.nac.aaa.status)
    inspect(intent.nac.global.status)
  }

  const total = readyCount + reviewRequiredCount + unsupportedCount + unknownCount
  const mapped = readyCount + reviewRequiredCount
  const percent = total > 0 ? Math.round((readyCount / total) * 100) : 100

  return {
    totalSourceItems: total,
    mappedItems: mapped,
    readyCount,
    reviewRequiredCount,
    unsupportedCount,
    unknownCount,
    coveragePercent: percent,
  }
}
