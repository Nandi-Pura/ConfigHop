/**
 * Cisco IOS/IOS XE Configuration Parser
 *
 * Parses Cisco Catalyst switch configurations into normalized switch intent.
 * Supports RADIUS, AAA, 802.1X, MAB, and CoA configurations.
 *
 * Security: Never stores plaintext secrets in normalized output.
 */

import {
  createEmptyIntent,
  createFinding,
  createSourceRef,
  type NormalizedSwitchIntent,
  type RadiusServerConfig,
  type RadiusServerGroupConfig,
  type InterfaceConfig,
  type SourceReference,
  type AaaMethodList,
  type AaaMethod,
  type LacpMode,
  type StpMode,
} from '../intent/index.ts'

// ===== PARSER STATE =====

interface ParserState {
  intent: NormalizedSwitchIntent
  lines: string[]
  currentLineNumber: number
  currentContext: ConfigContext
  lineOutcomes: Map<number, 'parsed' | 'partially-understood' | 'unparsed'>

  // NAC-specific state
  radiusServers: Map<string, RadiusServerConfig>
  radiusServerGroups: Map<string, RadiusServerGroupConfig>
  interfaceConfigs: Map<string, Partial<InterfaceConfig>>
}

interface ConfigContext {
  type: 'global' | 'interface' | 'line' | 'radius-server' | 'aaa-group' | 'vlan' | 'acl' | 'unknown'
  identifier?: string  // e.g., interface name, server name, group name, vlan id
}

// ===== SECRET REDACTION & LOGGING =====

const NON_SECRET_KEYWORDS = new Set([
  'generate', 'zeroize', 'export', 'import', 'pubkey-chain', 'chain',
  'config', 'default', 'alive', 'dead', 'reauthenticate', 'periodic',
  'port-control', 'host-mode', 'violation', 'order', 'priority', 'control-direction'
])

export function redactSensitiveLine(line: string): { text: string; wasRedacted: boolean } {
  const regex = /\b(key-string|pre-shared-key|secret|password|community|key)\s+(?:(?:0|5|6|7|hash|encrypted|md5|text)\s+)?(\S+)/i
  const match = line.match(regex)
  if (match) {
    const keyword = match[1].toLowerCase()
    const secretPart = match[2]
    if (secretPart && !NON_SECRET_KEYWORDS.has(secretPart.toLowerCase())) {
      if (keyword === 'key' && line.trim().startsWith('crypto key')) {
        return { text: line, wasRedacted: false }
      }
      const replaced = line.replace(secretPart, '<redacted>')
      return { text: replaced, wasRedacted: true }
    }
  }
  return { text: line, wasRedacted: false }
}

function markLineOutcome(state: ParserState, lineNum: number, outcome: 'parsed' | 'partially-understood' | 'unparsed'): void {
  state.lineOutcomes.set(lineNum, outcome)
}

function handleUnparsedLine(state: ParserState, lineNum: number, originalLine: string, reason: string): void {
  const { text: safeText, wasRedacted } = redactSensitiveLine(originalLine)
  const { text: safeReason } = redactSensitiveLine(reason)
  if (wasRedacted) {
    state.intent.findings.push(
      createFinding(
        'NAC_SECRET_REDACTED',
        'info',
        'Secret redacted from configuration command',
        createSourceRef(lineNum)
      )
    )
  }
  state.intent.unparsedLines.push({
    lineNumber: lineNum,
    text: safeText,
    reason: safeReason,
  })
  markLineOutcome(state, lineNum, 'unparsed')
}

function handlePartiallyUnderstoodLine(
  state: ParserState,
  lineNum: number,
  originalLine: string,
  reason: string,
  findingMessage?: string
): void {
  const { text: safeText, wasRedacted } = redactSensitiveLine(originalLine)
  const { text: safeReason } = redactSensitiveLine(reason)
  const safeFindingMessage = findingMessage ? redactSensitiveLine(findingMessage).text : undefined
  if (wasRedacted) {
    state.intent.findings.push(
      createFinding(
        'NAC_SECRET_REDACTED',
        'info',
        'Secret redacted from configuration command',
        createSourceRef(lineNum)
      )
    )
  }
  state.intent.unparsedLines.push({
    lineNumber: lineNum,
    text: safeText,
    reason: safeReason,
  })
  if (safeFindingMessage) {
    state.intent.findings.push(
      createFinding(
        'UNSUPPORTED_FEATURE',
        'info',
        safeFindingMessage,
        createSourceRef(lineNum)
      )
    )
  }
  markLineOutcome(state, lineNum, 'partially-understood')
}

// ===== MAIN PARSER =====

export function parseCiscoConfig(configText: string): NormalizedSwitchIntent {
  const lines = configText.split(/\r?\n/)

  const state: ParserState = {
    intent: createEmptyIntent({ vendor: 'cisco', osFamilyName: 'IOS' }),
    lines,
    currentLineNumber: 0,
    currentContext: { type: 'global' },
    lineOutcomes: new Map(),
    radiusServers: new Map(),
    radiusServerGroups: new Map(),
    interfaceConfigs: new Map(),
  }

  // First pass: parse all configuration
  for (let i = 0; i < lines.length; i++) {
    state.currentLineNumber = i + 1
    const line = lines[i]
    const trimmed = line.trim()

    if (!trimmed || trimmed.startsWith('!')) {
      continue // Skip empty lines and comments
    }

    parseLine(state, trimmed, line)
  }

  // Second pass: build final intent
  buildFinalIntent(state)
  calculateCoverage(state)

  return state.intent
}

// ===== LINE PARSING =====

function parseLine(state: ParserState, trimmed: string, originalLine: string): void {
  const lineNum = state.currentLineNumber

  // Context management
  // LAG/Port-channel interface
  if (trimmed.startsWith('interface Port-channel')) {
    const lagName = trimmed.substring('interface '.length).trim()
    state.currentContext = { type: 'interface', identifier: lagName }

    // Add LAG to intent if not exists
    const existingLag = state.intent.lags.find(l => l.sourceInterfaceId === lagName)
    if (!existingLag) {
      state.intent.lags.push({
        sourceInterfaceId: lagName,
        memberInterfaces: [],
        lacpMode: 'unknown',
        adminState: 'unknown',
        sourceRefs: [createSourceRef(lineNum)],
      })
    }

    // Also add interface config
    if (!state.interfaceConfigs.has(lagName)) {
      state.interfaceConfigs.set(lagName, {
        sourceInterfaceId: lagName,
        role: 'unknown',
        adminState: 'unknown',
        sourceRefs: [createSourceRef(lineNum)],
      })
    }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // SVI (VLAN interface)
  if (trimmed.toLowerCase().startsWith('interface vlan')) {
    const vlanIdStr = trimmed.substring('interface vlan'.length).trim()
    const vlanId = parseInt(vlanIdStr, 10)
    if (!isNaN(vlanId)) {
      state.currentContext = { type: 'interface', identifier: `Vlan${vlanId}` }

      // Add SVI to intent if not exists
      const existingSvi = state.intent.svis.find(s => s.vlanId === vlanId)
      if (!existingSvi) {
        state.intent.svis.push({
          vlanId,
          ipAddresses: [],
          adminState: 'up',
          sourceRefs: [createSourceRef(lineNum)],
        })
      }

      markLineOutcome(state, lineNum, 'parsed')
      return
    }
  }

  if (trimmed.startsWith('interface ')) {
    const interfaceName = trimmed.substring('interface '.length).trim()
    state.currentContext = { type: 'interface', identifier: interfaceName }
    if (!state.interfaceConfigs.has(interfaceName)) {
      state.interfaceConfigs.set(interfaceName, {
        sourceInterfaceId: interfaceName,
        role: 'unknown',
        adminState: 'unknown',
        sourceRefs: [createSourceRef(lineNum)],
      })
    }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  if (trimmed.startsWith('radius server ')) {
    const name = trimmed.substring('radius server '.length).trim()
    state.currentContext = { type: 'radius-server', identifier: name }
    parseRadiusServer(state, trimmed, lineNum)
    return
  }

  if (trimmed.startsWith('aaa group server radius ')) {
    const name = trimmed.substring('aaa group server radius '.length).trim()
    state.currentContext = { type: 'aaa-group', identifier: name }
    parseAaaGroupServer(state, trimmed, lineNum)
    return
  }

  if (trimmed.startsWith('line ')) {
    state.currentContext = { type: 'line', identifier: trimmed }
    handleUnparsedLine(state, lineNum, originalLine, 'Line configuration not parsed')
    return
  }

  if (trimmed === 'end' || trimmed === 'exit') {
    state.currentContext = { type: 'global' }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // Non-indented line exits sub-context back to global
  const isIndented = originalLine.startsWith(' ') || originalLine.startsWith('\t')
  if (!isIndented && state.currentContext.type !== 'global') {
    state.currentContext = { type: 'global' }
  }

  // Dispatch commands based on context
  if (state.currentContext.type === 'global') {
    parseGlobalCommand(state, trimmed, originalLine)
  } else if (state.currentContext.type === 'interface') {
    parseInterfaceCommand(state, trimmed, originalLine)
  } else if (state.currentContext.type === 'radius-server') {
    parseRadiusServerSubcommand(state, trimmed, originalLine)
  } else if (state.currentContext.type === 'aaa-group') {
    parseAaaGroupSubcommand(state, trimmed, originalLine)
  } else if (state.currentContext.type === 'vlan') {
    parseVlanSubcommand(state, trimmed, originalLine)
  } else if (state.currentContext.type === 'acl') {
    parseAclSubcommand(state, trimmed, originalLine)
  } else {
    handleUnparsedLine(state, lineNum, originalLine, `Unsupported command in context ${state.currentContext.type}: ${trimmed}`)
  }
}

function parseGlobalCommand(state: ParserState, trimmed: string, originalLine: string): void {
  const lineNum = state.currentLineNumber

  // Hostname
  if (trimmed.startsWith('hostname ')) {
    const hostname = trimmed.substring('hostname '.length).trim()
    if (!state.intent.system) {
      state.intent.system = {
        hostname,
        dnsServers: [],
        ntpServers: [],
        sourceRefs: [createSourceRef(lineNum)],
      }
    } else {
      state.intent.system.hostname = hostname
    }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // AAA new-model
  if (trimmed === 'aaa new-model') {
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // RADIUS server (modern syntax)
  if (trimmed.startsWith('radius server ')) {
    parseRadiusServer(state, trimmed, lineNum)
    return
  }

  // RADIUS host (legacy syntax)
  if (trimmed.startsWith('radius-server host ')) {
    parseRadiusHostLegacy(state, trimmed, lineNum)
    return
  }

  // RADIUS server key (legacy)
  if (trimmed.startsWith('radius-server key ')) {
    parseRadiusServerKey(state, trimmed, lineNum)
    return
  }

  // AAA group server
  if (trimmed.startsWith('aaa group server radius ')) {
    parseAaaGroupServer(state, trimmed, lineNum)
    return
  }

  // AAA authentication
  if (trimmed.startsWith('aaa authentication ')) {
    parseAaaAuthentication(state, trimmed, lineNum)
    return
  }

  // AAA authorization
  if (trimmed.startsWith('aaa authorization ')) {
    parseAaaAuthorization(state, trimmed, lineNum)
    return
  }

  // AAA accounting
  if (trimmed.startsWith('aaa accounting ')) {
    parseAaaAccounting(state, trimmed, lineNum)
    return
  }

  // 802.1X system-auth-control
  if (trimmed === 'dot1x system-auth-control') {
    ensureNacConfig(state)
    if (!state.intent.nac!.dot1x) {
      state.intent.nac!.dot1x = {
        enabled: true,
        systemAuthControl: true,
        sourceRefs: [createSourceRef(lineNum)],
      }
    } else {
      state.intent.nac!.dot1x.systemAuthControl = true
    }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // CoA server / dynamic-author
  // Format: aaa server radius dynamic-author
  if (trimmed === 'aaa server radius dynamic-author') {
    ensureNacConfig(state)
    if (!state.intent.nac!.coa) {
      state.intent.nac!.coa = {
        enabled: true,
        serverConfig: {
          enabled: true,
          sourceRefs: [createSourceRef(lineNum)],
        },
        sourceRefs: [createSourceRef(lineNum)],
      }
    } else {
      state.intent.nac!.coa.enabled = true
      if (!state.intent.nac!.coa.serverConfig) {
        state.intent.nac!.coa.serverConfig = {
          enabled: true,
          sourceRefs: [createSourceRef(lineNum)],
        }
      } else {
        state.intent.nac!.coa.serverConfig.enabled = true
      }
    }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // aaa server radius dynamic-author subcommands if unindented or global
  if (trimmed.startsWith('client ') && (state.intent.nac?.coa?.serverConfig)) {
    const parts = trimmed.substring('client '.length).trim().split(/\s+/)
    const clientIp = parts[0]
    const serverCfg = state.intent.nac.coa.serverConfig
    if (!serverCfg.clientAddresses) serverCfg.clientAddresses = []
    if (!serverCfg.clientAddresses.includes(clientIp)) {
      serverCfg.clientAddresses.push(clientIp)
    }
    serverCfg.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  if (trimmed.startsWith('port ') && (state.intent.nac?.coa?.serverConfig)) {
    const port = parseInt(trimmed.substring('port '.length).trim(), 10)
    state.intent.nac.coa.serverConfig.port = port
    state.intent.nac.coa.serverConfig.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // STP mode
  if (trimmed.startsWith('spanning-tree mode ')) {
    const mode = trimmed.substring('spanning-tree mode '.length).trim()
    if (!state.intent.stp) {
      state.intent.stp = {
        mode: 'unknown',
        sourceRefs: [createSourceRef(lineNum)],
      }
    }
    state.intent.stp.mode = normalizeStpMode(mode)
    state.intent.stp.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // VLAN definition
  if (trimmed.startsWith('vlan ')) {
    const vlanIdStr = trimmed.substring('vlan '.length).trim()
    const vlanId = parseInt(vlanIdStr, 10)
    if (!isNaN(vlanId)) {
      // Check if VLAN already exists
      const existingVlan = state.intent.vlans.find(v => v.vlanId === vlanId)
      if (!existingVlan) {
        state.intent.vlans.push({
          vlanId,
          sourceRefs: [createSourceRef(lineNum)],
        })
      }
      // Set context for VLAN subcommands
      state.currentContext = { type: 'vlan', identifier: vlanIdStr }
      markLineOutcome(state, lineNum, 'parsed')
      return
    }
  }

  // ACL definition (global)
  if (trimmed.startsWith('ip access-list ')) {
    const aclParts = trimmed.substring('ip access-list '.length).trim().split(/\s+/)
    const aclType = aclParts[0] // e.g., "extended" or "standard"
    const aclName = aclParts.slice(1).join(' ') // e.g., "SECURE-ACL"
    if (aclName) {
      const existingAcl = state.intent.acls.find(a => a.name === aclName)
      if (!existingAcl) {
        state.intent.acls.push({
          name: aclName,
          aclType: aclType === 'extended' ? 'ipv4' : 'ipv4',
          entries: [],
          sourceRefs: [createSourceRef(lineNum)],
        })
      }
      state.currentContext = { type: 'acl', identifier: aclName }
      markLineOutcome(state, lineNum, 'parsed')
      return
    }
  }

  // Unknown global command - add to unparsed
  handleUnparsedLine(state, lineNum, originalLine, 'Unknown or unsupported global command')
}

// ===== VLAN PARSING =====

function parseVlanSubcommand(state: ParserState, trimmed: string, originalLine: string): void {
  const lineNum = state.currentLineNumber
  const vlanIdStr = state.currentContext.identifier!
  const vlanId = parseInt(vlanIdStr, 10)

  // Find the VLAN in our intent
  const vlan = state.intent.vlans.find(v => v.vlanId === vlanId)
  if (!vlan) {
    handleUnparsedLine(state, lineNum, originalLine, `VLAN ${vlanId} not found in intent`)
    return
  }

  // VLAN name
  if (trimmed.startsWith('name ')) {
    const name = trimmed.substring('name '.length).trim()
    vlan.name = name
    vlan.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // Other VLAN subcommands can be added here
  handleUnparsedLine(state, lineNum, originalLine, 'Unsupported VLAN subcommand')
}


// ===== ACL PARSING =====

function parseAclSubcommand(state: ParserState, trimmed: string, originalLine: string): void {
  const lineNum = state.currentLineNumber
  const aclName = state.currentContext.identifier!

  const acl = state.intent.acls.find(a => a.name === aclName)
  if (!acl) {
    handleUnparsedLine(state, lineNum, originalLine, `ACL ${aclName} not found`)
    return
  }

  // Parse ACL entry (permit/deny)
  if (trimmed.match(/^(permit|deny)\s+/)) {
    acl.entries.push({
      sequenceNumber: acl.entries.length + 10,
      action: trimmed.split(/\s+/)[0] as any,
      protocol: 'ip' as any,
      sourceAddress: { address: '0.0.0.0', wildcardMask: '0.0.0.0' },
      destinationAddress: { address: '0.0.0.0', wildcardMask: '0.0.0.0' },
      canNormalize: false,
      sourceRefs: [createSourceRef(lineNum)],
    })
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  handleUnparsedLine(state, lineNum, originalLine, `Unsupported ACL subcommand: ${trimmed}`)
}


// ===== INTERFACE PARSING =====

function parseInterfaceCommand(state: ParserState, trimmed: string, originalLine: string): void {
  const lineNum = state.currentLineNumber
  const interfaceName = state.currentContext.identifier!

  // Get or create interface config
  if (!state.interfaceConfigs.has(interfaceName)) {
    state.interfaceConfigs.set(interfaceName, {
      sourceInterfaceId: interfaceName,
      role: 'unknown',
      adminState: 'unknown',
      sourceRefs: [],
    })
  }

  const iface = state.interfaceConfigs.get(interfaceName)!

  // Channel-group for LAG
  if (trimmed.startsWith('channel-group ')) {
    const match = trimmed.match(/channel-group\s+(\d+)\s+mode\s+(\S+)/)
    if (match) {
      const groupId = parseInt(match[1], 10)
      const mode = match[2]
      const lagName = `Port-channel${groupId}`

      // Add member interface to LAG
      const existingLag = state.intent.lags.find(l => l.sourceInterfaceId === lagName)
      if (!existingLag) {
        state.intent.lags.push({
          sourceInterfaceId: lagName,
          memberInterfaces: [interfaceName],
          lacpMode: normalizeLacpMode(mode),
          adminState: 'unknown',
          sourceRefs: [createSourceRef(lineNum)],
        })
      } else {
        if (!existingLag.memberInterfaces.includes(interfaceName)) {
          existingLag.memberInterfaces.push(interfaceName)
          existingLag.sourceRefs.push(createSourceRef(lineNum))
        }
        if (existingLag.lacpMode === 'unknown') existingLag.lacpMode = normalizeLacpMode(mode)
      }

      markLineOutcome(state, lineNum, 'parsed')
      return
    }
  }

  // Switchport mode
  if (trimmed === 'switchport mode access') {
    iface.role = 'access'
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  if (trimmed === 'switchport mode trunk') {
    iface.role = 'trunk'
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // 802.1X port-control
  if (trimmed.startsWith('authentication port-control ')) {
    const mode = trimmed.substring('authentication port-control '.length).trim()
    ensureInterfaceAuth(iface)
    iface.authentication!.portControl = normalizePortControl(mode)
    if (!iface.authentication!.sourceRefs) iface.authentication!.sourceRefs = []
    iface.authentication!.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // 802.1X host-mode
  if (trimmed.startsWith('authentication host-mode ')) {
    const mode = trimmed.substring('authentication host-mode '.length).trim()
    ensureInterfaceAuth(iface)
    iface.authentication!.hostMode = normalizeHostMode(mode)
    if (!iface.authentication!.sourceRefs) iface.authentication!.sourceRefs = []
    iface.authentication!.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // 802.1X pae
  if (trimmed === 'dot1x pae authenticator') {
    ensureInterfaceAuth(iface)
    if (!iface.authentication!.dot1x) {
      iface.authentication!.dot1x = {
        enabled: true,
        pae: 'authenticator',
        sourceRefs: [createSourceRef(lineNum)],
      }
    } else {
      iface.authentication!.dot1x.pae = 'authenticator'
    }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // MAB - DO NOT conflate with authentication open
  if (trimmed === 'mab') {
    ensureInterfaceAuth(iface)
    if (!iface.authentication!.mab) {
      iface.authentication!.mab = {
        enabled: true,
        sourceRefs: [createSourceRef(lineNum)],
      }
    } else {
      iface.authentication!.mab.enabled = true
      iface.authentication!.mab.sourceRefs.push(createSourceRef(lineNum))
    }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // Open authentication - distinct from MAB
  if (trimmed === 'authentication open') {
    ensureInterfaceAuth(iface)
    iface.authentication!.openAuthentication = true
    if (!iface.authentication!.sourceRefs) iface.authentication!.sourceRefs = []
    iface.authentication!.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // Authentication order
  if (trimmed.startsWith('authentication order ')) {
    const orderStr = trimmed.substring('authentication order '.length).trim()
    const methods = orderStr.split(/\s+/).map(normalizeAuthMethod).filter((m) => m !== 'unknown')
    ensureInterfaceAuth(iface)
    iface.authentication!.authenticationOrder = methods as any[]
    if (!iface.authentication!.sourceRefs) iface.authentication!.sourceRefs = []
    iface.authentication!.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // Authentication priority
  if (trimmed.startsWith('authentication priority ')) {
    const priorityStr = trimmed.substring('authentication priority '.length).trim()
    const methods = priorityStr.split(/\s+/).map(normalizeAuthMethod).filter((m) => m !== 'unknown')
    ensureInterfaceAuth(iface)
    iface.authentication!.authenticationPriority = methods as any[]
    if (!iface.authentication!.sourceRefs) iface.authentication!.sourceRefs = []
    iface.authentication!.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // Violation mode
  if (trimmed.startsWith('authentication violation ')) {
    const mode = trimmed.substring('authentication violation '.length).trim()
    ensureInterfaceAuth(iface)
    iface.authentication!.violation = normalizeViolationAction(mode)
    if (!iface.authentication!.sourceRefs) iface.authentication!.sourceRefs = []
    iface.authentication!.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // Description
  if (trimmed.startsWith('description ')) {
    iface.description = trimmed.substring('description '.length).trim()
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // 802.1X timeouts
  if (trimmed.startsWith('dot1x timeout tx-period ')) {
    const period = parseInt(trimmed.substring('dot1x timeout tx-period '.length).trim(), 10)
    ensureInterfaceAuth(iface)
    if (!iface.authentication!.dot1x) {
      iface.authentication!.dot1x = { enabled: true, sourceRefs: [createSourceRef(lineNum)] }
    }
    if (!iface.authentication!.dot1x.timeout) {
      iface.authentication!.dot1x.timeout = { sourceRefs: [createSourceRef(lineNum)] }
    }
    iface.authentication!.dot1x.timeout.txPeriod = period
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  if (trimmed.startsWith('dot1x timeout quiet-period ')) {
    const period = parseInt(trimmed.substring('dot1x timeout quiet-period '.length).trim(), 10)
    ensureInterfaceAuth(iface)
    if (!iface.authentication!.dot1x) {
      iface.authentication!.dot1x = { enabled: true, sourceRefs: [createSourceRef(lineNum)] }
    }
    if (!iface.authentication!.dot1x.timeout) {
      iface.authentication!.dot1x.timeout = { sourceRefs: [createSourceRef(lineNum)] }
    }
    iface.authentication!.dot1x.timeout.quietPeriod = period
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  if (trimmed.startsWith('dot1x timeout server-timeout ')) {
    const period = parseInt(trimmed.substring('dot1x timeout server-timeout '.length).trim(), 10)
    ensureInterfaceAuth(iface)
    if (!iface.authentication!.dot1x) {
      iface.authentication!.dot1x = { enabled: true, sourceRefs: [createSourceRef(lineNum)] }
    }
    if (!iface.authentication!.dot1x.timeout) {
      iface.authentication!.dot1x.timeout = { sourceRefs: [createSourceRef(lineNum)] }
    }
    iface.authentication!.dot1x.timeout.serverTimeout = period
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  if (trimmed.startsWith('dot1x timeout supp-timeout ')) {
    const period = parseInt(trimmed.substring('dot1x timeout supp-timeout '.length).trim(), 10)
    ensureInterfaceAuth(iface)
    if (!iface.authentication!.dot1x) {
      iface.authentication!.dot1x = { enabled: true, sourceRefs: [createSourceRef(lineNum)] }
    }
    if (!iface.authentication!.dot1x.timeout) {
      iface.authentication!.dot1x.timeout = { sourceRefs: [createSourceRef(lineNum)] }
    }
    iface.authentication!.dot1x.timeout.suppTimeout = period
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // Reauthentication
  if (trimmed === 'dot1x reauthentication' || trimmed === 'authentication periodic') {
    ensureInterfaceAuth(iface)
    if (!iface.authentication!.reauthentication) {
      iface.authentication!.reauthentication = {
        enabled: true,
        sourceRefs: [createSourceRef(lineNum)],
      }
    } else {
      iface.authentication!.reauthentication.enabled = true
    }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  if (trimmed.startsWith('dot1x timeout reauth-period ') || trimmed.startsWith('authentication timer reauthenticate ')) {
    const periodStr = trimmed.split(/\s+/).pop()!
    const period = parseInt(periodStr, 10)
    ensureInterfaceAuth(iface)
    if (!iface.authentication!.reauthentication) {
      iface.authentication!.reauthentication = {
        enabled: true,
        period,
        sourceRefs: [createSourceRef(lineNum)],
      }
    } else {
      iface.authentication!.reauthentication.period = period
    }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // Dynamic VLAN assignment
  if (trimmed === 'dot1x vlan-assignment' || trimmed === 'dot1x vlan-assignment enable') {
    ensureInterfaceAuth(iface)
    if (!iface.authentication!.authorizationAttributes) {
      iface.authentication!.authorizationAttributes = {
        sourceRefs: [createSourceRef(lineNum)],
      }
    }
    iface.authentication!.authorizationAttributes.dynamicVlan = {
      enabled: true,
      sourceRefs: [createSourceRef(lineNum)],
    }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  if (trimmed === 'dot1x vlan-assignment disable') {
    ensureInterfaceAuth(iface)
    if (!iface.authentication!.authorizationAttributes) {
      iface.authentication!.authorizationAttributes = {
        sourceRefs: [createSourceRef(lineNum)],
      }
    }
    iface.authentication!.authorizationAttributes.dynamicVlan = {
      enabled: false,
      sourceRefs: [createSourceRef(lineNum)],
    }
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // Static ACL reference on interface - distinct from dACL
  if (trimmed === 'ip access-group' || trimmed.startsWith('ip access-group ')) {
    handlePartiallyUnderstoodLine(
      state,
      lineNum,
      originalLine,
      'Static interface ACL reference preserved; distinct from downloadable ACL (dACL)',
      `Static interface ACL reference "${trimmed}" preserved in unparsed content; static ACLs are distinct from downloadable ACLs (dACL)`
    )
    return
  }

  // Authentication events - unsupported fallback actions
  if (trimmed.startsWith('authentication event ')) {
    handlePartiallyUnderstoodLine(
      state,
      lineNum,
      originalLine,
      `Unsupported authentication event action: ${trimmed}`,
      `Unsupported authentication event command "${trimmed}" preserved in unparsed content`
    )
    return
  }

  // Unsupported 802.1X parameters
  if (trimmed.startsWith('dot1x max-req ') || trimmed.startsWith('dot1x max-reauth-req ')) {
    handleUnparsedLine(state, lineNum, originalLine, `Unsupported 802.1X parameter: ${trimmed}`)
    return
  }

  // Shutdown
  if (trimmed === 'shutdown') {
    iface.adminState = 'down'
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  if (trimmed === 'no shutdown') {
    iface.adminState = 'up'
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // IP address for SVI
  if (trimmed.startsWith('ip address ')) {
    const ipMatch = trimmed.match(/ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)/)
    if (ipMatch) {
      const address = ipMatch[1]
      const subnetMask = ipMatch[2]
      // Convert subnet mask to prefix length
      const subnetToPrefix: {[key: string]: number} = {
        '255.255.255.0': 24,
        '255.255.0.0': 16,
        '255.0.0.0': 8,
        '255.255.255.255': 32,
        '255.255.255.252': 30,
        '255.255.255.248': 29,
        '255.255.255.240': 28,
        '255.255.255.224': 27,
        '255.255.255.192': 26,
        '255.255.255.128': 25,
      }
      const prefixLength = subnetToPrefix[subnetMask] || 24

      // Find SVI for this VLAN interface
      const vlanId = parseInt(interfaceName.replace('Vlan', ''), 10)
      if (!isNaN(vlanId)) {
        const svi = state.intent.svis.find(s => s.vlanId === vlanId)
        if (svi) {
          // Remove existing IP if any
          svi.ipAddresses = []
          svi.ipAddresses.push({
            address,
            prefixLength,
            type: 'primary',
          })
          svi.sourceRefs.push(createSourceRef(lineNum))
          markLineOutcome(state, lineNum, 'parsed')
          return
        }
      }
    }
  }

  // All other interface commands - preserve as unparsed lines
  handleUnparsedLine(state, lineNum, originalLine, `Unsupported interface command: ${trimmed}`)
}

// ===== RADIUS SERVER SUBCOMMANDS =====

function parseRadiusServerSubcommand(state: ParserState, trimmed: string, originalLine: string): void {
  const lineNum = state.currentLineNumber
  const name = state.currentContext.identifier!
  const serverId = `radius-server-${name}`
  const server = state.radiusServers.get(serverId)
  if (!server) {
    handleUnparsedLine(state, lineNum, originalLine, `Subcommand for unknown RADIUS server ${name}`)
    return
  }

  // address ipv4 <ip> [auth-port <port>] [acct-port <port>]
  // address ipv6 <ip> [auth-port <port>] [acct-port <port>]
  if (trimmed.startsWith('address ipv4 ') || trimmed.startsWith('address ipv6 ')) {
    const isIpv4 = trimmed.startsWith('address ipv4 ')
    const prefix = isIpv4 ? 'address ipv4 ' : 'address ipv6 '
    const parts = trimmed.substring(prefix.length).trim().split(/\s+/)
    server.address = parts[0]
    for (let i = 1; i < parts.length; i++) {
      if (parts[i] === 'auth-port' && i + 1 < parts.length) {
        server.authPort = parseInt(parts[i + 1], 10)
        i++
      } else if (parts[i] === 'acct-port' && i + 1 < parts.length) {
        server.acctPort = parseInt(parts[i + 1], 10)
        i++
      }
    }
    server.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // key [0|6|7] <secret>
  if (trimmed.startsWith('key ')) {
    server.key = { configured: true }
    server.sourceRefs.push(createSourceRef(lineNum))
    state.intent.findings.push(
      createFinding(
        'NAC_SECRET_REDACTED',
        'info',
        `RADIUS shared secret redacted from normalized intent for server ${server.address || name}`,
        createSourceRef(lineNum)
      )
    )
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // timeout <seconds>
  if (trimmed.startsWith('timeout ')) {
    server.timeout = parseInt(trimmed.substring('timeout '.length).trim(), 10)
    server.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // retransmit <count>
  if (trimmed.startsWith('retransmit ')) {
    server.retransmit = parseInt(trimmed.substring('retransmit '.length).trim(), 10)
    server.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  handleUnparsedLine(state, lineNum, originalLine, `Unsupported RADIUS server subcommand: ${trimmed}`)
}

// ===== AAA GROUP SUBCOMMANDS =====

function parseAaaGroupSubcommand(state: ParserState, trimmed: string, originalLine: string): void {
  const lineNum = state.currentLineNumber
  const groupName = state.currentContext.identifier!
  const group = state.radiusServerGroups.get(groupName)
  if (!group) {
    handleUnparsedLine(state, lineNum, originalLine, `Subcommand for unknown AAA group ${groupName}`)
    return
  }

  // server name <name>
  if (trimmed.startsWith('server name ')) {
    const sName = trimmed.substring('server name '.length).trim()
    const serverId = `radius-server-${sName}`
    if (!group.serverIds.includes(serverId)) {
      group.serverIds.push(serverId)
    }
    group.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  // server <ip> [auth-port <port>] [acct-port <port>]
  if (trimmed.startsWith('server ') && !trimmed.startsWith('server name ')) {
    const parts = trimmed.substring('server '.length).trim().split(/\s+/)
    const ip = parts[0]
    const serverId = `radius-${ip}`
    if (!group.serverIds.includes(serverId)) {
      group.serverIds.push(serverId)
    }
    group.sourceRefs.push(createSourceRef(lineNum))
    markLineOutcome(state, lineNum, 'parsed')
    return
  }

  handleUnparsedLine(state, lineNum, originalLine, `Unsupported AAA group subcommand: ${trimmed}`)
}

// ===== RADIUS PARSING =====

function parseRadiusServer(state: ParserState, line: string, lineNum: number): void {
  // Format: radius server <name>
  const name = line.substring('radius server '.length).trim()

  const serverId = `radius-server-${name}`
  if (!state.radiusServers.has(serverId)) {
    state.radiusServers.set(serverId, {
      id: serverId,
      name,
      // address intentionally left undefined until address command is parsed
      key: { configured: false },
      sourceRefs: [createSourceRef(lineNum)],
    })
  }
  ensureNacConfig(state)
  markLineOutcome(state, lineNum, 'parsed')
}

function parseRadiusHostLegacy(state: ParserState, line: string, lineNum: number): void {
  // Format: radius-server host <ip> [auth-port <port>] [acct-port <port>] [key <secret>]
  const parts = line.substring('radius-server host '.length).trim().split(/\s+/)
  const address = parts[0]

  const serverId = `radius-${address}`
  const server: RadiusServerConfig = {
    id: serverId,
    address,
    key: { configured: false },
    sourceRefs: [createSourceRef(lineNum)],
  }

  for (let i = 1; i < parts.length; i++) {
    if (parts[i] === 'auth-port' && i + 1 < parts.length) {
      server.authPort = parseInt(parts[i + 1], 10)
      i++
    } else if (parts[i] === 'acct-port' && i + 1 < parts.length) {
      server.acctPort = parseInt(parts[i + 1], 10)
      i++
    } else if (parts[i] === 'key' && i + 1 < parts.length) {
      // Secret detected - mark as configured but DO NOT store plaintext
      server.key = { configured: true }
      state.intent.findings.push(
        createFinding(
          'NAC_SECRET_REDACTED',
          'info',
          `RADIUS shared secret redacted from normalized intent for server ${address}`,
          createSourceRef(lineNum)
        )
      )
      break // Don't parse further to avoid capturing secret
    }
  }

  state.radiusServers.set(serverId, server)
  ensureNacConfig(state)
  markLineOutcome(state, lineNum, 'parsed')
}

function parseRadiusServerKey(state: ParserState, line: string, lineNum: number): void {
  // Global RADIUS key - mark that secrets exist but don't store
  state.intent.findings.push(
    createFinding(
      'NAC_SECRET_REDACTED',
      'info',
      'Global RADIUS shared secret redacted from normalized intent',
      createSourceRef(lineNum)
    )
  )
  markLineOutcome(state, lineNum, 'parsed')
}

function parseAaaGroupServer(state: ParserState, line: string, lineNum: number): void {
  // Format: aaa group server radius <group-name>
  const groupName = line.substring('aaa group server radius '.length).trim()

  if (!state.radiusServerGroups.has(groupName)) {
    state.radiusServerGroups.set(groupName, {
      name: groupName,
      serverIds: [],
      sourceRefs: [createSourceRef(lineNum)],
    })
  }

  ensureNacConfig(state)
  markLineOutcome(state, lineNum, 'parsed')
}

// ===== AAA PARSING =====

function parseAaaMethodTokens(tokens: string[]): AaaMethod[] {
  const methods: AaaMethod[] = []
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]
    if (token === 'group') {
      if (i + 1 >= tokens.length) {
        methods.push({ type: 'unknown', raw: 'group' })
        continue
      }
      methods.push({ type: 'group', groupName: tokens[i + 1] })
      i++
    } else if (token === 'local') {
      methods.push({ type: 'local' })
    } else if (token === 'none') {
      methods.push({ type: 'none' })
    } else {
      methods.push({ type: 'unknown', raw: token })
    }
  }
  return methods
}

function storeAaaMethodList(
  section: {
    defaultMethodList?: AaaMethodList
    defaultMethodLists?: Record<string, AaaMethodList>
    namedMethodLists: Record<string, AaaMethodList>
    methodLists?: AaaMethodList[]
  },
  listName: string,
  methodList: AaaMethodList,
  type: string
): void {
  if (!section.methodLists) {
    section.methodLists = []
  }
  section.methodLists.push(methodList)

  if (!section.defaultMethodLists) {
    section.defaultMethodLists = {}
  }

  if (listName === 'default') {
    section.defaultMethodLists[type] = methodList
    if (!section.defaultMethodList || type === 'dot1x') {
      section.defaultMethodList = methodList
    }
  } else {
    if (!section.namedMethodLists[listName]) {
      section.namedMethodLists[listName] = methodList
    } else if (section.namedMethodLists[listName].type === type) {
      section.namedMethodLists[listName] = methodList
    }
    section.namedMethodLists[`${type}/${listName}`] = methodList
  }
}

function parseAaaAuthentication(state: ParserState, line: string, lineNum: number): void {
  // Format: aaa authentication <type> {default | <list-name>} <method1> [<method2> ...]
  const parts = line.substring('aaa authentication '.length).trim().split(/\s+/)
  if (parts.length < 3) {
    handleUnparsedLine(state, lineNum, line, 'Malformed aaa authentication command')
    return
  }

  const type = parts[0] // login, dot1x, etc.
  const listName = parts[1]
  const methods = parseAaaMethodTokens(parts.slice(2))

  ensureNacConfig(state)
  if (!state.intent.nac!.aaa) {
    state.intent.nac!.aaa = {
      sourceRefs: [createSourceRef(lineNum)],
    }
  }

  if (!state.intent.nac!.aaa.authentication) {
    state.intent.nac!.aaa.authentication = {
      namedMethodLists: {},
      methodLists: [],
      defaultMethodLists: {},
      sourceRefs: [createSourceRef(lineNum)],
    }
  }

  const methodList: AaaMethodList = {
    name: listName === 'default' ? undefined : listName,
    type,
    methods,
    sourceRefs: [createSourceRef(lineNum)],
  }

  storeAaaMethodList(state.intent.nac!.aaa.authentication, listName, methodList, type)
  markLineOutcome(state, lineNum, 'parsed')
}

function parseAaaAuthorization(state: ParserState, line: string, lineNum: number): void {
  // Format: aaa authorization <type> {default | <list-name>} <method1> [<method2> ...]
  const parts = line.substring('aaa authorization '.length).trim().split(/\s+/)
  if (parts.length < 3) {
    handleUnparsedLine(state, lineNum, line, 'Malformed aaa authorization command')
    return
  }

  const type = parts[0]
  const listName = parts[1]
  const methods = parseAaaMethodTokens(parts.slice(2))

  ensureNacConfig(state)
  if (!state.intent.nac!.aaa) {
    state.intent.nac!.aaa = {
      sourceRefs: [createSourceRef(lineNum)],
    }
  }

  if (!state.intent.nac!.aaa.authorization) {
    state.intent.nac!.aaa.authorization = {
      namedMethodLists: {},
      methodLists: [],
      defaultMethodLists: {},
      sourceRefs: [createSourceRef(lineNum)],
    }
  }

  const methodList: AaaMethodList = {
    name: listName === 'default' ? undefined : listName,
    type,
    methods,
    sourceRefs: [createSourceRef(lineNum)],
  }

  storeAaaMethodList(state.intent.nac!.aaa.authorization, listName, methodList, type)
  markLineOutcome(state, lineNum, 'parsed')
}

function parseAaaAccounting(state: ParserState, line: string, lineNum: number): void {
  // Format: aaa accounting <type> {default | <list-name>} <action> <method1> [<method2> ...]
  const parts = line.substring('aaa accounting '.length).trim().split(/\s+/)
  if (parts.length < 4) {
    handleUnparsedLine(state, lineNum, line, 'Malformed aaa accounting command')
    return
  }

  const type = parts[0]
  const listName = parts[1]
  const action = parts[2] // start-stop, etc.
  const methods = parseAaaMethodTokens(parts.slice(3))

  ensureNacConfig(state)
  if (!state.intent.nac!.aaa) {
    state.intent.nac!.aaa = {
      sourceRefs: [createSourceRef(lineNum)],
    }
  }

  if (!state.intent.nac!.aaa.accounting) {
    state.intent.nac!.aaa.accounting = {
      namedMethodLists: {},
      methodLists: [],
      defaultMethodLists: {},
      sourceRefs: [createSourceRef(lineNum)],
    }
  }

  const methodList: AaaMethodList = {
    name: listName === 'default' ? undefined : listName,
    type,
    action,
    methods,
    sourceRefs: [createSourceRef(lineNum)],
  }

  storeAaaMethodList(state.intent.nac!.aaa.accounting, listName, methodList, type)
  markLineOutcome(state, lineNum, 'parsed')
}

function parseAaaMethod(methodStr: string): any {
  if (methodStr === 'local') {
    return { type: 'local' }
  }
  if (methodStr === 'none') {
    return { type: 'none' }
  }
  if (methodStr === 'group') {
    // "group" alone without a name - this is unusual, treat as unknown
    return { type: 'unknown', raw: methodStr }
  }
  // Check if it's a group reference like "CLEARPASS" (not prefixed with "group ")
  // In AAA commands, group references can appear without "group " prefix
  return { type: 'group', groupName: methodStr }
}


// ===== HELPER FUNCTIONS =====

function ensureNacConfig(state: ParserState): void {
  if (!state.intent.nac) {
    state.intent.nac = {
      radiusServers: [],
      radiusServerGroups: [],
      sourceRefs: [],
    }
  }
}

function ensureInterfaceAuth(iface: Partial<InterfaceConfig>): void {
  if (!iface.authentication) {
    iface.authentication = {
      sourceRefs: [],
    }
  }
}

function normalizePortControl(mode: string): any {
  if (mode === 'auto') return 'auto'
  if (mode === 'force-authorized') return 'force-authorized'
  if (mode === 'force-unauthorized') return 'force-unauthorized'
  return 'unknown'
}

function normalizeHostMode(mode: string): any {
  if (mode === 'single-host') return 'single-host'
  if (mode === 'multi-host') return 'multi-host'
  if (mode === 'multi-auth') return 'multi-auth'
  if (mode === 'multi-domain') return 'multi-domain'
  return 'unknown'
}

function normalizeAuthMethod(method: string): string {
  if (method === 'dot1x') return 'dot1x'
  if (method === 'mab') return 'mab'
  return 'unknown'
}

function normalizeViolationAction(action: string): any {
  if (action === 'shutdown') return 'shutdown'
  if (action === 'restrict') return 'restrict'
  if (action === 'protect') return 'protect'
  if (action === 'replace') return 'replace'
  return 'unknown'
}

function normalizeLacpMode(mode: string): LacpMode {
  const modeLower = mode.toLowerCase()
  if (modeLower === 'active') return 'active'
  if (modeLower === 'passive') return 'passive'
  if (modeLower === 'on' || modeLower === 'static') return 'static'
  return 'unknown'
}

function normalizeStpMode(mode: string): StpMode {
  const modeLower = mode.toLowerCase()
  if (modeLower === 'rapid-pvst') return 'rapid-pvst'
  if (modeLower === 'pvst') return 'pvst'
  if (modeLower === 'mstp') return 'mstp'
  if (modeLower === 'rstp') return 'rstp'
  if (modeLower === 'stp') return 'stp'
  return 'unknown'
}

// ===== FINALIZATION =====

function buildFinalIntent(state: ParserState): void {
  // Copy RADIUS servers to intent
  if (state.radiusServers.size > 0) {
    ensureNacConfig(state)
    state.intent.nac!.radiusServers = Array.from(state.radiusServers.values())
  }

  // Copy RADIUS server groups to intent
  if (state.radiusServerGroups.size > 0) {
    ensureNacConfig(state)
    state.intent.nac!.radiusServerGroups = Array.from(state.radiusServerGroups.values())
  }

  // Reconcile Port-channel configuration regardless of declaration order.
  for (const lag of state.intent.lags) {
    const portChannel = state.interfaceConfigs.get(lag.sourceInterfaceId)
    if (!portChannel) continue
    lag.adminState = portChannel.adminState ?? 'unknown'
    lag.description = portChannel.description
    lag.role = portChannel.role
    lag.accessVlan = portChannel.accessVlan
    lag.trunkNativeVlan = portChannel.trunkNativeVlan
    lag.trunkAllowedVlans = portChannel.trunkAllowedVlans
  }

  // Copy interfaces to intent
  for (const iface of state.interfaceConfigs.values()) {
    if (iface.sourceInterfaceId) {
      state.intent.interfaces.push(iface as InterfaceConfig)
    }
  }

  // Set NAC source refs
  if (state.intent.nac && state.intent.nac.sourceRefs.length === 0) {
    state.intent.nac.sourceRefs = [createSourceRef(1)]
  }

  // Reference validation
  validateNacReferences(state)
}

function validateNacReferences(state: ParserState): void {
  if (!state.intent.nac) return

  // 1. Missing server address finding for servers with unknown/unresolved address
  for (const server of state.intent.nac.radiusServers) {
    if (!server.address) {
      state.intent.findings.push(
        createFinding(
          'NAC_MISSING_SERVER_ADDRESS',
          'warning',
          `RADIUS server "${server.name || server.id}" has no configured IP address`,
          server.sourceRefs[0]
        )
      )
    }
  }

  const configuredServers = new Set<string>()
  for (const s of state.intent.nac.radiusServers) {
    configuredServers.add(s.id)
    if (s.name) {
      configuredServers.add(s.name)
      configuredServers.add(`radius-server-${s.name}`)
    }
    if (s.address) {
      configuredServers.add(s.address)
      configuredServers.add(`radius-${s.address}`)
    }
  }

  const configuredGroups = new Set<string>()
  for (const g of state.intent.nac.radiusServerGroups) {
    configuredGroups.add(g.name)
  }

  // 2. Check server groups referencing non-existent servers
  for (const group of state.intent.nac.radiusServerGroups) {
    for (const serverId of group.serverIds) {
      if (!configuredServers.has(serverId)) {
        state.intent.findings.push(
          createFinding(
            'NAC_UNRESOLVED_RADIUS_SERVER',
            'warning',
            `Server group "${group.name}" references unresolved RADIUS server "${serverId}"`,
            group.sourceRefs[0]
          )
        )
      }
    }
  }

  // 3. Check AAA method lists referencing non-existent server groups
  if (state.intent.nac.aaa) {
    const checkMethodList = (list: any) => {
      if (!list || !list.methods) return
      for (const m of list.methods) {
        if (m.type === 'group' && m.groupName) {
          // radius is a standard builtin keyword in IOS, but named groups should exist
          if (m.groupName.toLowerCase() !== 'radius' && !configuredGroups.has(m.groupName)) {
            state.intent.findings.push(
              createFinding(
                'NAC_UNRESOLVED_SERVER_GROUP',
                'warning',
                `AAA method list references unresolved RADIUS server group "${m.groupName}"`,
                list.sourceRefs?.[0]
              )
            )
          }
        }
      }
    }

    const checkSection = (section: any) => {
      if (!section) return
      if (section.methodLists) {
        for (const list of section.methodLists) {
          checkMethodList(list)
        }
      } else {
        checkMethodList(section.defaultMethodList)
        for (const list of Object.values(section.namedMethodLists || {})) {
          checkMethodList(list)
        }
      }
    }

    checkSection(state.intent.nac.aaa.authentication)
    checkSection(state.intent.nac.aaa.authorization)
    checkSection(state.intent.nac.aaa.accounting)
  }
}

function calculateCoverage(state: ParserState): void {
  const nonIgnoredLines = state.lines
    .map((l, idx) => ({ lineNum: idx + 1, text: l.trim() }))
    .filter((l) => l.text && !l.text.startsWith('!'))

  const totalLines = nonIgnoredLines.length
  let parsedLines = 0
  let partiallyParsedLines = 0
  let unparsedLines = 0

  for (const item of nonIgnoredLines) {
    const outcome = state.lineOutcomes.get(item.lineNum) || 'unparsed'
    if (outcome === 'parsed') {
      parsedLines++
    } else if (outcome === 'partially-understood') {
      partiallyParsedLines++
    } else {
      unparsedLines++
    }
  }

  state.intent.coverage = {
    totalLines,
    parsedLines,
    unparsedLines,
    partiallyParsedLines,
    coveragePercent: totalLines > 0 ? Math.round((parsedLines / totalLines) * 100) : 0,
  }
}
