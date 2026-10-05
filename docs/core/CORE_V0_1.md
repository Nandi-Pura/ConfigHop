# ConfigHop Core v0.1

## Purpose and boundary

Core v0.1 reads a local Palo Alto Networks XML configuration and returns a JSON-serializable Pydantic source inventory. It does not modify the source file or connect to the frontend. It does not generate target configuration, map interfaces, translate vendors, or execute a migration. There is no API, database, or background service.

This parser supports inventory extraction for the XML structures listed below. It is not a complete PAN-OS implementation. Core v0.1 has been tested against a supplied PAN-OS 11.1.4 XML configuration for the inventory structures covered here.

## Input and output

The input is a local PAN-OS `<config>` XML export, limited to 100 MiB. `parse_palo_alto_xml(path)` returns `PaloAltoInventory`; `inventory.model_dump_json()` serializes the result. The inventory may contain object names, addresses, policy details, and other configuration data, so consumers must treat full JSON output as sensitive.

The count-only inspection command prints platform version and counts for physical Ethernet, subinterfaces, aggregate Ethernet, VLAN interfaces, loopbacks, VSYS, zones, virtual routers, static routes, address objects, service objects, security rules, NAT rules, and warnings. It does not print configuration values or warning object names.

## Supported structures

- Root config and detail version metadata; device entries.
- Ethernet Layer 3, Layer 2, virtual-wire, and aggregate-member modes, with available link attributes, management profile, and IP addresses.
- Layer 3 and Layer 2 Ethernet units, VLAN tags, parent-child relationships, management profiles, IP addresses, and available TCP MSS setting.
- Aggregate Ethernet objects and member inversion from physical `<aggregate-group>` references.
- VLAN and loopback interface units.
- Zones with VSYS ownership and interface members.
- Virtual-router interface members; IPv4 static routes with IP or next-VR next hop.
- Shared and VSYS address and service objects; scoped security and NAT rule inventory in source order.
- Major NAT translation form and interface-address references.

Unknown unrelated XML sections are ignored. Unsupported address/service forms and route next-hop types can produce structured warnings. Invalid IP text is retained with a redacted warning rather than silently rewritten.

## Explicitly unsupported

Dynamic routing details, XML schemas, hardware model inference, full NAT semantics, App-ID conversion, policy translation, cross-vendor conversion, interface remapping, dependency propagation, and candidate configuration generation are outside v0.1.

## Safety and private sample

`defusedxml` rejects DTDs, entities, and external references. The parser checks file size before and after reading, returns controlled errors for malformed or oversized input, and does not log XML content. The local `local-samples/` directory is gitignored. Never commit the supplied real XML, a transformed copy of it, or its full JSON inventory.

Public tests use only two synthetic fixtures with generic names and documentation IP ranges. The real XML is used only for local count-only integration inspection. On the supplied sample, the implemented structures matched the expected inventory counts; three VLAN-interface IP values yielded `INVALID_IP_VALUE` warnings. The parser preserved those values in inventory and did not print them in the summary.

## Run locally on Windows PowerShell

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m pytest -q
python -m confighop_core.inspect "..\local-samples\paloalto\backup7sept2026.xml"
```

The Python package runs independently of the existing frontend. From the repository root, `npm test` and `npm run build` verify the frontend.

## Next boundary

Core v0.2 may add Physical Interface Mapping and a dependency propagation preview: for example, `ethernet1/12 → ethernet1/5`, `ethernet1/12.262 → ethernet1/5.262`, and affected zone, virtual-router, static-route, and NAT interface references. v0.1 performs none of those transformations.
