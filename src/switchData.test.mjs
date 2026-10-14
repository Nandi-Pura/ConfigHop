import test from 'node:test'
import assert from 'node:assert/strict'
import {
  autoMapSwitchPorts, changeSwitchPort, filterSwitchPorts,
  switchCatalog, switchOsLabel, switchPorts, switchSource, switchTarget,
  ARUBA_HARDWARE, getArubaSeries, getArubaHardwareBySeries, getArubaHardwareById,
  getCompatibleOs, evaluateCompatibility, AOS_CX_RELEASES,
  compareVersions, isVersionAtOrAboveFloor,
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

test('3. Compatibility matrix - CX6300M JL658A rules UNKNOWN (no verified evidence yet)', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  const os1017 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.17')
  const r1013 = evaluateCompatibility(CX6300M_24SFP, os1013)
  const r1016 = evaluateCompatibility(CX6300M_24SFP, os1016)
  const r1017 = evaluateCompatibility(CX6300M_24SFP, os1017)
  assert.ok(r1013.status === 'UNKNOWN' || r1013.status === 'REVIEW_REQUIRED', `10.13: ${r1013.status}`)
  assert.ok(r1016.status === 'UNKNOWN' || r1016.status === 'REVIEW_REQUIRED', `10.16: ${r1016.status}`)
  assert.ok(r1017.status === 'UNKNOWN' || r1017.status === 'REVIEW_REQUIRED', `10.17: ${r1017.status}`)
  assert.notEqual(r1013.status, 'READY')
  assert.notEqual(r1016.status, 'READY')
})

test('4. Verified hardware (CX6400 v2) is BLOCKED on 10.13, READY on 10.16+', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const os1016 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.16')
  const r1013 = evaluateCompatibility(CX6400_V2, os1013)
  const r1016 = evaluateCompatibility(CX6400_V2, os1016)
  assert.equal(r1013.status, 'BLOCKED')
  assert.equal(r1016.status, 'READY')
  if (r1013.evidence) {
    assert.ok(r1013.evidence.includes('ARUBA-EVD-CX6400V2-1016'))
  }
  if (r1016.evidence) {
    assert.ok(r1016.evidence.includes('ARUBA-EVD-CX6400V2-1016'))
  }
})

test('5. Deprecated product mappings removed', () => {
  assert.equal(getArubaHardwareById('aruba-cx-6300-48g'), undefined)
  assert.equal(getArubaHardwareById('aruba-cx-6300-24sfp'), undefined)
})

test('6. Unknown compatibility returns UNKNOWN, never fabricates READY', () => {
  const os1013 = AOS_CX_RELEASES.find((r) => r.id === 'aos-cx-10.13')
  const r = evaluateCompatibility(CX6000_R8N85A, os1013)
  assert.equal(r.status, 'UNKNOWN')
  assert.notEqual(r.status, 'READY')
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
  assert.ok(CX6400_V2.evidenceIds.includes('ARUBA-EVD-CX6400V2-1016'))
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

test('11. CX 6400 chassis vs management module distinction', () => {
  assert.equal(CX6405.hardwareRole, 'chassis')
  assert.equal(CX6410.hardwareRole, 'chassis')
  assert.equal(CX6400_V2.hardwareRole, 'management-module')
  assert.equal(CX6400_MGMT_V1.hardwareRole, 'management-module')

  assert.equal(CX6405.productNumber, 'R0X26A')
  assert.equal(CX6410.productNumber, 'R0X27A')
  assert.equal(CX6400_V2.productNumber, 'JL741A')
  assert.equal(CX6400_MGMT_V1.productNumber, 'R0X31A')

  assert.ok(CX6400_V2.notes?.includes('NOT A STANDALONE SWITCH'))
  assert.ok(CX6400_MGMT_V1.notes?.includes('NOT A STANDALONE SWITCH'))
})

test('12. Phase 2.3 Section 16 - CX 6300 official SKUs and VSF specs', () => {
  assert.equal(CX6300M_24SFP.productNumber, 'JL658A')
  assert.equal(CX6300M_24SFP.minimumVersion, '10.04.3000')
  assert.equal(CX6300M_24SFP.ports.length, 28)
  assert.equal(CX6300M_24SFP.totalAccessPorts, 24)
  assert.equal(CX6300M_24SFP.totalUplinkPorts, 4)
  assert.equal(CX6300M_24SFP.poeCapable, false)

  assert.equal(CX6300M_48SR5_POE.productNumber, 'JL659A')
  assert.equal(CX6300M_48SR5_POE.minimumVersion, '10.04.3000')
  assert.equal(CX6300M_48SR5_POE.ports.length, 52)
  assert.equal(CX6300M_48SR5_POE.totalAccessPorts, 48)
  assert.equal(CX6300M_48SR5_POE.totalUplinkPorts, 4)
  assert.equal(CX6300M_48SR5_POE.poeCapable, true)

  assert.equal(CX6300M_24SR5_POE.productNumber, 'JL660A')
  assert.equal(CX6300M_24SR5_POE.minimumVersion, '10.04.3000')
  assert.equal(CX6300M_24SR5_POE.ports.length, 28)
  assert.equal(CX6300M_24SR5_POE.totalAccessPorts, 24)
  assert.equal(CX6300M_24SR5_POE.totalUplinkPorts, 4)
  assert.equal(CX6300M_24SR5_POE.poeCapable, true)

  assert.equal(CX6300M_48G_POE.productNumber, 'JL661A')
  assert.equal(CX6300M_48G_POE.minimumVersion, '10.04.3000')
  assert.equal(CX6300M_48G_POE.ports.length, 52)
  assert.equal(CX6300M_48G_POE.totalAccessPorts, 48)
  assert.equal(CX6300M_48G_POE.totalUplinkPorts, 4)
  assert.equal(CX6300M_48G_POE.poeCapable, true)

  assert.equal(CX6300M_24G_POE.productNumber, 'JL662A')
  assert.equal(CX6300M_24G_POE.minimumVersion, '10.04.3000')
  assert.equal(CX6300M_24G_POE.ports.length, 28)
  assert.equal(CX6300M_24G_POE.totalAccessPorts, 24)
  assert.equal(CX6300M_24G_POE.totalUplinkPorts, 4)
  assert.equal(CX6300M_24G_POE.poeCapable, true)

  assert.equal(CX6300M_48G_NONPOE.productNumber, 'JL663A')
  assert.equal(CX6300M_48G_NONPOE.minimumVersion, '10.04.3000')
  assert.equal(CX6300M_48G_NONPOE.ports.length, 52)
  assert.equal(CX6300M_48G_NONPOE.totalAccessPorts, 48)
  assert.equal(CX6300M_48G_NONPOE.totalUplinkPorts, 4)
  assert.equal(CX6300M_48G_NONPOE.poeCapable, false)

  assert.equal(CX6300M_24G_NONPOE.productNumber, 'JL664A')
  assert.equal(CX6300M_24G_NONPOE.minimumVersion, '10.04.0001')
  assert.equal(CX6300M_24G_NONPOE.ports.length, 28)
  assert.equal(CX6300M_24G_NONPOE.totalAccessPorts, 24)
  assert.equal(CX6300M_24G_NONPOE.totalUplinkPorts, 4)
  assert.equal(CX6300M_24G_NONPOE.poeCapable, false)

  assert.equal(isVersionAtOrAboveFloor('10.04.2999', CX6300M_24SFP.minimumVersion), false)
  assert.equal(isVersionAtOrAboveFloor('10.04.3000', CX6300M_24SFP.minimumVersion), true)
  assert.equal(isVersionAtOrAboveFloor('10.04.3001', CX6300M_24SFP.minimumVersion), true)
  assert.equal(isVersionAtOrAboveFloor('10.13.0001', CX6300M_24SFP.minimumVersion), true)
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
