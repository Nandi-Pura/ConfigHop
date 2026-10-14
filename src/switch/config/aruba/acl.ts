// AOS-CX ACL configuration templates.
// Syntax: HPE Aruba Networking AOS-CX CLI reference.

export type AclRule = {
  sequence: number
  action: 'permit' | 'deny'
  protocol: 'ip' | 'tcp' | 'udp' | 'icmp'
  source: string      // e.g. "10.0.0.0/24" or "any"
  destination: string // e.g. "any" or "10.1.0.0/16"
  dstPort?: number
}

/** Render an IPv4 access-list definition */
export function renderAcl(name: string, rules: AclRule[]): string {
  const lines: string[] = [`access-list ip ${name}`]
  for (const rule of rules) {
    let line = `    ${rule.sequence} ${rule.action} ${rule.protocol} ${rule.source} ${rule.destination}`
    if (rule.dstPort != null) line += ` eq ${rule.dstPort}`
    lines.push(line)
  }
  return lines.join('\n')
}

/** Render applying an ACL to an interface */
export function renderInterfaceAcl(interfaceId: string, aclName: string, direction: 'in' | 'out'): string {
  return [`interface ${interfaceId}`, `    apply access-list ip ${aclName} ${direction}`].join('\n')
}
