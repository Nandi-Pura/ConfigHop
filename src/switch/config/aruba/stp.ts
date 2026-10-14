// AOS-CX STP configuration templates.
// Syntax: AOS-CX CLI reference (official HPE Aruba documentation).
// Note: AOS-CX uses MSTP by default. Per-port edge config uses 'admin-edge'.
// Per-interface edge: rendered in interface.ts via edgePort=true → 'spanning-tree port-type admin-edge'

/** Render global STP mode (MSTP is default on AOS-CX — usually not needed unless overriding) */
export function renderStpMode(mode: 'mstp' | 'rstp'): string {
  return `spanning-tree mode ${mode}`
}

/** Render MST instance VLAN mapping */
export function renderMstInstance(instance: number, vlans: number[]): string {
  return `spanning-tree mst ${instance} vlan ${vlans.join(',')}`
}
