// AOS-CX VSF configuration templates.
// Syntax: HPE Aruba Networking AOS-CX CLI reference.

export type VsfMemberConfig = {
  memberId: number
  type: string // e.g. "JL658A"
  priority?: number
  link1Ports?: string[]
  link2Ports?: string[]
}

/** Render VSF member definition */
export function renderVsfMember(member: VsfMemberConfig): string {
  const lines: string[] = [`vsf member ${member.memberId}`]
  lines.push(`    type ${member.type}`)
  if (member.priority != null) lines.push(`    priority ${member.priority}`)
  if (member.link1Ports && member.link1Ports.length > 0) {
    lines.push(`    link 1 ${member.link1Ports.join(',')}`)
  }
  if (member.link2Ports && member.link2Ports.length > 0) {
    lines.push(`    link 2 ${member.link2Ports.join(',')}`)
  }
  return lines.join('\n')
}

/** Render VSF secondary member configuration for auto-split prevention */
export function renderVsfSecondary(memberId: number): string {
  return `vsf secondary-member ${memberId}`
}
