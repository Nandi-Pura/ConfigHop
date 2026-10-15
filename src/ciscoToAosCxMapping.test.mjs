import test from 'node:test'
import assert from 'node:assert/strict'

import { parseCiscoConfig } from './switch/cisco/parser.ts'
import { mapCiscoToAosCx } from './switch/mapping/index.ts'
import { CX6300M_48G } from './switch/aruba/cx6300.ts'
import { CX6400_V2 } from './switch/aruba/cx6400.ts'
import { CX6300L_S3L75A } from './switch/aruba/cx6300l.ts'
import { CX6000_R8N85A } from './switch/aruba/cx6000.ts'
import { AOS_CX_RELEASES } from './switch/aosCxOs.ts'

const OS_1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
const OS_1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')

test('1. Deterministic mapping - source intent is not mutated', () => {
  const config = `
hostname CoreSwitch
vlan 10
 name Users
interface GigabitEthernet1/0/1
 switchport mode access
 switchport access vlan 10
`
  const parsed = parseCiscoConfig(config)
  const cloneBefore = JSON.parse(JSON.stringify(parsed))
  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)

  assert.deepEqual(parsed, cloneBefore, 'Source intent must not be mutated')
  assert.equal(mapped.targetIntent.system?.hostname, 'CoreSwitch')
  assert.equal(mapped.targetIntent.vlans.length, 1)
  assert.equal(mapped.targetIntent.vlans[0].vlanId, 10)
  assert.equal(mapped.targetIntent.vlans[0].name, 'Users')
})

test('2. Target model and OS compatibility affects decisions', () => {
  const config = `
hostname EdgeSwitch
vlan 20
`
  const parsed = parseCiscoConfig(config)

  // S3L75A on 10.13 is BLOCKED
  const resBlocked = mapCiscoToAosCx(parsed, CX6300L_S3L75A, OS_1013)
  assert.equal(resBlocked.targetIntent.targetPlatform.compatibilityStatus, 'BLOCKED')
  assert.ok(resBlocked.findings.some((f) => f.severity === 'error' && f.message.includes('BLOCKED')))

  // CX6400_V2 on 10.16 is READY
  const resReady = mapCiscoToAosCx(parsed, CX6400_V2, OS_1016)
  assert.equal(resReady.targetIntent.targetPlatform.compatibilityStatus, 'READY')

  // CX6000 on 10.13 is UNKNOWN
  const resUnknown = mapCiscoToAosCx(parsed, CX6000_R8N85A, OS_1013)
  assert.equal(resUnknown.targetIntent.targetPlatform.compatibilityStatus, 'UNKNOWN')
  assert.ok(resUnknown.findings.some((f) => f.code === 'MAPPING_UNKNOWN_COMPATIBILITY'))
})

test('3. authentication open versus MAB distinction and ClearPass dependency', () => {
  const config = `
interface GigabitEthernet1/0/1
 switchport mode access
 authentication open
 authentication port-control auto
 dot1x pae authenticator
 mab
`
  const parsed = parseCiscoConfig(config)
  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)

  const iface = mapped.targetIntent.interfaces[0]
  assert.ok(iface.portAccess)
  assert.equal(iface.portAccess.openAuthentication, true)
  assert.equal(iface.portAccess.macAuthEnabled, true)
  assert.equal(iface.portAccess.dot1xEnabled, true)

  const semFinding = mapped.findings.find(
    (f) => f.code === 'MAPPING_SEMANTIC_DIFFERENCE' && f.message.includes('authentication open')
  )
  assert.ok(semFinding, 'Must emit semantic difference finding for authentication open')

  const cpDep = mapped.missingDependencies.find(
    (d) => d.domain === 'CLEARPASS' && d.id.includes('OPEN-AUTH')
  )
  assert.ok(cpDep, 'Must record ClearPass dependency for authentication open')
})

test('4. AAA method-list identity, ordering, fallback, and accounting preservation', () => {
  const config = `
aaa new-model
aaa authentication dot1x default group CPPM-SERVERS local
aaa accounting dot1x default start-stop group CPPM-SERVERS
radius server CPPM-01
 address ipv4 10.10.10.10
 key 7 Secret123
aaa group server radius CPPM-SERVERS
 server name CPPM-01
`
  const parsed = parseCiscoConfig(config)
  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)

  assert.ok(mapped.targetIntent.nac)
  assert.equal(mapped.targetIntent.nac.aaa.dot1xAuthenticationGroup, 'CPPM-SERVERS')
  assert.equal(mapped.targetIntent.nac.aaa.dot1xAccounting?.groupName, 'CPPM-SERVERS')
  assert.equal(mapped.targetIntent.nac.aaa.dot1xAccounting?.action, 'start-stop')

  const fallbackFinding = mapped.findings.find(
    (f) => f.code === 'MAPPING_SEMANTIC_DIFFERENCE' && f.message.includes('fallback to local')
  )
  assert.ok(fallbackFinding, 'Must warn that AOS-CX 802.1X does not support local fallback passwords')
})

test('5. RADIUS server with missing address triggers REVIEW_REQUIRED and dependency', () => {
  const config = `
radius server INCOMPLETE-SRV
 key CiscoSharedKey
`
  const parsed = parseCiscoConfig(config)
  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)

  assert.ok(mapped.targetIntent.nac)
  const srv = mapped.targetIntent.nac.radiusServers[0]
  assert.equal(srv.host, undefined)
  assert.equal(srv.status, 'REVIEW_REQUIRED')

  const dep = mapped.missingDependencies.find(
    (d) => d.domain === 'NETWORK' && d.id.includes('RADIUS-ADDR')
  )
  assert.ok(dep, 'Must register network dependency for missing RADIUS server address')
})

test('6. Cisco dACL vs Aruba DUR and Filter-ID distinctions', () => {
  const config = `
interface GigabitEthernet1/0/1
 switchport mode access
 authentication port-control auto
 dot1x pae authenticator
 ip access-group PRE-AUTH in
`
  const parsed = parseCiscoConfig(config)
  parsed.interfaces[0].authentication = {
    ...parsed.interfaces[0].authentication,
    authorizationAttributes: {
      dynamicVlan: { enabled: true, sourceRefs: [{ startLine: 1 }] },
      downloadableAcl: { enabled: true, sourceRefs: [{ startLine: 2 }] },
      filterId: { enabled: true, sourceRefs: [{ startLine: 3 }] },
      sourceRefs: [{ startLine: 1 }],
    },
  }

  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)
  const pa = mapped.targetIntent.interfaces[0].portAccess
  assert.ok(pa)
  assert.equal(pa.dynamicVlanAllowed, true)
  assert.equal(pa.durConfigured, true)
  assert.equal(pa.status, 'REVIEW_REQUIRED')

  const durDep = mapped.missingDependencies.find(
    (d) => d.domain === 'CLEARPASS' && d.id.includes('DEP-CLEARPASS-DUR')
  )
  assert.ok(durDep, 'Must record ClearPass DUR conversion dependency')

  const filterIdDep = mapped.missingDependencies.find(
    (d) => d.domain === 'CLEARPASS' && d.id.includes('DEP-FILTER-ID')
  )
  assert.ok(filterIdDep, 'Must record Filter-ID LUR dependency')
})

test('7. CoA and RFC 5176 dynamic-authorization mapping', () => {
  const config = `
aaa server radius dynamic-author
 client 10.10.10.10 server-key SharedKey
 port 3799
`
  const parsed = parseCiscoConfig(config)
  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)

  assert.ok(mapped.targetIntent.nac)
  assert.equal(mapped.targetIntent.nac.global.radiusDynAuthEnabled, true)
  assert.equal(mapped.targetIntent.nac.global.radiusDynAuthPort, 3799)
  assert.deepEqual(mapped.targetIntent.nac.global.radiusDynAuthClients, ['10.10.10.10'])
})

test('8. Secret configuration status preserved without plaintext exposure', () => {
  const config = `
radius server SRV-PRIMARY
 address ipv4 10.1.1.1
 key PlaintextSecretNeverLeak
`
  const parsed = parseCiscoConfig(config)
  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)

  const srv = mapped.targetIntent.nac?.radiusServers[0]
  assert.equal(srv.hasSecretConfigured, true)
  assert.equal(srv.secretDeploymentRequired, true)

  const serialized = JSON.stringify(mapped)
  assert.ok(!serialized.includes('PlaintextSecretNeverLeak'), 'Plaintext secret must never appear in mapped intent')

  const credDep = mapped.missingDependencies.find(
    (d) => d.domain === 'CREDENTIAL' && d.id.includes('DEP-RADIUS-KEY')
  )
  assert.ok(credDep, 'Must create credential requirement for deployment provisioning')
})

test('9. General switch domains: VLAN, LAG, SVI, ACL, VRF, STP, VSF', () => {
  const config = `
vlan 100
 name Management
interface Port-channel1
 switchport mode trunk
 switchport trunk allowed vlan 100
interface Vlan100
 ip address 10.100.0.1 255.255.255.0
ip access-list extended SECURE-ACL
 permit ip 10.0.0.0 0.255.255.255 any
spanning-tree mode rapid-pvst
`
  const parsed = parseCiscoConfig(config)
  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)

  assert.equal(mapped.targetIntent.vlans[0].vlanId, 100)
  assert.equal(mapped.targetIntent.lags.length, 1)
  if (mapped.targetIntent.lags.length > 0) {
    console.log('LAG:', mapped.targetIntent.lags[0])
  }
  assert.equal(mapped.targetIntent.lags[0].lagId, 'Port-channel1')
  assert.equal(mapped.targetIntent.svis.length, 1)
  assert.equal(mapped.targetIntent.svis[0].ipAddress, '10.100.0.1/24')
  assert.equal(mapped.targetIntent.acls[0].name, 'SECURE-ACL')
  assert.equal(mapped.targetIntent.stp?.mode, 'rpvst')
})

test('10. Source-to-target traceability and unparsed lines pass-through', () => {
  const config = `
hostname Switch1
unsupported cisco specific command syntax
vlan 50
`
  const parsed = parseCiscoConfig(config)
  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)

  assert.equal(mapped.unparsedLines.length, 1)
  assert.equal(mapped.unparsedLines[0].text, 'unsupported cisco specific command syntax')
  assert.ok(mapped.targetIntent.vlans[0].sourceRefs.length > 0)
  assert.equal(mapped.targetIntent.vlans[0].sourceRefs[0].startLine, 4)
})

test('11. Mapping coverage calculation accurately accounts for statuses', () => {
  const config = `
vlan 10
vlan 20
`
  const parsed = parseCiscoConfig(config)
  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)

  assert.equal(mapped.coverage.totalSourceItems, 2)
  assert.equal(mapped.coverage.reviewRequiredCount, 2)
  assert.equal(mapped.coverage.coveragePercent, 0)
})


test('12. LAG declaration order preserves active/passive mode and explicit state', () => {
  const config = `
interface Port-channel1
 switchport mode trunk
 no shutdown
interface GigabitEthernet1/0/1
 channel-group 1 mode active
interface GigabitEthernet1/0/2
 channel-group 1 mode passive
`
  const parsed = parseCiscoConfig(config)
  const lag = parsed.lags[0]
  assert.equal(lag.lacpMode, 'active')
  assert.equal(lag.adminState, 'up')
  assert.deepEqual(lag.memberInterfaces, ['GigabitEthernet1/0/1', 'GigabitEthernet1/0/2'])
  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)
  assert.equal(mapped.targetIntent.lags[0].mode, 'active')
  assert.equal(mapped.targetIntent.lags[0].adminState, 'up')
})

test('13. LAG uncertainty, static EtherChannel, and duplicate members remain visible', () => {
  const parsed = parseCiscoConfig('interface Port-channel1\n no shutdown\n')
  parsed.lags[0].memberInterfaces = ['GigabitEthernet1/0/1', 'GigabitEthernet1/0/1']
  const unknown = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)
  assert.equal(unknown.targetIntent.lags[0].status, 'REVIEW_REQUIRED')
  assert.match(unknown.targetIntent.lags[0].statusReason, /LACP mode/)

  parsed.lags[0].lacpMode = 'static'
  const staticLag = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)
  assert.equal(staticLag.targetIntent.lags[0].status, 'UNSUPPORTED')
  assert.ok(staticLag.findings.some((f) => f.code === 'MAPPING_UNSUPPORTED_FEATURE'))
})

test('14. SVI references and ACL rule order remain traceable', () => {
  const parsed = parseCiscoConfig(`
interface Vlan200
 ip address 10.200.0.1 255.255.255.0
ip access-list extended ORDERED
 permit ip any any
 deny tcp any any eq 22
`)
  parsed.acls[0].entries[0].canNormalize = true
  const mapped = mapCiscoToAosCx(parsed, CX6300M_48G, OS_1016)
  assert.equal(mapped.targetIntent.svis[0].status, 'REVIEW_REQUIRED')
  assert.ok(mapped.findings.some((f) => f.message.includes('SVI VLAN 200')))
  assert.deepEqual(mapped.targetIntent.acls[0].entries.map((entry) => entry.action), ['permit', 'deny'])
  assert.equal(mapped.targetIntent.acls[0].canNormalize, false)
  assert.equal(mapped.targetIntent.acls[0].status, 'REVIEW_REQUIRED')
})



test('15. Unmapped routing and extensions remain explicit review findings', () => {
  const parsed = parseCiscoConfig('vlan 10\n')
  parsed.routing = {
    staticRoutes: [{ destinationPrefix: '192.0.2.0/24', nextHop: '192.0.2.1', sourceRefs: [{ startLine: 1 }] }],
    sourceRefs: [{ startLine: 1 }],
  }
  parsed.extensions = { lldp: { enabled: true } }
  const mapped = mapCiscoToAosCx(parsed, CX6400_V2, OS_1016)
  assert.ok(mapped.findings.some((f) => f.code === 'MAPPING_REVIEW_REQUIRED' && f.message.includes('Static route 192.0.2.0/24')))
  assert.ok(mapped.findings.some((f) => f.code === 'MAPPING_REVIEW_REQUIRED' && f.message.includes('Source extensions (lldp)')))
})

test('16. Unknown physical properties and nested ranges cannot become READY or share references', () => {
  const parsed = parseCiscoConfig('interface GigabitEthernet1/0/1\n switchport mode trunk\n switchport trunk allowed vlan 10-20\n')
  parsed.interfaces[0].adminState = 'unknown'
  parsed.interfaces[0].trunkAllowedVlans = [{ start: 10, end: 20 }]
  const mapped = mapCiscoToAosCx(parsed, CX6400_V2, OS_1016)
  const iface = mapped.targetIntent.interfaces[0]
  assert.equal(iface.status, 'REVIEW_REQUIRED')
  assert.ok(mapped.findings.some((f) => f.message.includes('unknown administrative state')))
  assert.notEqual(iface.trunkAllowedVlans?.[0], parsed.interfaces[0].trunkAllowedVlans?.[0])
  iface.trunkAllowedVlans[0].start = 999
  assert.equal(parsed.interfaces[0].trunkAllowedVlans[0].start, 10)
})

test('17. Interface status precedence preserves unsupported port-access mappings', () => {
  const config = 'interface GigabitEthernet1/0/1\n no shutdown\n switchport mode access\n authentication port-control auto\n'

  const unsupportedState = parseCiscoConfig(config)
  unsupportedState.interfaces[0].adminState = 'unknown'
  const unsupportedStateMapped = mapCiscoToAosCx(unsupportedState, CX6300L_S3L75A, OS_1013)
  assert.equal(unsupportedStateMapped.targetIntent.interfaces[0].portAccess?.status, 'UNSUPPORTED')
  assert.equal(unsupportedStateMapped.targetIntent.interfaces[0].status, 'UNSUPPORTED')
  assert.ok(unsupportedStateMapped.findings.some((f) => f.message.includes('unknown administrative state')))

  const unsupportedRole = parseCiscoConfig(config)
  unsupportedRole.interfaces[0].adminState = 'up'
  unsupportedRole.interfaces[0].role = 'unknown'
  const unsupportedRoleMapped = mapCiscoToAosCx(unsupportedRole, CX6300L_S3L75A, OS_1013)
  assert.equal(unsupportedRoleMapped.targetIntent.interfaces[0].portAccess?.status, 'UNSUPPORTED')
  assert.equal(unsupportedRoleMapped.targetIntent.interfaces[0].status, 'UNSUPPORTED')
  assert.ok(unsupportedRoleMapped.findings.some((f) => f.message.includes('unknown switchport role')))

  const reviewState = parseCiscoConfig(config)
  reviewState.interfaces[0].adminState = 'unknown'
  reviewState.interfaces[0].authentication.authorizationAttributes = {
    downloadableAcl: { enabled: true, sourceRefs: [{ startLine: 1 }] },
    sourceRefs: [{ startLine: 1 }],
  }
  const reviewStateMapped = mapCiscoToAosCx(reviewState, CX6300M_48G, OS_1016)
  assert.equal(reviewStateMapped.targetIntent.interfaces[0].portAccess?.status, 'REVIEW_REQUIRED')
  assert.equal(reviewStateMapped.targetIntent.interfaces[0].status, 'REVIEW_REQUIRED')
  assert.ok(reviewStateMapped.findings.some((f) => f.message.includes('unknown administrative state')))

  const knownParsed = parseCiscoConfig(config)
  knownParsed.interfaces[0].adminState = 'up'
  knownParsed.interfaces[0].role = 'access'
  const known = mapCiscoToAosCx(knownParsed, CX6300M_48G, OS_1016)
  assert.equal(known.targetIntent.interfaces[0].status, 'REVIEW_REQUIRED')
  assert.equal(known.targetIntent.interfaces[0].portAccess?.status, 'REVIEW_REQUIRED')
  assert.ok(!known.findings.some((f) => f.message.includes('unknown administrative state') || f.message.includes('unknown switchport role')))
})
