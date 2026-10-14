// AOS-CX interface configuration templates.
// Syntax: AOS-CX CLI reference (official HPE Aruba documentation).

export type ArubaInterfaceConfig = {
  id: string           // e.g. "1/1/1"
  description?: string
  accessVlan?: number
  voiceVlan?: number
  trunkNativeVlan?: number
  trunkAllowedVlans?: number[]
  mode?: 'access' | 'trunk' | 'routed'
  lagId?: number
  shutdown?: boolean
  edgePort?: boolean   // spanning-tree port-type admin-edge
  ipAddress?: string   // CIDR notation e.g. "10.99.0.1/24"
}

/** Render a physical interface block */
export function renderInterface(cfg: ArubaInterfaceConfig): string {
  const lines: string[] = [`interface ${cfg.id}`]
  if (cfg.description) lines.push(`    description ${cfg.description}`)
  if (!cfg.shutdown) lines.push(`    no shutdown`)
  if (cfg.mode === 'access' && cfg.accessVlan != null) lines.push(`    vlan access ${cfg.accessVlan}`)
  if (cfg.voiceVlan != null) lines.push(`    voice vlan ${cfg.voiceVlan}`)
  if (cfg.mode === 'trunk') {
    if (cfg.trunkNativeVlan != null) lines.push(`    vlan trunk native ${cfg.trunkNativeVlan}`)
    if (cfg.trunkAllowedVlans?.length) lines.push(`    vlan trunk allowed ${cfg.trunkAllowedVlans.join(',')}`)
  }
  if (cfg.lagId != null) lines.push(`    lag ${cfg.lagId}`)
  if (cfg.edgePort) lines.push(`    spanning-tree port-type admin-edge`)
  if (cfg.ipAddress) lines.push(`    ip address ${cfg.ipAddress}`)
  return lines.join('\n')
}

/** Render SVI (interface vlan N) */
export function renderSvi(vlanId: number, ipAddress?: string, description?: string): string {
  const lines = [`interface vlan ${vlanId}`]
  if (description) lines.push(`    description ${description}`)
  if (ipAddress) lines.push(`    ip address ${ipAddress}`)
  return lines.join('\n')
}
