// AOS-CX VLAN configuration templates.
// Data-driven — do not duplicate CLI syntax in SwitchWorkspace.tsx.
// All syntax verified against official HPE Aruba AOS-CX CLI documentation.

/** Render a VLAN definition */
export function renderVlan(id: number, name?: string): string {
  const lines = [`vlan ${id}`]
  if (name) lines.push(`    name ${name}`)
  return lines.join('\n')
}

/** Render multiple VLANs */
export function renderVlans(vlans: { id: number; name?: string }[]): string {
  return vlans.map((v) => renderVlan(v.id, v.name)).join('\n')
}
