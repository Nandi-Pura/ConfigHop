import test from 'node:test'
import assert from 'node:assert/strict'
import {
  autoMapSwitchPorts, changeSwitchPort, filterSwitchPorts,
  switchCatalog, switchOsLabel, switchPorts, switchSource, switchTarget,
  ARUBA_HARDWARE, getArubaSeries, getArubaHardwareBySeries, getArubaHardwareById,
  getCompatibleOs, evaluateCompatibility, AOS_CX_RELEASES,
  compareVersions, isVersionAtOrAboveFloor, computeLifecycleStatus,
} from './switchData.ts'
import { SWITCH_EVIDENCE, isVerified, isClaimVerified } from './switch/evidence.ts'
import {
  CX6300M_24SFP, CX6300M_48G,
  CX6300M_48SR5_POE, CX6300M_24SR5_POE,
  CX6300M_48G_POE, CX6300M_24G_POE,
  CX6300M_48G_NONPOE, CX6300M_24G_NONPOE,
  CX6300_MODELS,
} from './switch/aruba/cx6300.ts'
import { CX6405, CX6410, CX6400_MGMT_V1, CX6400_V2 } from './switch/aruba/cx6400.ts'
import {
  CX6100_JL675A, CX6100_JL676A, CX6100_JL677A, CX6100_JL678A, CX6100_JL679A, CX6100_MODELS,
} from './switch/aruba/cx6100.ts'
import {
  CX6000_R8N85A, CX6000_R8N86A, CX6000_R8N87A, CX6000_R8N88A, CX6000_R8N89A, CX6000_R9Y03A, CX6000_MODELS,
} from './switch/aruba/cx6000.ts'
import {
  CX6200_JL724A, CX6200_JL725A, CX6200_JL726A, CX6200_JL727A, CX6200_JL728A, CX6200_MODELS,
} from './switch/aruba/cx6200.ts'
import {
  CX6300L_S3L75A, CX6300L_S3L76A, CX6300L_S3L77A, CX6300L_MODELS,
} from './switch/aruba/cx6300l.ts'
import { CX5420F } from './switch/aruba/cx5420.ts'
import {
  renderVlan, renderVlans, renderInterface, renderLag,
  renderStaticRoute, renderStpMode, renderAcl,
  renderVrf, renderVsfMember,
} from './switch/config/aruba/index.ts'

test('Legacy switch catalog keeps vendor hardware and OS combinations separate', () => {
  assert.deepEqual([...new Set(switchCatalog.map((item) => item.vendor))], ['Cisco', 'HPE Aruba Networking', 'Juniper Networks', 'Huawei'])
  assert.equal(switchSource.hardware.model, 'C9300-48P')
  assert.equal(switchSource.hardware.series, 'Catalyst 9300 Series')
  assert.equal(switchOsLabel(switchSource), 'IOS XE 17.12')
  assert.equal(switchTarget.hardware.model, 'CX 6300M 48G')
  assert.equal(switchOsLabel(switchTarget), 'AOS-CX 10.15')
  assert.ok(switchCatalog.filter((item) => item.vendor === 'Cisco').every((item) => item.software.product === 'IOS XE'))
  assert.ok(switchCatalog.filter((item) => item.vendor === 'HPE Aruba Networking').every((item) => item.software.product === 'AOS-CX'))
  assert.ok(switchCatalog.filter((item) => item.vendor === 'Juniper Networks').every((item) => item.software.product === 'Junos'))
  assert.ok(switchCatalog.filter((item) => item.vendor === 'Huawei').every((item) => item.software.product === 'VRP'))
})

test('1. Hardware catalog contains valid Aruba models across required series', () => {
  assert.ok(ARUBA_HARDWARE.length >= 7)
  const series = getArubaSeries()
  for (const s of ['CX 5420', 'CX 6000', 'CX 6100', 'CX 6200', 'CX 6300', 'CX 6300L', 'CX 6400']) {
    assert.ok(series.includes(s), `Series includes ${s}`)
  }
  for (const hw of ARUBA_HARDWARE) {
    assert.equal(hw.vendor, 'hpe_aruba')
    assert.ok(hw.totalAccessPorts >= 0)
    assert.ok(hw.ports.length >= hw.totalAccessPorts)
  }
  const found = getArubaHardwareById('aruba-cx-6300m-24sfp-jl658a')
  assert.equal(found?.productNumber, 'JL658A')
})

test('2. Models are decoupled from OS releases', () => {
  assert.ok(AOS_CX_RELEASES.length >= 4)
  assert.ok(AOS_CX_RELEASES.some((r) => r.releaseType === 'LSR' && r.train === '10.13'))
  assert.ok(AOS_CX_RELEASES.some((r) => r.releaseType === 'LSR' && r.train === '10.16'))
  assert.ok(AOS_CX_RELEASES.some((r) => r.releaseType === 'SSR' && r.train === '10.17'))
  assert.ok(AOS_CX_RELEASES.some((r) => r.releaseType === 'SSR' && r.train === '10.18'))
  assert.equal(CX6300M_24SFP.ports.length, 28)
  assert.equal(CX6300M_48G.ports.length, 28)
  assert.equal(CX6300M_24SFP.productNumber, 'JL658A')
})

test('3. Compatibility matrix - CX6300M JL658A: BLOCKED on 10.13, READY on 10.16, REVIEW_REQUIRED on 10.17 (EXPIRING_SOON)', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  const os1017 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.17')
  const r1013 = evaluateCompatibility(CX6300M_24SFP, os1013)
  const r1016 = evaluateCompatibility(CX6300M_24SFP, os1016)
  const r1017 = evaluateCompatibility(CX6300M_24SFP, os1017)
  // JL658A floor 10.14.0001 — train 10.13 below floor
  assert.equal(r1013.status, 'BLOCKED', `10.13 must be BLOCKED for JL658A (floor 10.14.0001): ${r1013.reason}`)
  // 10.16 lifecycle ACTIVE (earliest bound 2024-05-21 official) → floor met → READY
  assert.equal(r1016.status, 'READY', `10.16: ${r1016.reason}`)
  // 10.17 lifecycle EXPIRING_SOON (latestEOS 2027-02-26 within 180d from 2026-10-16) → REVIEW_REQUIRED
  assert.equal(r1017.status, 'REVIEW_REQUIRED', `10.17 should be REVIEW_REQUIRED (EXPIRING_SOON): ${r1017.reason}`)
})

test('4. Hardware with floor above 10.13 (CX6300L S3L75A): BLOCKED on 10.13, READY on 10.16 (lifecycle ACTIVE)', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  const r1013 = evaluateCompatibility(CX6300L_S3L75A, os1013)
  const r1016 = evaluateCompatibility(CX6300L_S3L75A, os1016)
  assert.equal(r1013.status, 'BLOCKED')
  // 10.16 lifecycle ACTIVE → floor 10.14.0006 met by 10.16 → READY
  assert.equal(r1016.status, 'READY', `S3L75A on 10.16: ${r1016.reason}`)
  if (r1013.evidenceIds) {
    assert.ok(r1013.evidenceIds.includes('ARUBA-EVD-RN-1013-1050'))
  }
})

test('5. Deprecated product mappings removed', () => {
  assert.equal(getArubaHardwareById('aruba-cx-6300-48g'), undefined)
  assert.equal(getArubaHardwareById('aruba-cx-6300-24sfp'), undefined)
})

test('6. Data-driven evaluator: R8N85A and JL676A are consistent and READY on 10.13', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  // R8N85A: floor 10.11.1011, OS 10.13 > 10.11, lifecycle 10.13 active, evidence release-notes → READY
  const rR8N85A = evaluateCompatibility(CX6000_R8N85A, os1013)
  assert.equal(rR8N85A.status, 'READY', `R8N85A on 10.13: ${rR8N85A.reason}`)
  assert.notEqual(rR8N85A.status, 'UNKNOWN')
  // JL676A: floor 10.06.0001, OS 10.13 > 10.06, lifecycle active, evidence release-notes → READY
  const rJL676A = evaluateCompatibility(CX6100_JL676A, os1013)
  assert.equal(rJL676A.status, 'READY', `JL676A on 10.13: ${rJL676A.reason}`)
  // Both consistent — same status
  assert.equal(rR8N85A.status, rJL676A.status, 'R8N85A and JL676A must be consistent on 10.13')
})

test('Unknown hardware or OS fails closed without throwing', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const unknownHardware = evaluateCompatibility(undefined, os1013)
  const unknownOs = evaluateCompatibility(CX6000_R8N85A, undefined)
  assert.equal(unknownHardware.status, 'UNKNOWN')
  assert.match(unknownHardware.reason, /Hardware is not in the Aruba catalog/)
  assert.equal(unknownOs.status, 'UNKNOWN')
  assert.match(unknownOs.reason, /OS release is not in the AOS-CX catalog/)
})

test('7. Port layout correctness - JL658A is 24 SFP+ + 4 SFP56 = 28 ports', () => {
  assert.equal(CX6300M_24SFP.ports.length, 28)
  assert.equal(CX6300M_24SFP.totalAccessPorts, 24)
  assert.equal(CX6300M_24SFP.totalUplinkPorts, 4)
  assert.equal(CX6300M_24SFP.poeCapable, false)

  assert.equal(CX6100_JL675A.ports.length, 52)
  assert.equal(CX6100_JL675A.totalAccessPorts, 48)
  assert.equal(CX6100_JL675A.totalUplinkPorts, 4)
  assert.equal(CX6100_JL675A.poeCapable, true)
})

test('8. Evidence links are present and verified where claims exist', () => {
  assert.ok(CX6400_V2.evidenceIds.includes('ARUBA-EVD-RN-1013-1050'))
  assert.ok(isVerified(CX6400_V2.evidenceIds))
})

test('9. VSF semantic model - vsfStatus SUPPORTED/UNSUPPORTED/UNKNOWN', () => {
  assert.equal(CX6300M_24SFP.vsf.vsfStatus, 'SUPPORTED')
  assert.equal(CX6300M_24SFP.vsf.maxMembers, 10)
  assert.equal(CX6200_JL724A.vsf.vsfStatus, 'SUPPORTED')
  assert.equal(CX6200_JL724A.vsf.maxMembers, 8)
  assert.equal(CX6100_JL675A.vsf.vsfStatus, 'UNKNOWN')
  assert.equal(CX6000_R8N85A.vsf.vsfStatus, 'UNKNOWN')
  assert.equal(CX6300L_S3L75A.vsf.vsfStatus, 'UNKNOWN')
})

test('10. Claim-specific evidence validation', () => {
  // SKU evidence must explicitly mention the product number
  assert.equal(isClaimVerified(['ARUBA-EVD-CX6300-1012-RN'], 'sku', 'JL658A'), true)
  assert.equal(isClaimVerified(['ARUBA-EVD-CX6300-1012-RN'], 'sku', 'JL999Z'), false)

  // Port layout evidence must describe port configuration
  assert.equal(isClaimVerified(['ARUBA-EVD-CX6300-1012-RN'], 'port-layout'), true)
  assert.equal(isClaimVerified(['ARUBA-EVD-CX6300-1013'], 'port-layout'), false)

  // Minimum version evidence must state minimum software version
  assert.equal(isClaimVerified(['ARUBA-EVD-CX6300-1012-RN'], 'minimum-version'), true)
  assert.equal(isClaimVerified(['ARUBA-CX6300-DATASHEET-TODO'], 'minimum-version'), false)

  // VSF support evidence must explicitly mention VSF/stacking
  assert.equal(isClaimVerified(['ARUBA-EVD-VSF-CENTRAL'], 'vsf-support'), true)
  assert.equal(isClaimVerified(['ARUBA-EVD-CX6100-1012-RN'], 'vsf-support'), false)

  // Chassis role evidence must distinguish chassis from module
  assert.equal(isClaimVerified(['ARUBA-EVD-CX6400-CHASSIS'], 'chassis-role'), true)
  assert.equal(isClaimVerified(['ARUBA-EVD-CX6300-1012-RN'], 'chassis-role'), false)

  // Unverified evidence never validates any claim
  assert.equal(isClaimVerified(['ARUBA-CX6300-DATASHEET-TODO'], 'sku', 'JL658A'), false)

  // Empty evidence list never validates
  assert.equal(isClaimVerified([], 'sku', 'JL658A'), false)
})

test('11. CX 6400 chassis and bundle distinction', () => {
  assert.equal(CX6405.hardwareRole, 'chassis')
  assert.equal(CX6410.hardwareRole, 'chassis')
  assert.equal(CX6400_V2.hardwareRole, 'chassis')
  assert.equal(CX6400_MGMT_V1.hardwareRole, 'management-module')

  assert.equal(CX6405.productNumber, 'R0X26A')
  assert.equal(CX6410.productNumber, 'R0X27A')
  assert.equal(CX6400_V2.productNumber, 'JL741A')
  assert.equal(CX6400_MGMT_V1.productNumber, 'R0X31A')

  assert.equal(CX6400_V2.marketingModel, 'Aruba 6410 96-port 1GbE Class 4 PoE and 4-port SFP56 Switch')
  assert.equal(CX6400_V2.minimumVersion, '10.05.0001')
  assert.ok(CX6400_MGMT_V1.notes?.includes('NOT A STANDALONE SWITCH'))
})

test('12. Phase 2.3 Section 16 - CX 6300 official SKUs and VSF specs', () => {
  assert.equal(CX6300M_24SFP.productNumber, 'JL658A')
  assert.equal(CX6300M_24SFP.minimumVersion, '10.14.0001')
  assert.equal(CX6300M_24SFP.ports.length, 28)
  assert.equal(CX6300M_24SFP.totalAccessPorts, 24)
  assert.equal(CX6300M_24SFP.totalUplinkPorts, 4)
  assert.equal(CX6300M_24SFP.poeCapable, false)

  assert.equal(CX6300M_48SR5_POE.productNumber, 'JL659A')
  assert.equal(CX6300M_48SR5_POE.minimumVersion, '10.14.0001')
  assert.equal(CX6300M_48SR5_POE.ports.length, 52)
  assert.equal(CX6300M_48SR5_POE.totalAccessPorts, 48)
  assert.equal(CX6300M_48SR5_POE.totalUplinkPorts, 4)
  assert.equal(CX6300M_48SR5_POE.poeCapable, true)

  assert.equal(CX6300M_24SR5_POE.productNumber, 'JL660A')
  assert.equal(CX6300M_24SR5_POE.minimumVersion, '10.04.3000')
  assert.equal(CX6300M_24SR5_POE.minimumVersionStatus, 'UNVERIFIED')
  assert.equal(CX6300M_24SR5_POE.ports.length, 28)
  assert.equal(CX6300M_24SR5_POE.totalAccessPorts, 24)
  assert.equal(CX6300M_24SR5_POE.totalUplinkPorts, 4)
  assert.equal(CX6300M_24SR5_POE.poeCapable, true)

  assert.equal(CX6300M_48G_POE.productNumber, 'JL661A')
  assert.equal(CX6300M_48G_POE.minimumVersion, '10.04.3000')
  assert.equal(CX6300M_48G_POE.minimumVersionStatus, 'UNVERIFIED')
  assert.equal(CX6300M_48G_POE.ports.length, 52)
  assert.equal(CX6300M_48G_POE.totalAccessPorts, 48)
  assert.equal(CX6300M_48G_POE.totalUplinkPorts, 4)
  assert.equal(CX6300M_48G_POE.poeCapable, true)

  assert.equal(CX6300M_24G_POE.productNumber, 'JL662A')
  assert.equal(CX6300M_24G_POE.minimumVersion, '10.04.3000')
  assert.equal(CX6300M_24G_POE.minimumVersionStatus, 'UNVERIFIED')
  assert.equal(CX6300M_24G_POE.ports.length, 28)
  assert.equal(CX6300M_24G_POE.totalAccessPorts, 24)
  assert.equal(CX6300M_24G_POE.totalUplinkPorts, 4)
  assert.equal(CX6300M_24G_POE.poeCapable, true)

  assert.equal(CX6300M_48G_NONPOE.productNumber, 'JL663A')
  assert.equal(CX6300M_48G_NONPOE.minimumVersion, '10.04.3000')
  assert.equal(CX6300M_48G_NONPOE.minimumVersionStatus, 'UNVERIFIED')
  assert.equal(CX6300M_48G_NONPOE.ports.length, 52)
  assert.equal(CX6300M_48G_NONPOE.totalAccessPorts, 48)
  assert.equal(CX6300M_48G_NONPOE.totalUplinkPorts, 4)
  assert.equal(CX6300M_48G_NONPOE.poeCapable, false)

  assert.equal(CX6300M_24G_NONPOE.productNumber, 'JL664A')
  assert.equal(CX6300M_24G_NONPOE.minimumVersion, '10.04.0001')
  assert.equal(CX6300M_24G_NONPOE.minimumVersionStatus, 'UNVERIFIED')
  assert.equal(CX6300M_24G_NONPOE.ports.length, 28)
  assert.equal(CX6300M_24G_NONPOE.totalAccessPorts, 24)
  assert.equal(CX6300M_24G_NONPOE.totalUplinkPorts, 4)
  assert.equal(CX6300M_24G_NONPOE.poeCapable, false)

  assert.equal(isVersionAtOrAboveFloor('10.04.2999', CX6300M_24SFP.minimumVersion), false)
  assert.equal(isVersionAtOrAboveFloor('10.14.0000', CX6300M_24SFP.minimumVersion), false)
  assert.equal(isVersionAtOrAboveFloor('10.14.0001', CX6300M_24SFP.minimumVersion), true)
  assert.equal(isVersionAtOrAboveFloor('10.16.0001', CX6300M_24SFP.minimumVersion), true)
  assert.equal(isVersionAtOrAboveFloor('10.04.0000', CX6300M_24G_NONPOE.minimumVersion), false)
  assert.equal(isVersionAtOrAboveFloor('10.04.0001', CX6300M_24G_NONPOE.minimumVersion), true)

  assert.ok(!ARUBA_HARDWARE.some((hw) => hw.productNumber === 'JL658B'))
  assert.ok(!ARUBA_HARDWARE.some((hw) => hw.id.includes('jl658b')))
  assert.ok(!ARUBA_HARDWARE.some((hw) => hw.id.includes('sku-x')))

  assert.equal(isVerified(CX6300M_24SFP.evidenceIds), true)
  assert.equal(isVerified(CX6300M_48SR5_POE.evidenceIds), true)
  assert.equal(isVerified(CX6300M_24G_NONPOE.evidenceIds), true)
  assert.ok(SWITCH_EVIDENCE['ARUBA-EVD-CX6300-1012-RN'])
  assert.equal(SWITCH_EVIDENCE['ARUBA-EVD-CX6300-1012-RN'].sourceType, 'release-notes')
  assert.ok(SWITCH_EVIDENCE['ARUBA-EVD-CX6300-1012-RN'].url.startsWith('https://'))

  const cx6405 = getArubaHardwareById('aruba-cx-6405-r0x26a')
  const cx6410 = getArubaHardwareById('aruba-cx-6410-r0x27a')
  assert.equal(cx6405?.productNumber, 'R0X26A')
  assert.equal(cx6410?.productNumber, 'R0X27A')
  assert.equal(cx6405?.totalAccessPorts, 0)
  assert.equal(cx6410?.totalAccessPorts, 0)
})

test('13. Official release notes fixture: SKU -> name + minVersion locked, S3L75A on 10.13 is BLOCKED', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  assert.equal(evaluateCompatibility(CX6300L_S3L75A, os1013).status, 'BLOCKED')

  const FIXTURES = [
    { sku: 'JL741A', name: 'Aruba 6410 96-port 1GbE Class 4 PoE and 4-port SFP56 Switch', min: '10.05.0001', role: 'chassis' },
    { sku: 'JL658A', min: '10.14.0001' },
    { sku: 'JL659A', min: '10.14.0001' },
    { sku: 'S3L75A', min: '10.14.0006' },
    { sku: 'S3L76A', min: '10.14.0006' },
    { sku: 'S3L77A', min: '10.14.0006' },
    { sku: 'R0X26A', min: '10.05.0021' },
    { sku: 'R0X27A', min: '10.05.0001' },
    { sku: 'R0X31A', min: '10.04.1000' },
    { sku: 'R8N85A', min: '10.11.1011' },
    { sku: 'R8N86A', min: '10.11.1011' },
    { sku: 'R8N87A', min: '10.11.1011' },
    { sku: 'R8N88A', min: '10.11.1011' },
    { sku: 'R8N89A', min: '10.11.1011' },
    { sku: 'R9Y03A', min: '10.11.1001' },
    { sku: 'JL675A', min: '10.06.0001' },
    { sku: 'JL676A', min: '10.06.0001' },
    { sku: 'JL677A', min: '10.06.0001' },
    { sku: 'JL678A', min: '10.06.0001' },
    { sku: 'JL679A', min: '10.06.0001' },
  ]

  for (const f of FIXTURES) {
    const hw = ARUBA_HARDWARE.find((item) => item.productNumber === f.sku)
    assert.ok(hw, `Hardware ${f.sku} must exist in catalog`)
    assert.equal(hw.minimumVersion, f.min, `${f.sku} minimumVersion mismatch`)
    if (f.name) {
      assert.equal(hw.marketingModel, f.name, `${f.sku} marketingModel mismatch`)
    }
    if (f.role) {
      assert.equal(hw.hardwareRole, f.role, `${f.sku} hardwareRole mismatch`)
    }
  }

  // Unverified minimum versions evaluate to UNKNOWN
  for (const unverifiedHw of [CX6300M_24SR5_POE, CX6300M_48G_POE, CX6300M_24G_POE, CX6300M_48G_NONPOE, CX6300M_24G_NONPOE, CX6200_JL724A, CX5420F]) {
    assert.equal(evaluateCompatibility(unverifiedHw, os1013).status, 'UNKNOWN')
  }
})

// ──────────────────────────────────────────────────────────────────────────────
// Tes baru: evaluator data-driven — per kasus, nama jelas
// ──────────────────────────────────────────────────────────────────────────────

test('14a. JL658A on 10.13 is BLOCKED (floor 10.14.0001 > train 10.13)', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const r = evaluateCompatibility(CX6300M_24SFP, os1013)
  assert.equal(r.status, 'BLOCKED', r.reason)
  assert.ok(r.reason.includes('10.14.0001'), `reason should mention floor: ${r.reason}`)
})

test('14b. JL659A on 10.13 is BLOCKED (floor 10.14.0001 > train 10.13)', () => {
  const hw = ARUBA_HARDWARE.find((h) => h.productNumber === 'JL659A')
  assert.ok(hw, 'JL659A must exist in catalog')
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const r = evaluateCompatibility(hw, os1013)
  assert.equal(r.status, 'BLOCKED', r.reason)
})

test('14c. S3L75A on 10.13 is BLOCKED (floor 10.14.0006 > train 10.13)', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const r = evaluateCompatibility(CX6300L_S3L75A, os1013)
  assert.equal(r.status, 'BLOCKED', r.reason)
})

test('14d. S3L75A on 10.16 is READY (10.16 lifecycle ACTIVE; floor 10.14.0006 met; official evidence)', () => {
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  const r = evaluateCompatibility(CX6300L_S3L75A, os1016)
  // 10.16 lifecycle ACTIVE (earliest bound 2024-05-21 official) → floor terpenuhi → READY
  assert.equal(r.status, 'READY', r.reason)
  assert.notEqual(r.status, 'BLOCKED')
})

test('14e. R0X26A, R0X27A, R0X31A, JL741A on 10.16 are READY (lifecycle ACTIVE, official evidence)', () => {
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  for (const sku of ['R0X26A', 'R0X27A', 'R0X31A', 'JL741A']) {
    const hw = ARUBA_HARDWARE.find((h) => h.productNumber === sku)
    assert.ok(hw, `${sku} must exist in catalog`)
    const r = evaluateCompatibility(hw, os1016)
    // 10.16 lifecycle ACTIVE (earliest bound 2024-05-21 from official 10.14.0001 RN)
    assert.equal(r.status, 'READY', `${sku} on 10.16: expected READY (lifecycle ACTIVE), got ${r.status}: ${r.reason}`)
  }
})

test('14f. R0X26A on 10.13 is READY (floor 10.05.0021 met; lifecycle 10.13 active; release-notes evidence)', () => {
  const hw = ARUBA_HARDWARE.find((h) => h.productNumber === 'R0X26A')
  assert.ok(hw, 'R0X26A must exist')
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const r = evaluateCompatibility(hw, os1013)
  assert.equal(r.status, 'READY', r.reason)
})

test('14g. R8N85A on 10.13 yields same status as JL676A on 10.13 (both READY)', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const rR8N85A = evaluateCompatibility(CX6000_R8N85A, os1013)
  const rJL676A = evaluateCompatibility(CX6100_JL676A, os1013)
  assert.equal(rR8N85A.status, 'READY', `R8N85A: ${rR8N85A.reason}`)
  assert.equal(rJL676A.status, 'READY', `JL676A: ${rJL676A.reason}`)
  assert.equal(rR8N85A.status, rJL676A.status, 'Must be consistent')
})

test('14h. 6200F (floor UNVERIFIED) on 10.13 and 10.16 is UNKNOWN', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  for (const hw of [CX6200_JL724A, CX6200_JL725A, CX6200_JL726A, CX6200_JL727A, CX6200_JL728A]) {
    assert.equal(evaluateCompatibility(hw, os1013).status, 'UNKNOWN', `${hw.productNumber} on 10.13 must be UNKNOWN`)
    assert.equal(evaluateCompatibility(hw, os1016).status, 'UNKNOWN', `${hw.productNumber} on 10.16 must be UNKNOWN`)
  }
})

test('14i. CX5420 on all trains is UNKNOWN (minimumVersion UNVERIFIED)', () => {
  for (const os of AOS_CX_RELEASES) {
    const r = evaluateCompatibility(CX5420F, os)
    assert.equal(r.status, 'UNKNOWN', `CX5420 on ${os.train}: expected UNKNOWN, got ${r.status}: ${r.reason}`)
  }
})

test('14j. build comparison: floor 10.16.1006, build 10.16.1005 → BLOCKED; no build → REVIEW_REQUIRED', () => {
  // Synthetic OS at train 10.16 with verified lifecycle to isolate build-comparison logic
  const os1016verified = {
    ...AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16'),
    initialReleaseDate: '2024-01-01',  // override to verified so lifecycle check passes
  }
  // Hardware with floor 10.16.1006 (same train as OS)
  const hwFloor1006 = {
    ...CX6405,
    id: 'synthetic-floor-1006',
    minimumVersion: '10.16.1006',
  }
  const rBlocked = evaluateCompatibility(hwFloor1006, os1016verified, '10.16.1005')
  assert.equal(rBlocked.status, 'BLOCKED', `build 10.16.1005 < floor 10.16.1006 must be BLOCKED: ${rBlocked.reason}`)

  const rReview = evaluateCompatibility(hwFloor1006, os1016verified)
  assert.equal(rReview.status, 'REVIEW_REQUIRED', `no build on same-train must be REVIEW_REQUIRED: ${rReview.reason}`)
})

test('14k. hardware undefined and OS undefined both yield UNKNOWN without throwing', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const rNoHw = evaluateCompatibility(undefined, os1013)
  assert.equal(rNoHw.status, 'UNKNOWN')
  assert.equal(rNoHw.hardwareId, 'unknown')

  const rNoOs = evaluateCompatibility(CX6300M_24SFP, undefined)
  assert.equal(rNoOs.status, 'UNKNOWN')
  assert.equal(rNoOs.osId, 'unknown')

  const rBoth = evaluateCompatibility(undefined, undefined)
  assert.equal(rBoth.status, 'UNKNOWN')
})


// ──────────────────────────────────────────────────────────────────────────────
// Tes baru: lifecycle bounds dan date-driven status
// asOf disuntikkan ke computeLifecycleStatus agar tes stabil terhadap waktu.
// Referensi utama: 2026-10-16 (hari ini). Skenario tambahan: 2027-03-01.
// ──────────────────────────────────────────────────────────────────────────────

test('15a. 10.13 lifecycle ACTIVE on 2026-10-16 (EOS 2028-11-30, > 180d away)', () => {
  const os = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  assert.equal(os.lifecycleStatus, 'ACTIVE', `10.13 must be ACTIVE: ${os.notes}`)
  // Verify via direct computeLifecycleStatus call with injected asOf
  const status = computeLifecycleStatus(os.initialReleaseEarliest, os.initialReleaseLatest, os.endOfSupportDate, 5, '2026-10-16')
  assert.equal(status, 'ACTIVE')
})

test('15b. 10.16 lifecycle ACTIVE on 2026-10-16 (earliest bound official; EOS derived ~2029-05)', () => {
  const os = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  assert.equal(os.lifecycleStatus, 'ACTIVE', `10.16 must be ACTIVE: ${os.notes}`)
  const status = computeLifecycleStatus(os.initialReleaseEarliest, os.initialReleaseLatest, os.endOfSupportDate, 5, '2026-10-16')
  assert.equal(status, 'ACTIVE')
  // Earliest tier must be 'official' for ACTIVE to be granted
  assert.equal(os.initialReleaseEarliest.tier, 'official', '10.16 earliest bound must be official tier')
})

test('15c. 10.17 lifecycle EXPIRING_SOON on 2026-10-16 (SSR 1y; latestEOS 2027-02-26 within 180d)', () => {
  const os = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.17')
  // latestEOS = 2026-02-26 + 1y = 2027-02-26; 2027-02-26 - 2026-10-16 = 133d < 180d → EXPIRING_SOON
  assert.equal(os.lifecycleStatus, 'EXPIRING_SOON', `10.17 on 2026-10-16 must be EXPIRING_SOON (latestEOS 2027-02-26, 133d away): ${os.notes}`)
  const status = computeLifecycleStatus(os.initialReleaseEarliest, os.initialReleaseLatest, os.endOfSupportDate, 1, '2026-10-16')
  assert.equal(status, 'EXPIRING_SOON')
  // Earliest tier must be official
  assert.equal(os.initialReleaseEarliest.tier, 'official', '10.17 earliest bound must be official tier')
})

test('15d. 10.18 lifecycle UNKNOWN (earliest bound tier unverified; never ACTIVE)', () => {
  const os = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.18')
  assert.equal(os.lifecycleStatus, 'UNKNOWN', `10.18 must be UNKNOWN: ${os.notes}`)
  const status = computeLifecycleStatus(os.initialReleaseEarliest, os.initialReleaseLatest, os.endOfSupportDate, 1, '2026-10-16')
  assert.equal(status, 'UNKNOWN')
  assert.notEqual(status, 'ACTIVE')
})

test('15e. JL676A on 10.16 is READY (floor 10.06.0001 met; 10.16 ACTIVE; official evidence)', () => {
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  const r = evaluateCompatibility(CX6100_JL676A, os1016)
  assert.equal(r.status, 'READY', `JL676A on 10.16: ${r.reason}`)
})

test('15f. R0X27A on 10.16 is READY (floor 10.05.0001 met; 10.16 ACTIVE; official evidence)', () => {
  const hw = ARUBA_HARDWARE.find((h) => h.productNumber === 'R0X27A')
  assert.ok(hw, 'R0X27A must exist')
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  const r = evaluateCompatibility(hw, os1016)
  assert.equal(r.status, 'READY', `R0X27A on 10.16: ${r.reason}`)
})

test('15g. JL741A on 10.16 is READY (floor 10.05.0001 met; 10.16 ACTIVE; official evidence)', () => {
  const hw = ARUBA_HARDWARE.find((h) => h.productNumber === 'JL741A')
  assert.ok(hw, 'JL741A must exist')
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  const r = evaluateCompatibility(hw, os1016)
  assert.equal(r.status, 'READY', `JL741A on 10.16: ${r.reason}`)
})

test('15h. Synthetic hardware (floor 10.16.1006) on 10.16: build 10.16.1006 → READY; build 10.16.1005 → BLOCKED', () => {
  // Synthetic with official evidence so floor evidence check passes
  const hwFloor1006 = {
    ...CX6405,
    id: 'synthetic-floor-1006-test',
    minimumVersion: '10.16.1006',
    minimumVersionStatus: /** @type {const} */ ('VERIFIED'),
  }
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  // build at floor → READY (same-train, build >= floor, lifecycle ACTIVE, official evidence)
  const rReady = evaluateCompatibility(hwFloor1006, os1016, '10.16.1006')
  assert.equal(rReady.status, 'READY', `build 10.16.1006 on floor 10.16.1006: ${rReady.reason}`)
  // build below floor → BLOCKED
  const rBlocked = evaluateCompatibility(hwFloor1006, os1016, '10.16.1005')
  assert.equal(rBlocked.status, 'BLOCKED', `build 10.16.1005 < floor 10.16.1006: ${rBlocked.reason}`)
})

test('15i. Hardware floor 10.04.1000, build 10.16.1005 → REVIEW_REQUIRED (archived build)', () => {
  // Any hardware with floor below 10.16 (train > floorTrain); build = archived 10.16.1005
  const hw = ARUBA_HARDWARE.find((h) => h.productNumber === 'R0X31A')  // floor 10.04.1000
  assert.ok(hw, 'R0X31A must exist')
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  const r = evaluateCompatibility(hw, os1016, '10.16.1005')
  // cmpTrain > 0 (10.16 > 10.04), so same-train block skipped; then archived-build rule fires
  assert.equal(r.status, 'REVIEW_REQUIRED', `archived build 10.16.1005: ${r.reason}`)
  assert.ok(r.reason.includes('archived'), `reason must mention archived: ${r.reason}`)
})

test('15j. 10.17 on 2027-03-01: END_OF_SUPPORT (latestEOS 2027-02-26 < asOf)', () => {
  // 2027-03-01 > latestEOS = 2026-02-26 + 1y = 2027-02-26 → END_OF_SUPPORT
  const os = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.17')
  const status = computeLifecycleStatus(os.initialReleaseEarliest, os.initialReleaseLatest, os.endOfSupportDate, 1, '2027-03-01')
  assert.equal(status, 'END_OF_SUPPORT', `10.17 on 2027-03-01 should be END_OF_SUPPORT (latestEOS 2027-02-26)`)
})

test('15k. 10.17 on 2026-03-01: ACTIVE (earliestEOS 2026-11-20 > asOf + 180d)', () => {
  // earliestEOS = 2025-11-20 + 1y = 2026-11-20; 2026-11-20 - 2026-03-01 = 264d > 180d → ACTIVE
  const os = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.17')
  const status = computeLifecycleStatus(os.initialReleaseEarliest, os.initialReleaseLatest, os.endOfSupportDate, 1, '2026-03-01')
  assert.equal(status, 'ACTIVE', `10.17 on 2026-03-01 should be ACTIVE (earliestEOS 2026-11-20, 264d away)`)
})

test('15l. 10.17 on 2026-12-01: UNKNOWN (earliestEOS past, latestEOS future)', () => {
  // earliestEOS = 2026-11-20 < 2026-12-01; latestEOS = 2027-02-26 > 2026-12-01 → straddling → UNKNOWN
  const os = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.17')
  const status = computeLifecycleStatus(os.initialReleaseEarliest, os.initialReleaseLatest, os.endOfSupportDate, 1, '2026-12-01')
  assert.equal(status, 'UNKNOWN', `10.17 on 2026-12-01 should be UNKNOWN (straddling EOS bounds)`)
})

test('15m. JL658A on 10.17 is REVIEW_REQUIRED (lifecycle EXPIRING_SOON on 2026-10-16)', () => {
  const hw = ARUBA_HARDWARE.find((h) => h.productNumber === 'JL658A')
  const os1017 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.17')
  const r = evaluateCompatibility(hw, os1017)
  assert.equal(r.status, 'REVIEW_REQUIRED', `JL658A on 10.17 should be REVIEW_REQUIRED (lifecycle EXPIRING_SOON): ${r.reason}`)
  assert.ok(r.reason.includes('End of Support'), `reason should mention End of Support: ${r.reason}`)
})

test('15n. Real compatibility matrix — print for all hardware × trains', () => {
  console.log('\n=== Compatibility Matrix (asOf: 2026-10-16) ===')
  console.log('hardwareId | train | status | reason')
  console.log('---')
  
  ARUBA_HARDWARE.forEach((hw) => {
    AOS_CX_RELEASES.forEach((os) => {
      const r = evaluateCompatibility(hw, os)
      if (r.status !== 'UNKNOWN') {
        console.log(`${hw.productNumber.padEnd(8)} | ${os.train.padEnd(6)} | ${r.status.padEnd(17)} | ${r.reason.slice(0, 80)}`)
      }
    })
  })
  
  // Sample UNKNOWN
  const sampleUnknown = evaluateCompatibility(
    ARUBA_HARDWARE.find((h) => h.minimumVersionStatus === 'UNVERIFIED'),
    AOS_CX_RELEASES[0]
  )
  console.log(`... (UNKNOWN entries omitted; sample): ${sampleUnknown.reason.slice(0, 60)}`)
  console.log('===\n')
})

