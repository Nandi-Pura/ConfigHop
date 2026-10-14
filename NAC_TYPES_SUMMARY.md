# NAC (Network Access Control) Types - Implementation Summary

## Overview
Added comprehensive NAC type definitions to the normalized switch intent schema for 802.1X, MAB, RADIUS, AAA, and CoA configurations.

## Key Design Principles

### 1. Security-First: No Plaintext Secrets
- RADIUS shared secrets use `RadiusKeyStatus` type with `configured: boolean` flag
- CoA server keys similarly protected
- Secret references tracked via `keyReference?: string` for named keys
- New finding code: `NAC_SECRET_REDACTED` for audit trail

### 2. Vendor-Neutral Design
- Cisco dACL and Aruba DUR kept as distinct types (not equivalent)
- `DownloadableAclConfig` for Cisco dACL
- `DownloadableUserRoleConfig` for Aruba DUR
- New finding code: `NAC_MIGRATION_REVIEW_REQUIRED` for cross-vendor migrations

### 3. Backward Compatibility
- `NacConfig` is optional field on `NormalizedSwitchIntent`
- Empty intents have `nac: undefined` by default
- Existing non-NAC workflows unchanged

## Type Structure

### Top-Level NAC Configuration
```typescript
interface NacConfig {
  radiusServers: RadiusServerConfig[]
  radiusServerGroups: RadiusServerGroupConfig[]
  aaa?: AaaConfig
  dot1x?: Dot1xGlobalConfig
  mab?: MabGlobalConfig
  coa?: CoaConfig
  sourceRefs: SourceReference[]
}
```

### RADIUS Infrastructure
- **RadiusServerConfig**: Individual RADIUS servers with auth/acct ports, timeouts, and key status
- **RadiusServerGroupConfig**: Named server groups referencing server IDs
- **RadiusKeyStatus**: Secret tracking without plaintext exposure

### AAA Method Lists
- **AaaConfig**: Split into authentication, authorization, accounting
- **AaaMethodList**: Ordered methods (group/local/none/unknown)
- Named and default method lists separated

### Interface Authentication
- **InterfaceAuthenticationConfig**: Added to existing `Interface` type
- **802.1X**: `InterfaceDot1xConfig` with PAE role, timeouts, reauthentication
- **MAB**: `InterfaceMabConfig` for MAC Authentication Bypass
- Port control modes: auto | force-authorized | force-unauthorized
- Host modes: single-host | multi-host | multi-auth | multi-domain
- Violation actions: shutdown | restrict | protect | replace

### Dynamic Authorization
- **AuthorizationAttributes**: RADIUS-assigned policies
- **DynamicVlanConfig**: Dynamic VLAN assignment
- **DownloadableAclConfig**: Cisco dACL support
- **FilterIdConfig**: Filter-ID RADIUS attribute
- **DownloadableUserRoleConfig**: Aruba ClearPass DUR (distinct from dACL)

### Change of Authorization (CoA)
- **CoaConfig**: Client and server configurations
- **CoaClientConfig**: Outbound CoA to RADIUS servers
- **CoaServerConfig**: Inbound CoA from RADIUS servers

## New Finding Codes
- `NAC_UNRESOLVED_RADIUS_SERVER`: Server referenced but not defined
- `NAC_UNRESOLVED_SERVER_GROUP`: Group referenced but not defined
- `NAC_SECRET_REDACTED`: Secret removed for security
- `NAC_MIGRATION_REVIEW_REQUIRED`: Vendor-specific feature needs manual review

## Test Coverage
Added 10 comprehensive tests (tests 15-24):
- Empty intent backward compatibility
- RADIUS server and group configuration
- Secret redaction enforcement
- AAA method lists with ordered methods
- Interface 802.1X and MAB
- Cisco dACL vs Aruba DUR distinction
- CoA client/server configuration
- NAC-specific finding codes
- Global 802.1X/MAB settings
- Non-NAC intent backward compatibility

All 42 tests pass. TypeScript compilation clean.

## Usage Example

```typescript
import { createEmptyIntent, NacConfig } from './switch/intent'

const intent = createEmptyIntent({ vendor: 'cisco', osFamilyName: 'IOS XE' })

intent.nac = {
  radiusServers: [
    {
      id: 'clearpass-primary',
      address: '10.1.1.10',
      authPort: 1812,
      acctPort: 1813,
      key: { configured: true, keyReference: 'named-key-1' },
      sourceRefs: [{ startLine: 100, endLine: 105 }],
    },
  ],
  radiusServerGroups: [
    {
      name: 'CLEARPASS',
      serverIds: ['clearpass-primary'],
      sourceRefs: [{ startLine: 110 }],
    },
  ],
  aaa: {
    authentication: {
      defaultMethodList: {
        methods: [
          { type: 'group', groupName: 'CLEARPASS' },
          { type: 'local' },
        ],
        sourceRefs: [{ startLine: 200 }],
      },
      namedMethodLists: {},
      sourceRefs: [{ startLine: 200, endLine: 210 }],
    },
    sourceRefs: [{ startLine: 200, endLine: 210 }],
  },
  sourceRefs: [{ startLine: 100, endLine: 210 }],
}

// Interface with 802.1X
intent.interfaces.push({
  sourceInterfaceId: 'GigabitEthernet1/0/1',
  role: 'access',
  adminState: 'up',
  authentication: {
    dot1x: { enabled: true, pae: 'authenticator', sourceRefs: [{ startLine: 300 }] },
    mab: { enabled: true, sourceRefs: [{ startLine: 305 }] },
    portControl: 'auto',
    hostMode: 'multi-auth',
    authenticationOrder: ['dot1x', 'mab'],
    sourceRefs: [{ startLine: 300, endLine: 320 }],
  },
  sourceRefs: [{ startLine: 300, endLine: 320 }],
})
```

## Migration Notes
- Parser implementations should populate `RadiusKeyStatus.configured = true` when secret detected
- Never extract or store plaintext secrets in normalized intent
- Use finding code `NAC_SECRET_REDACTED` when secrets are encountered
- Cisco-to-Aruba migrations must check dACL → DUR mappings and emit `NAC_MIGRATION_REVIEW_REQUIRED`

## Files Modified
- `src/switch/intent/types.ts`: Added 200+ lines of NAC type definitions
- `src/intent.test.mjs`: Added 10 comprehensive NAC tests (tests 15-24)

Schema version remains `1.0.0` (additive change, backward compatible).
