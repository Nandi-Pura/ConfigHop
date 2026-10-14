import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseCiscoConfig } from './switch/cisco/parser.ts'

// ===== CISCO IOS/IOS XE PARSER TESTS =====

test('Cisco 1. Parse RADIUS server with secret (legacy syntax)', () => {
  const config = `
!
radius-server host 10.1.1.100 auth-port 1812 acct-port 1813 key MySecret123
!
`
  const intent = parseCiscoConfig(config)

  assert.equal(intent.source.vendor, 'cisco')
  assert.equal(intent.nac?.radiusServers.length, 1)
  assert.equal(intent.nac?.radiusServers[0].address, '10.1.1.100')
  assert.equal(intent.nac?.radiusServers[0].authPort, 1812)
  assert.equal(intent.nac?.radiusServers[0].acctPort, 1813)
  assert.equal(intent.nac?.radiusServers[0].key.configured, true)

  // Secret must be redacted
  assert.equal('secret' in intent.nac?.radiusServers[0].key, false)

  // Finding should indicate secret was redacted
  const secretFinding = intent.findings.find(f => f.code === 'NAC_SECRET_REDACTED')
  assert.ok(secretFinding)
  assert.equal(secretFinding.severity, 'info')
})

test('Cisco 2. Parse AAA authentication with method lists', () => {
  const config = `
!
aaa new-model
aaa authentication login default group CLEARPASS local
aaa authentication dot1x DOT1X_LIST group CLEARPASS
!
`
  const intent = parseCiscoConfig(config)

  assert.ok(intent.nac?.aaa?.authentication)
  assert.ok(intent.nac?.aaa?.authentication?.defaultMethodList)
  assert.equal(intent.nac?.aaa?.authentication?.defaultMethodList?.methods.length, 2)
  assert.equal(intent.nac?.aaa?.authentication?.defaultMethodList?.methods[0].type, 'group')
  assert.equal(intent.nac?.aaa?.authentication?.defaultMethodList?.methods[1].type, 'local')

  assert.ok(intent.nac?.aaa?.authentication?.namedMethodLists['DOT1X_LIST'])
})

test('Cisco 3. Parse interface with 802.1X and MAB', () => {
  const config = `
!
interface GigabitEthernet1/0/1
 switchport mode access
 authentication port-control auto
 authentication host-mode multi-auth
 authentication order dot1x mab
 dot1x pae authenticator
 mab
 no shutdown
!
`
  const intent = parseCiscoConfig(config)

  assert.equal(intent.interfaces.length, 1)
  const iface = intent.interfaces[0]

  assert.equal(iface.sourceInterfaceId, 'GigabitEthernet1/0/1')
  assert.equal(iface.role, 'access')
  assert.equal(iface.adminState, 'up')
  assert.equal(iface.authentication?.portControl, 'auto')
  assert.equal(iface.authentication?.hostMode, 'multi-auth')
  assert.ok(iface.authentication?.dot1x)
  assert.ok(iface.authentication?.mab)
  assert.equal(iface.authentication?.authenticationOrder?.length, 2)
})

test('Cisco 4. Secret redaction - no secrets in output', () => {
  const config = `
!
radius-server host 10.1.1.100 key SuperSecret123
radius-server key GlobalSecret456
!
`
  const intent = parseCiscoConfig(config)

  const serialized = JSON.stringify(intent)
  assert.equal(serialized.includes('SuperSecret123'), false)
  assert.equal(serialized.includes('GlobalSecret456'), false)

  assert.equal(intent.nac?.radiusServers[0].key.configured, true)
  const secretFindings = intent.findings.filter(f => f.code === 'NAC_SECRET_REDACTED')
  assert.equal(secretFindings.length, 2)
})

test('Cisco 5. Source line traceability', () => {
  const config = `
!
hostname TEST-SW
radius-server host 10.1.1.100
aaa authentication dot1x default group radius
interface GigabitEthernet1/0/1
 authentication port-control auto
!
`
  const intent = parseCiscoConfig(config)

  assert.ok(intent.system?.sourceRefs)
  assert.equal(intent.system?.sourceRefs[0].startLine, 3)
  assert.equal(intent.nac?.radiusServers[0].sourceRefs[0].startLine, 4)
  assert.ok(intent.nac?.aaa?.authentication?.defaultMethodList?.sourceRefs)
  assert.equal(intent.nac?.aaa?.authentication?.defaultMethodList?.sourceRefs[0].startLine, 5)
  assert.ok(intent.interfaces[0].authentication?.sourceRefs)
  assert.equal(intent.interfaces[0].authentication?.sourceRefs[0].startLine, 7)
})

test('Cisco 6. Comprehensive NAC configuration', () => {
  const config = `
!
hostname CAMPUS-SW-01
!
aaa new-model
!
radius-server host 10.10.1.10 auth-port 1812 acct-port 1813 key ClearPass123
radius-server host 10.10.1.11 auth-port 1812 acct-port 1813 key ClearPass123
!
aaa group server radius CLEARPASS
!
aaa authentication login default group CLEARPASS local
aaa authentication dot1x default group CLEARPASS
aaa authorization network default group CLEARPASS
aaa accounting dot1x default start-stop group CLEARPASS
!
dot1x system-auth-control
!
interface GigabitEthernet1/0/1
 description User Access Port
 switchport mode access
 authentication port-control auto
 authentication host-mode multi-auth
 authentication order dot1x mab
 authentication violation restrict
 dot1x pae authenticator
 mab
 no shutdown
!
interface GigabitEthernet1/0/24
 description Uplink Port
 switchport mode trunk
 no shutdown
!
end
`
  const intent = parseCiscoConfig(config)

  // System
  assert.equal(intent.system?.hostname, 'CAMPUS-SW-01')

  // RADIUS
  assert.equal(intent.nac?.radiusServers.length, 2)
  assert.equal(intent.nac?.radiusServers[0].address, '10.10.1.10')
  assert.equal(intent.nac?.radiusServers[0].key.configured, true)

  // Server group
  assert.equal(intent.nac?.radiusServerGroups.length, 1)
  assert.equal(intent.nac?.radiusServerGroups[0].name, 'CLEARPASS')

  // AAA
  assert.ok(intent.nac?.aaa?.authentication?.defaultMethodList)
  assert.ok(intent.nac?.aaa?.authorization?.defaultMethodList)
  assert.ok(intent.nac?.aaa?.accounting?.defaultMethodList)

  // Global 802.1X
  assert.equal(intent.nac?.dot1x?.systemAuthControl, true)

  // Interfaces
  assert.equal(intent.interfaces.length, 2)

  const accessPort = intent.interfaces[0]
  assert.equal(accessPort.sourceInterfaceId, 'GigabitEthernet1/0/1')
  assert.equal(accessPort.role, 'access')
  assert.equal(accessPort.adminState, 'up')
  assert.ok(accessPort.authentication?.dot1x)
  assert.ok(accessPort.authentication?.mab)
  assert.equal(accessPort.authentication?.portControl, 'auto')
  assert.equal(accessPort.authentication?.hostMode, 'multi-auth')

  const trunkPort = intent.interfaces[1]
  assert.equal(trunkPort.sourceInterfaceId, 'GigabitEthernet1/0/24')
  assert.equal(trunkPort.role, 'trunk')

  // Secret findings
  const secretFindings = intent.findings.filter(f => f.code === 'NAC_SECRET_REDACTED')
  assert.equal(secretFindings.length, 2)
})

test('Cisco 7. Multiple interfaces with different settings', () => {
  const config = `
!
interface GigabitEthernet1/0/1
 authentication port-control auto
 dot1x pae authenticator
!
interface GigabitEthernet1/0/2
 authentication port-control force-authorized
!
interface GigabitEthernet1/0/3
 switchport mode trunk
!
`
  const intent = parseCiscoConfig(config)

  assert.equal(intent.interfaces.length, 3)
  assert.equal(intent.interfaces[0].authentication?.portControl, 'auto')
  assert.equal(intent.interfaces[1].authentication?.portControl, 'force-authorized')
  assert.equal(intent.interfaces[2].authentication, undefined)
})

test('Cisco 8. Empty configuration produces valid intent', () => {
  const config = `!
! Empty config
!`
  const intent = parseCiscoConfig(config)

  assert.equal(intent.source.vendor, 'cisco')
  assert.equal(intent.interfaces.length, 0)
  assert.equal(intent.nac, undefined)
  assert.ok(Array.isArray(intent.findings))
})

test('Cisco 9. AAA authorization and accounting', () => {
  const config = `
!
aaa authorization network default group CLEARPASS
aaa accounting dot1x default start-stop group CLEARPASS
!
`
  const intent = parseCiscoConfig(config)

  assert.ok(intent.nac?.aaa?.authorization?.defaultMethodList)
  assert.equal(intent.nac?.aaa?.authorization?.defaultMethodList?.methods[0].type, 'group')
  assert.ok(intent.nac?.aaa?.accounting?.defaultMethodList)
  assert.equal(intent.nac?.aaa?.accounting?.defaultMethodList?.methods[0].type, 'group')
})

test('Cisco 10. Port control and host mode variations', () => {
  const config = `
!
interface GigabitEthernet1/0/1
 authentication port-control force-unauthorized
 authentication host-mode single-host
!
interface GigabitEthernet1/0/2
 authentication host-mode multi-domain
!
`
  const intent = parseCiscoConfig(config)

  assert.equal(intent.interfaces[0].authentication?.portControl, 'force-unauthorized')
  assert.equal(intent.interfaces[0].authentication?.hostMode, 'single-host')
  assert.equal(intent.interfaces[1].authentication?.hostMode, 'multi-domain')
})

test('Cisco 11. Violation actions', () => {
  const config = `
!
interface GigabitEthernet1/0/1
 authentication violation shutdown
!
interface GigabitEthernet1/0/2
 authentication violation protect
!
interface GigabitEthernet1/0/3
 authentication violation replace
!
`
  const intent = parseCiscoConfig(config)

  assert.equal(intent.interfaces[0].authentication?.violation, 'shutdown')
  assert.equal(intent.interfaces[1].authentication?.violation, 'protect')
  assert.equal(intent.interfaces[2].authentication?.violation, 'replace')
})

test('Cisco 12. Coverage calculation with unparsed lines', () => {
  const config = `
!
hostname TEST
radius-server host 10.1.1.1
unknown-command-here
interface GigabitEthernet1/0/1
 switchport mode access
another-unknown-command
!
`
  const intent = parseCiscoConfig(config)

  assert.ok(intent.coverage)
  assert.ok(intent.coverage.totalLines > 0)
  assert.ok(intent.coverage.unparsedLines >= 2)
  assert.equal(typeof intent.coverage.coveragePercent, 'number')
})

test('Cisco 13. Modern RADIUS server syntax with subcommands', () => {
  const config = `
!
radius server CPPM-PRIMARY
 address ipv4 10.20.1.10 auth-port 1812 acct-port 1813
 key ClearPassSharedKey
 timeout 5
 retransmit 3
!
aaa group server radius RADIUS-GROUP
 server name CPPM-PRIMARY
!
`
  const intent = parseCiscoConfig(config)

  assert.equal(intent.nac?.radiusServers.length, 1)
  const server = intent.nac?.radiusServers[0]
  assert.equal(server?.id, 'radius-server-CPPM-PRIMARY')
  assert.equal(server?.address, '10.20.1.10')
  assert.equal(server?.authPort, 1812)
  assert.equal(server?.acctPort, 1813)
  assert.equal(server?.key.configured, true)
  assert.equal(server?.timeout, 5)
  assert.equal(server?.retransmit, 3)

  assert.equal(intent.nac?.radiusServerGroups.length, 1)
  const group = intent.nac?.radiusServerGroups[0]
  assert.equal(group?.name, 'RADIUS-GROUP')
  assert.deepEqual(group?.serverIds, ['radius-server-CPPM-PRIMARY'])

  // Ensure secret redacted finding
  const secretFindings = intent.findings.filter(f => f.code === 'NAC_SECRET_REDACTED')
  assert.equal(secretFindings.length, 1)
})

test('Cisco 14. CoA / Dynamic Author configuration', () => {
  const config = `
!
aaa server radius dynamic-author
 client 10.20.1.10
 port 3799
!
`
  const intent = parseCiscoConfig(config)

  assert.equal(intent.nac?.coa?.enabled, true)
  assert.equal(intent.nac?.coa?.serverConfig?.enabled, true)
  assert.deepEqual(intent.nac?.coa?.serverConfig?.clientAddresses, ['10.20.1.10'])
  assert.equal(intent.nac?.coa?.serverConfig?.port, 3799)
})

test('Cisco 15. Unresolved references generate warnings', () => {
  const config = `
!
aaa group server radius GROUP-1
 server name NON-EXISTENT-SERVER
!
aaa authentication dot1x default group NON-EXISTENT-GROUP
!
`
  const intent = parseCiscoConfig(config)

  const serverFindings = intent.findings.filter(f => f.code === 'NAC_UNRESOLVED_RADIUS_SERVER')
  assert.equal(serverFindings.length, 1)

  const groupFindings = intent.findings.filter(f => f.code === 'NAC_UNRESOLVED_SERVER_GROUP')
  assert.equal(groupFindings.length, 1)
})

test('Cisco 16. Interface 802.1X timeout and reauth configuration', () => {
  const config = `
!
interface GigabitEthernet1/0/1
 authentication periodic
 authentication timer reauthenticate 3600
 dot1x timeout tx-period 10
 dot1x timeout quiet-period 30
 dot1x timeout server-timeout 20
 dot1x timeout supp-timeout 25
!
`
  const intent = parseCiscoConfig(config)

  const iface = intent.interfaces[0]
  assert.equal(iface.authentication?.reauthentication?.enabled, true)
  assert.equal(iface.authentication?.reauthentication?.period, 3600)
  assert.equal(iface.authentication?.dot1x?.timeout?.txPeriod, 10)
  assert.equal(iface.authentication?.dot1x?.timeout?.quietPeriod, 30)
  assert.equal(iface.authentication?.dot1x?.timeout?.serverTimeout, 20)
  assert.equal(iface.authentication?.dot1x?.timeout?.suppTimeout, 25)
})

test('Cisco 17. authentication open is distinct from MAB', () => {
  const config = `
!
interface GigabitEthernet1/0/1
 switchport mode access
 authentication port-control auto
 authentication open
!
interface GigabitEthernet1/0/2
 switchport mode access
 mab
!
`
  const intent = parseCiscoConfig(config)

  const iface1 = intent.interfaces[0]
  assert.equal(iface1.authentication?.openAuthentication, true)
  assert.equal(iface1.authentication?.mab, undefined, 'authentication open must NOT enable MAB')

  const iface2 = intent.interfaces[1]
  assert.equal(iface2.authentication?.mab?.enabled, true)
  assert.equal(iface2.authentication?.openAuthentication, undefined)
})

test('Cisco 18. Preserve AAA method-list identity, types, order, and accounting action', () => {
  const config = `
!
aaa new-model
aaa authentication login METHOD_A group RADIUS local
aaa authentication dot1x METHOD_A group CLEARPASS
aaa authorization network default group CLEARPASS local
aaa authorization exec default group TACACS local none
aaa accounting dot1x default start-stop group CLEARPASS
aaa accounting network default stop-only group RADIUS
!
`
  const intent = parseCiscoConfig(config)
  const aaa = intent.nac?.aaa
  assert.ok(aaa)

  // Named method lists with same list name but different types do not overwrite each other
  assert.ok(aaa?.authentication?.namedMethodLists['login/METHOD_A'])
  assert.ok(aaa?.authentication?.namedMethodLists['dot1x/METHOD_A'])
  assert.equal(aaa?.authentication?.namedMethodLists['login/METHOD_A'].type, 'login')
  assert.equal(aaa?.authentication?.namedMethodLists['dot1x/METHOD_A'].type, 'dot1x')

  // Method order and fallback semantics preserved
  const loginMethods = aaa?.authentication?.namedMethodLists['login/METHOD_A'].methods
  assert.equal(loginMethods?.[0].type, 'group')
  assert.equal(loginMethods?.[1].type, 'local')

  // Authorization defaults for different types preserved
  assert.ok(aaa?.authorization?.defaultMethodLists?.['network'])
  assert.ok(aaa?.authorization?.defaultMethodLists?.['exec'])
  assert.equal(aaa?.authorization?.defaultMethodLists?.['network'].methods[0].type, 'group')
  assert.equal(aaa?.authorization?.defaultMethodLists?.['exec'].methods[2].type, 'none')

  // Accounting actions preserved
  assert.ok(aaa?.accounting?.defaultMethodLists?.['dot1x'])
  assert.equal(aaa?.accounting?.defaultMethodLists?.['dot1x'].action, 'start-stop')
  assert.ok(aaa?.accounting?.defaultMethodLists?.['network'])
  assert.equal(aaa?.accounting?.defaultMethodLists?.['network'].action, 'stop-only')
})

test('Cisco 19. Modern RADIUS address handling and missing address finding', () => {
  const config = `
!
radius server CPPM-PRIMARY
 address ipv4 10.20.1.10 auth-port 1812 acct-port 1813
 key SecretKey1
!
radius server CPPM-NO-ADDR
 key SecretKey2
 timeout 5
!
`
  const intent = parseCiscoConfig(config)
  const servers = intent.nac?.radiusServers
  assert.ok(servers)
  assert.equal(servers?.length, 2)

  const primary = servers?.find(s => s.name === 'CPPM-PRIMARY')
  assert.ok(primary)
  assert.equal(primary?.name, 'CPPM-PRIMARY')
  assert.equal(primary?.address, '10.20.1.10')

  const noAddr = servers?.find(s => s.name === 'CPPM-NO-ADDR')
  assert.ok(noAddr)
  assert.equal(noAddr?.name, 'CPPM-NO-ADDR')
  assert.equal(noAddr?.address, undefined, 'Server name must not be used as IP address')

  // Finding emitted for missing server address
  const missingAddrFinding = intent.findings.find(f => f.code === 'NAC_MISSING_SERVER_ADDRESS')
  assert.ok(missingAddrFinding)
  assert.ok(missingAddrFinding.message.includes('CPPM-NO-ADDR'))
})

test('Cisco 20. Preserve unsupported interface commands with line traceability and secret redaction', () => {
  const config = `
!
interface GigabitEthernet1/0/1
 switchport mode access
 dot1x max-req 5
 standby 1 ip 10.1.1.254
 standby 1 authentication md5 key-string UltraSecretHSRPPass
 custom-vendor-command test-param
!
`
  const intent = parseCiscoConfig(config)
  const unparsed = intent.unparsedLines
  assert.ok(unparsed.length >= 3)

  // Verify source line traceability
  const hsrpLine = unparsed.find(u => u.text.includes('standby 1 authentication'))
  assert.ok(hsrpLine)
  assert.ok(hsrpLine.lineNumber > 0)

  // Verify secret is redacted from unparsed content
  assert.equal(hsrpLine.text.includes('UltraSecretHSRPPass'), false)
  assert.ok(hsrpLine.text.includes('<redacted>'))

  // Verify finding was generated
  const secretFinding = intent.findings.find(f => f.code === 'NAC_SECRET_REDACTED')
  assert.ok(secretFinding)
})

test('Cisco 21. Accurate per-line parsing coverage calculation', () => {
  const config = `
!
hostname SW1
interface GigabitEthernet1/0/1
 switchport mode access
 ip access-group STATIC_ACL in
 unknown-command-line
!
`
  const intent = parseCiscoConfig(config)
  const cov = intent.coverage
  assert.ok(cov)
  assert.equal(cov.totalLines, 5)
  assert.equal(cov.parsedLines, 3) // hostname, interface, switchport mode access
  assert.equal(cov.partiallyParsedLines, 1) // ip access-group
  assert.equal(cov.unparsedLines, 1) // unknown-command-line
  assert.equal(cov.parsedLines + (cov.partiallyParsedLines || 0) + cov.unparsedLines, cov.totalLines)
  assert.equal(cov.coveragePercent, 60)
})

test('Cisco 22. Authorization normalization and dACL vs DUR distinction', () => {
  const config = `
!
interface GigabitEthernet1/0/1
 switchport mode access
 dot1x vlan-assignment
 ip access-group STATIC_FILTER in
 authentication event fail action next-method
!
`
  const intent = parseCiscoConfig(config)
  const iface = intent.interfaces[0]

  // Dynamic VLAN assignment normalized
  assert.equal(iface.authentication?.authorizationAttributes?.dynamicVlan?.enabled, true)

  // Static ACL is not conflated with dACL or DUR
  assert.equal(iface.authentication?.authorizationAttributes?.downloadableAcl, undefined)
  assert.equal(iface.authentication?.authorizationAttributes?.downloadableUserRole, undefined)

  // Static ACL and authentication event preserved in unparsed content with findings
  assert.ok(intent.unparsedLines.some(u => u.text.includes('ip access-group')))
  assert.ok(intent.unparsedLines.some(u => u.text.includes('authentication event fail')))
  assert.ok(intent.findings.some(f => f.message.includes('Static interface ACL reference')))
  assert.ok(intent.findings.some(f => f.message.includes('Unsupported authentication event command')))
})

test('Cisco 23. Secret redaction audit across all configuration styles', () => {
  const secretA = 'PlainRadiusHostSecret99'
  const secretB = 'PlainModernSubcommandSecret88'
  const secretC = 'PlainInterfaceSecret77'
  const secretD = 'PlainGlobalSecret66'

  const config = `
!
radius-server host 10.1.1.1 key ${secretA}
radius-server key ${secretD}
radius server RADIUS-1
 address ipv4 10.2.2.2
 key 7 ${secretB}
interface GigabitEthernet1/0/1
 standby 1 authentication md5 key-string ${secretC}
!
`
  const intent = parseCiscoConfig(config)
  const serialized = JSON.stringify(intent)

  // None of the plaintext secrets should appear anywhere in normalized intent
  assert.equal(serialized.includes(secretA), false, 'Legacy RADIUS secret must not be in intent')
  assert.equal(serialized.includes(secretB), false, 'Modern RADIUS secret must not be in intent')
  assert.equal(serialized.includes(secretC), false, 'Interface secret must not be in intent')
  assert.equal(serialized.includes(secretD), false, 'Global secret must not be in intent')
})
