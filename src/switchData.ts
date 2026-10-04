export type SwitchPlatform = { vendor: string; hardware: { model: string; series: string }; software: { product: string; version: string; train: string } }
export type SwitchPort = { id: number; source: string; mode: string; vlan: string; speed: string; lag: string; suggested: string; target: string; status: 'Mapped' | 'Review' | 'Unmapped'; notes: string }

const models: Record<string, Record<string, string[]>> = {
  Cisco: {
    'Catalyst 9200 Series': ['C9200-24P', 'C9200-48P', 'C9200L-24P-4G', 'C9200L-48P-4G'],
    'Catalyst 9300 Series': ['C9300-24P', 'C9300-48P', 'C9300-24T', 'C9300-48T', 'C9300X-24Y', 'C9300X-48HX'],
    'Catalyst 9400 Series': ['C9404R', 'C9407R', 'C9410R'],
  },
  'HPE Aruba Networking': {
    'CX 6100 Series': ['CX 6100 24G', 'CX 6100 48G'],
    'CX 6200 Series': ['CX 6200F 24G', 'CX 6200F 48G', 'CX 6200M 24G', 'CX 6200M 48G'],
    'CX 6300 Series': ['CX 6300M 24G', 'CX 6300M 48G', 'CX 6300F 24G', 'CX 6300F 48G'],
    'CX 6400 Series': ['CX 6405', 'CX 6410'],
  },
  'Juniper Networks': {
    'EX3400 Series': ['EX3400-24P', 'EX3400-48P'],
    'EX4100 Series': ['EX4100-24P', 'EX4100-48P'],
    'EX4400 Series': ['EX4400-24P', 'EX4400-48P'],
    'EX4650 Series': ['EX4650-48Y'],
  },
}
const software: Record<string, { product: string; versions: string[]; train: string }> = {
  Cisco: { product: 'IOS XE', versions: ['17.9', '17.10', '17.11', '17.12'], train: '17.x' },
  'HPE Aruba Networking': { product: 'AOS-CX', versions: ['10.11', '10.12', '10.13', '10.14'], train: '10.x' },
  'Juniper Networks': { product: 'Junos', versions: ['21.4R3', '22.4R3', '23.2R2', '23.4R1'], train: '21.x–23.x' },
}
export const switchCatalog: SwitchPlatform[] = Object.entries(models).flatMap(([vendor, series]) => Object.entries(series).flatMap(([name, devices]) => devices.flatMap((model) => software[vendor].versions.map((version) => ({ vendor, hardware: { model, series: name }, software: { product: software[vendor].product, version, train: software[vendor].train } })))))
export const switchSource = switchCatalog.find((item) => item.hardware.model === 'C9300-48P' && item.software.version === '17.12')!
export const switchTarget = switchCatalog.find((item) => item.hardware.model === 'CX 6300M 48G' && item.software.version === '10.13')!
export const switchOsLabel = (item: SwitchPlatform) => `${item.software.product} ${item.software.version}`

export const switchConfig = `version 17.12.3
hostname C9300-CORE
vlan 10
 name USERS
vlan 20
 name VOICE
vlan 30
 name SERVERS
vlan 99
 name MANAGEMENT
vlan 999
 name NATIVE
interface GigabitEthernet1/0/1
 description USER-FLOOR-1
 switchport mode access
 switchport access vlan 10
 switchport voice vlan 20
 spanning-tree portfast
interface GigabitEthernet1/0/2
 description IP-PHONE
 switchport mode access
 switchport access vlan 20
 spanning-tree portfast
interface TenGigabitEthernet1/1/1
 description UPLINK-DISTRIBUTION-A
 switchport trunk native vlan 999
 switchport trunk allowed vlan 10,20,30,99,999
 switchport mode trunk
 channel-group 1 mode active
interface TenGigabitEthernet1/1/2
 description UPLINK-DISTRIBUTION-B
 switchport trunk native vlan 999
 switchport trunk allowed vlan 10,20,30,99,999
 switchport mode trunk
 channel-group 1 mode active
interface Port-channel1
 description UPLINK-DISTRIBUTION
 switchport trunk native vlan 999
 switchport trunk allowed vlan 10,20,30,99,999
 switchport mode trunk
interface Vlan99
 description MANAGEMENT
 ip address 10.99.0.1 255.255.255.0
ip route 0.0.0.0 0.0.0.0 10.99.0.254`

export const switchCandidate = `hostname CX6300-CORE
vlan 10
    name USERS
vlan 20
    name VOICE
vlan 30
    name SERVERS
vlan 99
    name MANAGEMENT
vlan 999
    name NATIVE
interface 1/1/1
    description USER-FLOOR-1
    no shutdown
    vlan access 10
    voice vlan 20
    spanning-tree port-type admin-edge
interface 1/1/2
    description IP-PHONE
    no shutdown
    vlan access 20
    spanning-tree port-type admin-edge
interface 1/1/49
    description UPLINK-DISTRIBUTION-A
    no shutdown
    lag 1
interface 1/1/50
    description UPLINK-DISTRIBUTION-B
    no shutdown
    lag 1
interface lag 1
    description UPLINK-DISTRIBUTION
    no shutdown
    no routing
    vlan trunk native 999
    vlan trunk allowed 10,20,30,99,999
    lacp mode active
interface vlan 99
    ip address 10.99.0.1/24
ip route 0.0.0.0/0 10.99.0.254`

export const switchInventory = [
  ['48', 'Physical Interfaces'], ['12', 'VLANs'], ['6', 'SVIs'], ['4', 'LAGs / Port-Channels'],
  ['2', 'VRFs'], ['18', 'Access Ports'], ['22', 'Trunk Ports'], ['4', 'Routed Ports'],
  ['1', 'STP Instance'], ['3', 'ACLs'], ['5', 'QoS Policies'], ['2', 'Switch Stacks / Stacking Units'],
] as const

export const switchPorts: SwitchPort[] = Array.from({ length: 48 }, (_, index) => {
  const id = index + 1
  const review = id === 47 || id === 48
  const unmapped = id === 45 || id === 46
  return {
    id, source: `Gi1/0/${id}`, mode: review ? 'Trunk' : 'Access',
    vlan: review ? '10,20,30,99,999' : id === 2 ? 'VLAN 20 / Voice' : id === 10 ? 'VLAN 30 / Servers' : 'VLAN 10 / Users',
    speed: review ? '10G' : '1G', lag: review ? 'Po1' : '—',
    suggested: `1/1/${review ? id + 2 : id}`, target: unmapped ? 'None' : `1/1/${review ? id + 2 : id}`,
    status: unmapped ? 'Unmapped' : review ? 'Review' : 'Mapped',
    notes: review ? 'Uplink to distribution' : id === 1 ? 'User access port' : id === 2 ? 'IP Phone port' : id === 10 ? 'Server access port' : 'Access port',
  }
})

export const filterSwitchPorts = (ports: SwitchPort[], filter: string, search: string) => ports.filter((port) =>
  (filter === 'All' || (filter === 'Mapped' ? port.target !== 'None' : filter === 'Unmapped' ? port.target === 'None' : filter === 'Review' ? port.status === 'Review' : false)) &&
  `${port.source} ${port.mode} ${port.vlan} ${port.target} ${port.notes}`.toLowerCase().includes(search.toLowerCase()),
)
export const changeSwitchPort = (ports: SwitchPort[], id: number, target: string): SwitchPort[] => ports.map((row) => row.id === id ? { ...row, target, status: target === 'None' ? 'Unmapped' : row.status === 'Review' || target !== row.suggested ? 'Review' : 'Mapped' } : row)
export const autoMapSwitchPorts = (ports: SwitchPort[]): SwitchPort[] => ports.map((row) => ({ ...row, target: row.suggested, status: row.status === 'Review' ? 'Review' : 'Mapped' }))

export const switchVlans = [
  { id: 10, name: 'USERS', target: '10', targetName: 'USERS', status: 'Mapped' },
  { id: 20, name: 'VOICE', target: '20', targetName: 'VOICE', status: 'Mapped' },
  { id: 30, name: 'SERVERS', target: '30', targetName: 'SERVERS', status: 'Mapped' },
  { id: 99, name: 'MANAGEMENT', target: '99', targetName: 'MANAGEMENT', status: 'Mapped' },
  { id: 999, name: 'NATIVE', target: '999', targetName: 'NATIVE', status: 'Review' },
]
