// Normalized Switch Intent tests
import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  INTENT_SCHEMA_VERSION,
  createEmptyIntent,
  createFinding,
  createSourceRef,
  isValidIntent,
} from './switch/intent/index.ts'

test('1. Schema version is exposed and stable', () => {
  assert.equal(INTENT_SCHEMA_VERSION, '1.0.0')

  const intent = createEmptyIntent()
  assert.equal(intent.schemaVersion, '1.0.0')
})

test('2. Empty intent has required structure with no fabricated data', () => {
  const intent = createEmptyIntent()

  // Schema and source present
  assert.equal(typeof intent.schemaVersion, 'string')
  assert.equal(intent.source.vendor, 'hpe_aruba')
  assert.equal(intent.source.deviceName, undefined)
  assert.equal(intent.source.hardwareSku, undefined)
  assert.equal(intent.source.osVersion, undefined)

  // Empty collections
  assert.equal(intent.vlans.length, 0)
  assert.equal(intent.interfaces.length, 0)
  assert.equal(intent.lags.length, 0)
  assert.equal(intent.svis.length, 0)
  assert.equal(intent.acls.length, 0)
  assert.equal(intent.vrfs.length, 0)

  // Coverage initialized
  assert.equal(intent.coverage.totalLines, 0)
  assert.equal(intent.coverage.parsedLines, 0)
  assert.equal(intent.coverage.unparsedLines, 0)
  assert.equal(intent.coverage.coveragePercent, 0)

  // No findings or unparsed lines
  assert.equal(intent.findings.length, 0)
  assert.equal(intent.unparsedLines.length, 0)
})

test('3. Empty intent accepts partial source platform', () => {
  const intent = createEmptyIntent({
    vendor: 'cisco',
    osFamilyName: 'IOS XE',
    osVersion: '16.12.4',
    hardwareModel: 'Catalyst 3850',
    hardwareSku: 'WS-C3850-48P',
    deviceName: 'CORE-SW-01',
    inputFileName: 'core-sw-01.cfg',
  })

  assert.equal(intent.source.vendor, 'cisco')
  assert.equal(intent.source.osFamilyName, 'IOS XE')
  assert.equal(intent.source.osVersion, '16.12.4')
  assert.equal(intent.source.hardwareModel, 'Catalyst 3850')
  assert.equal(intent.source.hardwareSku, 'WS-C3850-48P')
  assert.equal(intent.source.deviceName, 'CORE-SW-01')
  assert.equal(intent.source.inputFileName, 'core-sw-01.cfg')
})

test('4. Valid intent with VLANs, interfaces, LAG, SVI, and static routes', () => {
  const intent = createEmptyIntent({ vendor: 'hpe_aruba' })

  // Add VLANs
  intent.vlans.push({
    vlanId: 10,
    name: 'DATA',
    description: 'Data VLAN',
    adminState: 'up',
    sourceRefs: [createSourceRef(5, 7, 'vlan 10\n  name DATA\n  description Data VLAN')],
  })

  intent.vlans.push({
    vlanId: 20,
    name: 'VOICE',
    sourceRefs: [createSourceRef(9, 10, 'vlan 20\n  name VOICE')],
  })

  // Add interfaces
  intent.interfaces.push({
    sourceInterfaceId: '1/1/1',
    role: 'access',
    adminState: 'up',
    description: 'Access port to workstation',
    accessVlan: 10,
    voiceVlan: 20,
    sourceRefs: [createSourceRef(15, 19)],
  })

  intent.interfaces.push({
    sourceInterfaceId: '1/1/48',
    role: 'trunk',
    adminState: 'up',
    description: 'Trunk to distribution',
    trunkNativeVlan: 1,
    trunkAllowedVlans: [{ start: 10, end: 20 }, { start: 99 }],
    sourceRefs: [createSourceRef(25, 29)],
  })

  // Add LAG
  intent.lags.push({
    sourceInterfaceId: 'lag1',
    memberInterfaces: ['1/1/49', '1/1/50'],
    lacpMode: 'active',
    role: 'trunk',
    adminState: 'up',
    trunkAllowedVlans: [{ start: 1, end: 4094 }],
    sourceRefs: [createSourceRef(35, 40)],
  })

  // Add SVI
  intent.svis.push({
    vlanId: 10,
    ipAddresses: [{ address: '10.10.10.1', prefixLength: 24, type: 'primary' }],
    adminState: 'up',
    description: 'Data VLAN SVI',
    sourceRefs: [createSourceRef(45, 48)],
  })

  // Add routing
  intent.routing = {
    staticRoutes: [
      {
        destinationPrefix: '0.0.0.0/0',
        nextHop: '192.168.1.1',
        sourceRefs: [createSourceRef(52)],
      },
      {
        destinationPrefix: '172.16.0.0/16',
        nextHop: '10.10.10.254',
        adminDistance: 10,
        sourceRefs: [createSourceRef(53)],
      },
    ],
    sourceRefs: [createSourceRef(50, 53)],
  }

  // Update coverage
  intent.coverage = {
    totalLines: 100,
    parsedLines: 85,
    unparsedLines: 15,
    coveragePercent: 85,
  }

  // Validate structure
  assert.equal(intent.vlans.length, 2)
  assert.equal(intent.interfaces.length, 2)
  assert.equal(intent.lags.length, 1)
  assert.equal(intent.svis.length, 1)
  assert.equal(intent.routing?.staticRoutes.length, 2)

  assert.equal(intent.vlans[0].vlanId, 10)
  assert.equal(intent.vlans[0].name, 'DATA')
  assert.equal(intent.interfaces[0].sourceInterfaceId, '1/1/1')
  assert.equal(intent.interfaces[0].accessVlan, 10)
  assert.equal(intent.interfaces[0].voiceVlan, 20)
  assert.equal(intent.lags[0].memberInterfaces.length, 2)
  assert.equal(intent.svis[0].ipAddresses[0].address, '10.10.10.1')
  assert.equal(intent.routing.staticRoutes[0].destinationPrefix, '0.0.0.0/0')
})

test('5. Source references support line ranges and multiple references', () => {
  const ref1 = createSourceRef(10)
  assert.equal(ref1.startLine, 10)
  assert.equal(ref1.endLine, undefined)

  const ref2 = createSourceRef(15, 20, 'interface 1/1/1', 'interfaces')
  assert.equal(ref2.startLine, 15)
  assert.equal(ref2.endLine, 20)
  assert.equal(ref2.originalText, 'interface 1/1/1')
  assert.equal(ref2.context, 'interfaces')

  // Multiple references for one semantic object
  const vlan = {
    vlanId: 100,
    name: 'GUEST',
    sourceRefs: [
      createSourceRef(5, 7, 'vlan 100'),
      createSourceRef(120, 122, 'interface vlan 100'),
    ],
  }

  assert.equal(vlan.sourceRefs.length, 2)
  assert.equal(vlan.sourceRefs[0].startLine, 5)
  assert.equal(vlan.sourceRefs[1].startLine, 120)
})

test('6. Findings distinguish unknown, unsupported, and not-implemented states', () => {
  const intent = createEmptyIntent()

  // Unknown command
  intent.findings.push(
    createFinding(
      'UNKNOWN_COMMAND',
      'warning',
      'Unrecognized command: show-tech-support-auto-upload',
      createSourceRef(10, undefined, 'show-tech-support-auto-upload')
    )
  )

  // Unsupported feature
  intent.findings.push(
    createFinding(
      'UNSUPPORTED_FEATURE',
      'error',
      'QoS policy-map not supported in normalized intent schema',
      createSourceRef(25, 30)
    )
  )

  // Parser not implemented
  intent.findings.push(
    createFinding(
      'PARSER_NOT_IMPLEMENTED',
      'info',
      'LLDP configuration parsing not yet implemented',
      createSourceRef(50, 55)
    )
  )

  // Ambiguous syntax
  intent.findings.push(
    createFinding('AMBIGUOUS_SYNTAX', 'warning', 'VLAN range syntax ambiguous without context')
  )

  assert.equal(intent.findings.length, 4)
  assert.equal(intent.findings[0].code, 'UNKNOWN_COMMAND')
  assert.equal(intent.findings[1].code, 'UNSUPPORTED_FEATURE')
  assert.equal(intent.findings[2].code, 'PARSER_NOT_IMPLEMENTED')
  assert.equal(intent.findings[3].code, 'AMBIGUOUS_SYNTAX')

  assert.equal(intent.findings[0].severity, 'warning')
  assert.equal(intent.findings[1].severity, 'error')
  assert.equal(intent.findings[2].severity, 'info')
})

test('7. Unparsed content tracked separately from findings', () => {
  const intent = createEmptyIntent()

  intent.unparsedLines.push({
    lineNumber: 15,
    text: 'crypto pki trustpoint TP-self-signed-123456789',
    reason: 'Crypto configuration not supported',
  })

  intent.unparsedLines.push({
    lineNumber: 16,
    text: ' enrollment selfsigned',
  })

  intent.unparsedLines.push({
    lineNumber: 78,
    text: 'spanning-tree bpduguard enable',
    reason: 'Per-interface STP settings not yet implemented',
  })

  assert.equal(intent.unparsedLines.length, 3)
  assert.equal(intent.unparsedLines[0].lineNumber, 15)
  assert.equal(intent.unparsedLines[0].reason, 'Crypto configuration not supported')
  assert.equal(intent.unparsedLines[1].lineNumber, 16)
  assert.equal(intent.unparsedLines[1].reason, undefined)
})

test('8. ACL entries preserve ordering and canNormalize status', () => {
  const intent = createEmptyIntent()

  intent.acls.push({
    name: 'PERMIT_SSH',
    aclType: 'ipv4',
    entries: [
      {
        sequenceNumber: 10,
        action: 'permit',
        protocol: 'tcp',
        sourceAddress: { address: '10.0.0.0', prefixLength: 8 },
        destinationAddress: { address: 'any' },
        destinationPorts: [{ start: 22 }],
        canNormalize: true,
        sourceRefs: [createSourceRef(100)],
      },
      {
        sequenceNumber: 20,
        action: 'permit',
        protocol: 'tcp',
        sourceAddress: { address: '192.168.0.0', wildcardMask: '0.0.255.255' },
        destinationPorts: [{ start: 22 }],
        canNormalize: true,
        sourceRefs: [createSourceRef(101)],
      },
      {
        sequenceNumber: 30,
        action: 'deny',
        protocol: 'ip',
        sourceAddress: { address: 'any' },
        destinationAddress: { address: 'any' },
        canNormalize: true,
        sourceRefs: [createSourceRef(102)],
      },
    ],
    sourceRefs: [createSourceRef(99, 102)],
  })

  // ACL with entry that cannot be normalized
  intent.acls.push({
    name: 'COMPLEX_ACL',
    entries: [
      {
        action: 'permit',
        protocol: 'tcp',
        flags: ['established', 'rst'],
        canNormalize: false,
        normalizationNote: 'Flag combination not supported by target platform',
        sourceRefs: [createSourceRef(110)],
      },
    ],
    sourceRefs: [createSourceRef(109, 111)],
  })

  assert.equal(intent.acls.length, 2)
  assert.equal(intent.acls[0].entries.length, 3)
  assert.equal(intent.acls[0].entries[0].sequenceNumber, 10)
  assert.equal(intent.acls[0].entries[1].sequenceNumber, 20)
  assert.equal(intent.acls[0].entries[2].sequenceNumber, 30)
  assert.equal(intent.acls[0].entries[0].canNormalize, true)
  assert.equal(intent.acls[1].entries[0].canNormalize, false)
  assert.equal(intent.acls[1].entries[0].normalizationNote, 'Flag combination not supported by target platform')
})

test('9. Source interface IDs remain distinct from target mapping', () => {
  const intent = createEmptyIntent({
    vendor: 'cisco',
    hardwareModel: 'Catalyst 3850',
  })

  intent.interfaces.push({
    sourceInterfaceId: 'GigabitEthernet1/0/1',
    role: 'access',
    adminState: 'up',
    accessVlan: 10,
    sourceRefs: [createSourceRef(50)],
  })

  intent.interfaces.push({
    sourceInterfaceId: 'TenGigabitEthernet1/1/1',
    role: 'trunk',
    adminState: 'up',
    sourceRefs: [createSourceRef(60)],
  })

  // Source IDs preserve original naming
  assert.equal(intent.interfaces[0].sourceInterfaceId, 'GigabitEthernet1/0/1')
  assert.equal(intent.interfaces[1].sourceInterfaceId, 'TenGigabitEthernet1/1/1')

  // No target interface ID field exists in intent
  assert.equal('targetInterfaceId' in intent.interfaces[0], false)
})

test('10. Optional values remain unknown without fabricated defaults', () => {
  const intent = createEmptyIntent()

  // VLAN with minimal info
  intent.vlans.push({
    vlanId: 99,
    sourceRefs: [createSourceRef(10)],
  })

  // Interface with minimal info
  intent.interfaces.push({
    sourceInterfaceId: '1/1/10',
    role: 'unknown',
    adminState: 'unknown',
    sourceRefs: [createSourceRef(20)],
  })

  // SVI without IP
  intent.svis.push({
    vlanId: 99,
    ipAddresses: [],
    adminState: 'down',
    sourceRefs: [createSourceRef(30)],
  })

  assert.equal(intent.vlans[0].name, undefined)
  assert.equal(intent.vlans[0].description, undefined)
  assert.equal(intent.interfaces[0].description, undefined)
  assert.equal(intent.interfaces[0].accessVlan, undefined)
  assert.equal(intent.interfaces[0].speed, undefined)
  assert.equal(intent.svis[0].ipAddresses.length, 0)
  assert.equal(intent.svis[0].description, undefined)
})

test('11. isValidIntent type guard validates structure', () => {
  const validIntent = createEmptyIntent()
  assert.equal(isValidIntent(validIntent), true)

  // Invalid objects
  assert.equal(isValidIntent(null), false)
  assert.equal(isValidIntent(undefined), false)
  assert.equal(isValidIntent({}), false)
  assert.equal(isValidIntent({ schemaVersion: '1.0.0' }), false)
  assert.equal(isValidIntent({ source: {}, vlans: [] }), false)

  // Valid-looking but missing required fields
  const incomplete = {
    schemaVersion: '1.0.0',
    source: { vendor: 'hpe_aruba' },
    vlans: [],
    interfaces: [],
    // missing coverage and findings
  }
  assert.equal(isValidIntent(incomplete), false)
})

test('12. VRF and STP configuration preserved', () => {
  const intent = createEmptyIntent()

  // Add VRF
  intent.vrfs.push({
    name: 'MGMT',
    description: 'Management VRF',
    routeDistinguisher: '65000:100',
    interfaces: ['vlan100', '1/1/1'],
    sourceRefs: [createSourceRef(200, 205)],
  })

  // Add STP
  intent.stp = {
    mode: 'rapid-pvst',
    bridgePriority: 4096,
    instances: [
      {
        instanceId: 10,
        vlans: [10, 20, 30],
        priority: 8192,
        sourceRefs: [createSourceRef(250)],
      },
    ],
    sourceRefs: [createSourceRef(240, 260)],
  }

  assert.equal(intent.vrfs.length, 1)
  assert.equal(intent.vrfs[0].name, 'MGMT')
  assert.equal(intent.vrfs[0].interfaces.length, 2)
  assert.equal(intent.stp?.mode, 'rapid-pvst')
  assert.equal(intent.stp?.instances?.[0].vlans?.length, 3)
})

test('13. VSF topology with capability assessment', () => {
  const intent = createEmptyIntent()

  intent.vsf = {
    enabled: true,
    members: [
      {
        memberId: '1',
        role: 'primary',
        priority: 255,
        sourceRefs: [createSourceRef(300)],
      },
      {
        memberId: '2',
        role: 'secondary',
        priority: 200,
        sourceRefs: [createSourceRef(305)],
      },
    ],
    capability: 'review-required',
    sourceRefs: [createSourceRef(299, 310)],
  }

  assert.equal(intent.vsf.enabled, true)
  assert.equal(intent.vsf.members.length, 2)
  assert.equal(intent.vsf.members[0].role, 'primary')
  assert.equal(intent.vsf.capability, 'review-required')
})

test('14. Extensions mechanism for unsupported features', () => {
  const intent = createEmptyIntent()

  intent.extensions = {
    lldp: {
      enabled: true,
      transmitInterval: 30,
    },
    qos: {
      globalTrustMode: 'dscp',
    },
  }

  assert.equal(typeof intent.extensions, 'object')
  assert.ok(intent.extensions?.lldp)
  assert.equal(intent.extensions.lldp.enabled, true)
})

// ===== NAC (Network Access Control) Tests =====

test('15. Empty intent has no NAC configuration by default', () => {
  const intent = createEmptyIntent()
  assert.equal(intent.nac, undefined)
})

test('16. NAC intent with RADIUS servers and server groups', () => {
  const intent = createEmptyIntent({ vendor: 'cisco', osFamilyName: 'IOS XE' })

  intent.nac = {
    radiusServers: [
      {
        id: 'radius-1',
        address: '10.1.1.10',
        authPort: 1812,
        acctPort: 1813,
        key: { configured: true, keyReference: 'key-1' },
        timeout: 5,
        retransmit: 3,
        sourceRefs: [createSourceRef(100, 105)],
      },
      {
        id: 'radius-2',
        address: '10.1.1.11',
        key: { configured: true },
        sourceRefs: [createSourceRef(110, 112)],
      },
    ],
    radiusServerGroups: [
      {
        name: 'CLEARPASS',
        serverIds: ['radius-1', 'radius-2'],
        sourceRefs: [createSourceRef(120, 125)],
      },
    ],
    sourceRefs: [createSourceRef(100, 125)],
  }

  assert.equal(intent.nac.radiusServers.length, 2)
  assert.equal(intent.nac.radiusServers[0].id, 'radius-1')
  assert.equal(intent.nac.radiusServers[0].address, '10.1.1.10')
  assert.equal(intent.nac.radiusServers[0].authPort, 1812)
  assert.equal(intent.nac.radiusServers[0].key.configured, true)
  assert.equal(intent.nac.radiusServers[0].key.keyReference, 'key-1')

  assert.equal(intent.nac.radiusServerGroups.length, 1)
  assert.equal(intent.nac.radiusServerGroups[0].name, 'CLEARPASS')
  assert.equal(intent.nac.radiusServerGroups[0].serverIds.length, 2)
})

test('17. RADIUS secrets never contain plaintext', () => {
  const intent = createEmptyIntent()

  intent.nac = {
    radiusServers: [
      {
        id: 'radius-1',
        address: '10.1.1.10',
        key: { configured: true, keyReference: 'named-key' },
        sourceRefs: [createSourceRef(10)],
      },
      {
        id: 'radius-2',
        address: '10.1.1.11',
        key: { configured: false },
        sourceRefs: [createSourceRef(15)],
      },
    ],
    radiusServerGroups: [],
    sourceRefs: [createSourceRef(10, 15)],
  }

  // Verify no plaintext secret field exists
  const server1 = intent.nac.radiusServers[0]
  assert.equal('secret' in server1.key, false)
  assert.equal('sharedSecret' in server1.key, false)
  assert.equal('plaintext' in server1.key, false)
  assert.equal(server1.key.configured, true)
  assert.equal(server1.key.keyReference, 'named-key')

  const server2 = intent.nac.radiusServers[1]
  assert.equal(server2.key.configured, false)
})

test('18. AAA method lists with ordered methods', () => {
  const intent = createEmptyIntent({ vendor: 'cisco' })

  intent.nac = {
    radiusServers: [],
    radiusServerGroups: [],
    aaa: {
      authentication: {
        defaultMethodList: {
          methods: [
            { type: 'group', groupName: 'CLEARPASS' },
            { type: 'local' },
          ],
          sourceRefs: [createSourceRef(200)],
        },
        namedMethodLists: {
          'DOT1X': {
            name: 'DOT1X',
            methods: [{ type: 'group', groupName: 'CLEARPASS' }],
            sourceRefs: [createSourceRef(205)],
          },
        },
        sourceRefs: [createSourceRef(200, 205)],
      },
      authorization: {
        defaultMethodList: {
          methods: [{ type: 'group', groupName: 'CLEARPASS' }],
          sourceRefs: [createSourceRef(210)],
        },
        namedMethodLists: {},
        sourceRefs: [createSourceRef(210)],
      },
      sourceRefs: [createSourceRef(200, 210)],
    },
    sourceRefs: [createSourceRef(200, 210)],
  }

  assert.equal(intent.nac.aaa?.authentication?.defaultMethodList?.methods.length, 2)
  assert.equal(intent.nac.aaa?.authentication?.defaultMethodList?.methods[0].type, 'group')
  assert.equal(intent.nac.aaa?.authentication?.defaultMethodList?.methods[1].type, 'local')
  assert.equal(intent.nac.aaa?.authorization?.defaultMethodList?.methods[0].type, 'group')
})

test('19. Interface 802.1X and MAB configuration', () => {
  const intent = createEmptyIntent({ vendor: 'cisco' })

  intent.interfaces.push({
    sourceInterfaceId: 'GigabitEthernet1/0/1',
    role: 'access',
    adminState: 'up',
    authentication: {
      dot1x: {
        enabled: true,
        pae: 'authenticator',
        timeout: {
          txPeriod: 30,
          quietPeriod: 60,
          serverTimeout: 30,
          reauthPeriod: 3600,
          sourceRefs: [createSourceRef(310)],
        },
        sourceRefs: [createSourceRef(305, 310)],
      },
      mab: {
        enabled: true,
        sourceRefs: [createSourceRef(315)],
      },
      portControl: 'auto',
      hostMode: 'multi-auth',
      authenticationOrder: ['dot1x', 'mab'],
      authenticationPriority: ['dot1x', 'mab'],
      reauthentication: {
        enabled: true,
        period: 3600,
        sourceRefs: [createSourceRef(320)],
      },
      violation: 'restrict',
      maxClients: 8,
      authorizationAttributes: {
        dynamicVlan: { enabled: true, sourceRefs: [createSourceRef(325)] },
        downloadableAcl: { enabled: true, sourceRefs: [createSourceRef(330)] },
        filterId: { enabled: true, sourceRefs: [createSourceRef(335)] },
        sourceRefs: [createSourceRef(325, 335)],
      },
      sourceRefs: [createSourceRef(300, 340)],
    },
    sourceRefs: [createSourceRef(300, 340)],
  })

  const iface = intent.interfaces[0]
  assert.equal(iface.authentication?.dot1x?.enabled, true)
  assert.equal(iface.authentication?.dot1x?.pae, 'authenticator')
  assert.equal(iface.authentication?.mab?.enabled, true)
  assert.equal(iface.authentication?.portControl, 'auto')
  assert.equal(iface.authentication?.hostMode, 'multi-auth')
  assert.equal(iface.authentication?.authenticationOrder?.length, 2)
  assert.equal(iface.authentication?.violation, 'restrict')
  assert.equal(iface.authentication?.maxClients, 8)
})

test('20. Cisco dACL and Aruba DUR are distinct', () => {
  const intent = createEmptyIntent({ vendor: 'cisco' })

  intent.interfaces.push({
    sourceInterfaceId: 'GigabitEthernet1/0/1',
    role: 'access',
    adminState: 'up',
    authentication: {
      authorizationAttributes: {
        downloadableAcl: { enabled: true, sourceRefs: [createSourceRef(100)] },
        downloadableUserRole: { enabled: false, sourceRefs: [] },
        sourceRefs: [createSourceRef(100)],
      },
      sourceRefs: [createSourceRef(100)],
    },
    sourceRefs: [createSourceRef(100)],
  })

  const attrs = intent.interfaces[0].authentication?.authorizationAttributes
  assert.ok(attrs && 'downloadableAcl' in attrs)
  assert.ok(attrs && 'downloadableUserRole' in attrs)
  assert.equal(attrs?.downloadableAcl?.enabled, true)
  assert.equal(attrs?.downloadableUserRole?.enabled, false)
})

test('21. Change of Authorization (CoA) configuration', () => {
  const intent = createEmptyIntent({ vendor: 'cisco' })

  intent.nac = {
    radiusServers: [],
    radiusServerGroups: [],
    coa: {
      enabled: true,
      clientConfig: {
        serverAddresses: ['10.1.1.10', '10.1.1.11'],
        port: 3799,
        sourceRefs: [createSourceRef(400)],
      },
      serverConfig: {
        enabled: true,
        port: 1700,
        clientAddresses: ['10.1.1.10', '10.1.1.11'],
        sourceRefs: [createSourceRef(405)],
      },
      sourceRefs: [createSourceRef(400, 410)],
    },
    sourceRefs: [createSourceRef(400, 410)],
  }

  assert.equal(intent.nac.coa?.enabled, true)
  assert.equal(intent.nac.coa?.clientConfig?.serverAddresses.length, 2)
  assert.equal(intent.nac.coa?.clientConfig?.port, 3799)
  assert.equal(intent.nac.coa?.serverConfig?.enabled, true)
  assert.equal(intent.nac.coa?.serverConfig?.port, 1700)
})

test('22. NAC findings for unresolved references', () => {
  const intent = createEmptyIntent({ vendor: 'cisco' })

  intent.findings.push(
    createFinding(
      'NAC_UNRESOLVED_RADIUS_SERVER',
      'error',
      'RADIUS server "10.2.2.20" referenced in server group "BACKUP" not found',
      createSourceRef(150)
    )
  )

  intent.findings.push(
    createFinding(
      'NAC_UNRESOLVED_SERVER_GROUP',
      'error',
      'AAA method list references server group "LEGACY" which is not defined',
      createSourceRef(220)
    )
  )

  intent.findings.push(
    createFinding(
      'NAC_SECRET_REDACTED',
      'info',
      'RADIUS shared secret redacted from normalized intent for security',
      createSourceRef(110)
    )
  )

  intent.findings.push(
    createFinding(
      'NAC_MIGRATION_REVIEW_REQUIRED',
      'warning',
      'Cisco dACL to Aruba DUR migration requires ClearPass policy review'
    )
  )

  assert.equal(intent.findings.length, 4)
  assert.equal(intent.findings[0].code, 'NAC_UNRESOLVED_RADIUS_SERVER')
  assert.equal(intent.findings[1].code, 'NAC_UNRESOLVED_SERVER_GROUP')
  assert.equal(intent.findings[2].code, 'NAC_SECRET_REDACTED')
  assert.equal(intent.findings[3].code, 'NAC_MIGRATION_REVIEW_REQUIRED')
})

test('23. Global 802.1X and MAB configuration', () => {
  const intent = createEmptyIntent({ vendor: 'cisco' })

  intent.nac = {
    radiusServers: [],
    radiusServerGroups: [],
    dot1x: {
      enabled: true,
      systemAuthControl: true,
      sourceRefs: [createSourceRef(500)],
    },
    mab: {
      enabled: true,
      sourceRefs: [createSourceRef(505)],
    },
    sourceRefs: [createSourceRef(500, 505)],
  }

  assert.equal(intent.nac.dot1x?.enabled, true)
  assert.equal(intent.nac.dot1x?.systemAuthControl, true)
  assert.equal(intent.nac.mab?.enabled, true)
})

test('24. Backward compatibility with non-NAC intents', () => {
  const intent = createEmptyIntent()

  intent.vlans.push({
    vlanId: 10,
    name: 'DATA',
    sourceRefs: [createSourceRef(10)],
  })

  intent.interfaces.push({
    sourceInterfaceId: '1/1/1',
    role: 'access',
    adminState: 'up',
    accessVlan: 10,
    sourceRefs: [createSourceRef(20)],
  })

  assert.equal(intent.nac, undefined)
  assert.equal(intent.vlans.length, 1)
  assert.equal(intent.interfaces.length, 1)
  assert.equal(intent.interfaces[0].authentication, undefined)
  assert.equal(intent.schemaVersion, '1.0.0')
})
