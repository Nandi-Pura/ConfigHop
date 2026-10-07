import test from 'node:test'
import assert from 'node:assert/strict'
import { dataMode, firewallSource, firewallTarget, migrationMode, platform, semanticTabs, switchSourcePlatform, switchTargetPlatform, vendors } from './platformCatalog.ts'
import { mappings, semantics } from './mockData.ts'

test('scoped platform catalog routes only Palo Alto same-vendor Firewall to backend', () => {
  assert.deepEqual(vendors('Firewall'), ['Palo Alto Networks', 'Fortinet', 'Juniper Networks'])
  assert.deepEqual(vendors('Switch'), ['Cisco', 'HPE Aruba Networking', 'Juniper Networks', 'Huawei'])
  assert.equal(dataMode(firewallSource, platform('Firewall', 'Palo Alto Networks')), 'BACKEND')
  assert.equal(dataMode(firewallSource, firewallTarget), 'MOCK')
  assert.equal(dataMode(firewallSource, platform('Firewall', 'Juniper Networks')), 'MOCK')
  assert.equal(dataMode(switchSourcePlatform, switchTargetPlatform), 'MOCK')
  assert.equal(migrationMode(firewallSource, firewallTarget), 'CROSS_VENDOR')
  assert.equal(migrationMode(firewallSource, platform('Firewall', 'Palo Alto Networks')), 'SAME_VENDOR')
  assert.throws(() => platform('Firewall', 'Cisco'))
})

test('fixture semantic tabs and conversion states cover both domains', () => {
  assert.deepEqual(semanticTabs.Firewall, ['Objects', 'Policies', 'NAT', 'Routing', 'Security Services', 'Unsupported'])
  assert.deepEqual(semanticTabs.Switch, ['VLANs', 'LAGs', 'Layer 2', 'STP', 'SVIs / Layer 3', 'Routing', 'ACLs', 'Unsupported'])
  const states = new Set([...semantics.Firewall, ...semantics.Switch].map((row) => row.state))
  assert.deepEqual([...states].sort(), ['EQUIVALENT', 'EXACT', 'MANUAL_ACTION_REQUIRED', 'TRANSFORMED', 'UNSUPPORTED'].sort())
  assert.equal(mappings.Firewall[0].target, 'port1')
  assert.equal(mappings.Switch[0].target, '1/1/1')
})
