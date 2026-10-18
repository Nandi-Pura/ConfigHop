export type SwitchDeclaration = { name: string; type: 'Physical' | 'Logical' | 'Unrecognized' }

export function inspectSwitchDeclarations(text: string): SwitchDeclaration[] {
  const seen = new Set<string>()
  return text.split(/\r?\n/).flatMap((line) => {
    const name = /^\s*interface\s+(\S+)/i.exec(line)?.[1]
    if (!name || seen.has(name.toLowerCase())) return []
    seen.add(name.toLowerCase())
    const type = /^(?:(?:GigabitEthernet|TenGigabitEthernet|TwentyFiveGigE|FortyGigabitEthernet|HundredGigE|Ethernet|FastEthernet|Gi|Te|Fa|Eth)\d|\d+\/\d+\/\d+$)/i.test(name) ? 'Physical' : /^(?:Port-channel|Po|Vlan|Loopback|lag|tunnel)\d/i.test(name) ? 'Logical' : 'Unrecognized'
    return [{ name, type }]
  })
}

export function validSlotAssignments(text: string, saved: unknown): Record<string, number> {
  if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return {}
  const names = new Set(inspectSwitchDeclarations(text).filter((item) => item.type === 'Physical').map((item) => item.name))
  const slots = new Set<number>()
  return Object.fromEntries(Object.entries(saved).filter(([name, slot]) => {
    if (!names.has(name) || !Number.isInteger(slot) || Number(slot) < 1 || Number(slot) > 48 || slots.has(Number(slot))) return false
    slots.add(Number(slot))
    return true
  })) as Record<string, number>
}
