// AOS-CX LAG/LACP configuration templates.
// Syntax: AOS-CX CLI reference (official HPE Aruba documentation).

export type ArubaLagConfig = {
  lagId: number
  description?: string
  mode?: 'active' | 'passive'  // LACP mode
  trunkNativeVlan?: number
  trunkAllowedVlans?: number[]
  routing?: boolean
}

/** Render a LAG (port-channel equivalent) interface block */
export function renderLag(cfg: ArubaLagConfig): string {
  const lines: string[] = [`interface lag ${cfg.lagId}`]
  if (cfg.description) lines.push(`    description ${cfg.description}`)
  lines.push(`    no shutdown`)
  if (cfg.routing === false) lines.push(`    no routing`)
  if (cfg.trunkNativeVlan != null) lines.push(`    vlan trunk native ${cfg.trunkNativeVlan}`)
  if (cfg.trunkAllowedVlans?.length) lines.push(`    vlan trunk allowed ${cfg.trunkAllowedVlans.join(',')}`)
  if (cfg.mode) lines.push(`    lacp mode ${cfg.mode}`)
  return lines.join('\n')
}
