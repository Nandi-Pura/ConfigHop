// AOS-CX VRF configuration templates.
// Syntax: HPE Aruba Networking AOS-CX CLI reference.

/** Render VRF definition (e.g. 'vrf red') */
export function renderVrf(name: string, description?: string): string {
  const lines: string[] = [`vrf ${name}`]
  if (description) lines.push(`    description ${description}`)
  return lines.join('\n')
}

/** Render binding an interface or SVI to a VRF */
export function renderInterfaceVrf(interfaceId: string, vrfName: string): string {
  return [`interface ${interfaceId}`, `    vrf attach ${vrfName}`].join('\n')
}
