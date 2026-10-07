import type { ConversionState, Domain } from './platformCatalog'
export type MappingRow = { source: string; type: string; details: string; suggested: string; target: string; status: 'Mapped' | 'Unmapped' | 'Review'; notes: string }
export type SemanticRow = { tab: string; sourceType: string; source: string; targetType: string; target: string; state: ConversionState; note: string }
export const firewallConfig = `<config>\n  <devices>\n    <entry name="localhost.localdomain">\n      <network>\n        <interface>\n          <ethernet>\n            <entry name="ethernet1/1"/>\n            <entry name="ethernet1/2"/>\n          </ethernet>\n        </interface>\n      </network>\n    </entry>\n  </devices>\n</config>`
export const firewallCandidate = `config system interface\n    edit "port1"\n        set alias "TRUST"\n    next\n    edit "port2"\n        set alias "UNTRUST"\n    next\nend\nconfig firewall address\n    edit "WEB-SERVERS"\n        set subnet 10.10.10.0 255.255.255.0\n    next\nend\n# Synthetic UI fixture; engineer review required.`
export const switchConfig = `version 17.12.1\nhostname C9300-CORE\ninterface GigabitEthernet1/0/1\n description User Access Port\n switchport mode access\n switchport access vlan 10\n spanning-tree portfast\ninterface GigabitEthernet1/0/2\n description Trunk to Distribution\n switchport mode trunk\n switchport trunk allowed vlan 10,20,30\ninterface Port-channel10\n switchport mode trunk\ninterface Vlan100\n ip address 10.100.0.1 255.255.255.0`
export const switchCandidate = `hostname CX6300-CORE\nvlan 10\n    name USERS\ninterface 1/1/1\n    description User Access Port\n    vlan access 10\ninterface 1/1/2\n    description Trunk to Distribution\n    vlan trunk allowed 10,20,30\ninterface lag 10\n    lacp mode active\ninterface vlan 100\n    ip address 10.100.0.1/24\n# Synthetic UI fixture; engineer review required.`
export const inventory: Record<Domain, [number, string][]> = {
  Firewall: [[24, 'Physical Interfaces'], [18, 'Subinterfaces'], [12, 'Zones'], [356, 'Address Objects'], [48, 'Address Groups'], [128, 'Service Objects'], [86, 'Security Policies'], [42, 'NAT Rules'], [28, 'Static Routes']],
  Switch: [[48, 'Physical Interfaces'], [4, 'LAGs / Port-channels'], [37, 'VLANs'], [22, 'Access Ports'], [18, 'Trunk Ports'], [12, 'SVIs / L3 Interfaces'], [8, 'Static Routes'], [1, 'OSPF Process'], [16, 'ACLs']],
}
export const mappings: Record<Domain, MappingRow[]> = {
  Firewall: [
    { source: 'ethernet1/1', type: 'Interface', details: 'Layer 3 · 1 subinterface', suggested: 'port1', target: 'port1', status: 'Mapped', notes: 'Fixture suggestion' },
    { source: 'ethernet1/2', type: 'Interface', details: 'Layer 3 · 2 subinterfaces', suggested: 'port2', target: 'port2', status: 'Mapped', notes: 'Fixture suggestion' },
    { source: 'ethernet1/3', type: 'Interface', details: 'Layer 3', suggested: 'port3', target: '', status: 'Review', notes: 'Check link speed' },
    { source: 'TRUST', type: 'Zone', details: '3 interfaces', suggested: 'LAN', target: 'LAN', status: 'Mapped', notes: 'Review security context' },
    { source: 'UNTRUST', type: 'Zone', details: '2 interfaces', suggested: 'WAN', target: 'WAN', status: 'Mapped', notes: 'Review security context' },
    { source: 'DMZ', type: 'Zone', details: '4 interfaces', suggested: 'DMZ', target: 'DMZ', status: 'Mapped', notes: 'Review security context' },
  ],
  Switch: [
    { source: 'GigabitEthernet1/0/1', type: 'Physical', details: 'Access VLAN 10', suggested: '1/1/1', target: '1/1/1', status: 'Mapped', notes: 'Fixture suggestion' },
    { source: 'GigabitEthernet1/0/2', type: 'Physical', details: 'Trunk VLAN 10,20,30', suggested: '1/1/2', target: '1/1/2', status: 'Mapped', notes: 'Fixture suggestion' },
    { source: 'GigabitEthernet1/0/48', type: 'Physical', details: 'Guest VLAN 20', suggested: '1/1/48', target: '', status: 'Review', notes: 'Check port speed' },
    { source: 'Port-channel10', type: 'LAG', details: 'Members: Gi1/0/1–4', suggested: 'lag10', target: 'lag10', status: 'Mapped', notes: 'LACP review' },
    { source: 'Port-channel20', type: 'LAG', details: 'Members: Gi1/0/5–8', suggested: 'lag20', target: 'lag20', status: 'Mapped', notes: 'LACP review' },
  ],
}
export const semantics: Record<Domain, SemanticRow[]> = {
  Firewall: [
    { tab: 'Objects', sourceType: 'Address Object', source: 'WEB-SERVERS', targetType: 'Firewall Address', target: 'WEB-SERVERS', state: 'EXACT', note: 'Direct concept mapping' },
    { tab: 'Objects', sourceType: 'Address Group', source: 'PROD-SERVERS', targetType: 'Address Group', target: 'PROD-SERVERS', state: 'EXACT', note: 'Group structure preserved' },
    { tab: 'Policies', sourceType: 'Security Policy', source: 'Allow-Web', targetType: 'Firewall Policy', target: 'Allow-Web', state: 'TRANSFORMED', note: 'Policy structure differs' },
    { tab: 'Policies', sourceType: 'Source Zone', source: 'TRUST', targetType: 'Security context', target: 'LAN', state: 'EQUIVALENT', note: 'Review interface binding' },
    { tab: 'Policies', sourceType: 'Destination Zone', source: 'UNTRUST', targetType: 'Security context', target: 'WAN', state: 'EQUIVALENT', note: 'Review interface binding' },
    { tab: 'NAT', sourceType: 'NAT Rule', source: 'WEB-NAT', targetType: 'VIP / NAT', target: 'WEB-NAT', state: 'TRANSFORMED', note: 'Review translation order' },
    { tab: 'Routing', sourceType: 'Static Route', source: '0.0.0.0/0', targetType: 'Static Route', target: '0.0.0.0/0', state: 'EQUIVALENT', note: 'Review next hop' },
    { tab: 'Security Services', sourceType: 'Profile', source: 'Threat Prevention', targetType: 'Security Service', target: 'Manual choice', state: 'MANUAL_ACTION_REQUIRED', note: 'Select target service' },
    { tab: 'Unsupported', sourceType: 'WildFire behavior', source: 'File analysis', targetType: 'No verified equivalent', target: '—', state: 'UNSUPPORTED', note: 'No safe fixture mapping' },
  ],
  Switch: [
    { tab: 'VLANs', sourceType: 'VLAN', source: 'VLAN 10 / USERS', targetType: 'VLAN', target: 'VLAN 10 / USERS', state: 'EXACT', note: 'Direct concept mapping' },
    { tab: 'LAGs', sourceType: 'Port-channel', source: 'Port-channel10', targetType: 'LAG', target: 'lag 10', state: 'EQUIVALENT', note: 'LACP mode review' },
    { tab: 'Layer 2', sourceType: 'Access mode', source: 'switchport mode access', targetType: 'Access mode', target: 'vlan access 10', state: 'EQUIVALENT', note: 'Access VLAN preserved' },
    { tab: 'Layer 2', sourceType: 'Trunk', source: 'allowed vlan 10,20,30', targetType: 'Trunk', target: 'vlan trunk allowed 10,20,30', state: 'EXACT', note: 'Allowed VLANs preserved' },
    { tab: 'STP', sourceType: 'Rapid-PVST', source: 'Per-VLAN STP', targetType: 'RSTP / MSTP', target: 'Manual choice', state: 'MANUAL_ACTION_REQUIRED', note: 'Per-VLAN behavior differs' },
    { tab: 'SVIs / Layer 3', sourceType: 'SVI', source: 'interface Vlan100', targetType: 'SVI', target: 'interface vlan 100', state: 'EQUIVALENT', note: 'Review address' },
    { tab: 'Routing', sourceType: 'Static route', source: '0.0.0.0/0', targetType: 'Static route', target: '0.0.0.0/0', state: 'EQUIVALENT', note: 'Review next hop' },
    { tab: 'ACLs', sourceType: 'IP access list', source: 'USERS-IN', targetType: 'ACL', target: 'USERS-IN', state: 'TRANSFORMED', note: 'Review rule order' },
    { tab: 'Unsupported', sourceType: 'Platform feature', source: 'Proprietary feature', targetType: 'No verified equivalent', target: '—', state: 'UNSUPPORTED', note: 'No safe fixture mapping' },
  ],
}
