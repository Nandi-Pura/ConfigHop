const ciscoPrefixes: Record<string, string> = {
  gi: 'GigabitEthernet', te: 'TenGigabitEthernet', twe: 'TwentyFiveGigE',
  fo: 'FortyGigabitEthernet', hu: 'HundredGigE',
}

export function canonicalSwitchTarget(value: string | number): string {
  const name = String(value)
  const match = /^(GigabitEthernet|Gi|TenGigabitEthernet|Te|TwentyFiveGigE|Twe|FortyGigabitEthernet|Fo|HundredGigE|Hu)(\d+\/\d+\/\d+)$/i.exec(name)
  if (!match) return name
  const prefix = match[1].toLowerCase()
  return `${ciscoPrefixes[prefix] ?? Object.values(ciscoPrefixes).find(full => full.toLowerCase() === prefix)}${match[2]}`
}

export function previewSequentialMapping(sources: string[], firstTarget: string, existing: Record<string, string | number>): Record<string, string> {
  const match = /^(GigabitEthernet|TenGigabitEthernet|TwentyFiveGigE|FortyGigabitEthernet|HundredGigE)([1-9]\d*\/\d+\/)([1-9]\d*)$/.exec(firstTarget)
  if (!match || sources.length === 0) throw new Error('Enter an IOS XE physical interface such as GigabitEthernet1/0/1.')
  if (sources.length > 512 || !Number.isSafeInteger(Number(match[3]) + sources.length - 1)) throw new Error('Bulk mapping exceeds supported interface bounds.')
  const proposed = Object.fromEntries(sources.map((source, index) => [source, `${match[1]}${match[2]}${Number(match[3]) + index}`]))
  const reserved = new Set(Object.entries(existing).filter(([source]) => !sources.includes(source)).map(([, target]) => canonicalSwitchTarget(target)))
  if (Object.values(proposed).some(target => reserved.has(canonicalSwitchTarget(target)))) throw new Error('Bulk mapping collides with an existing assignment.')
  return proposed
}
