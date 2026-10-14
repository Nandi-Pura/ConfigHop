// AOS-CX routing configuration templates.
// Syntax: AOS-CX CLI reference (official HPE Aruba documentation).

/** Render a static IPv4 route */
export function renderStaticRoute(prefix: string, nexthop: string): string {
  // AOS-CX syntax: ip route <prefix/len> <nexthop>
  return `ip route ${prefix} ${nexthop}`
}

/** Render hostname */
export function renderHostname(name: string): string {
  return `hostname ${name}`
}
