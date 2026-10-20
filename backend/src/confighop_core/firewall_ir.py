from confighop_core.models.firewall import FirewallIR


def finalize_ir(ir: FirewallIR) -> FirewallIR:
    categories = [('interface', ir.interfaces), ('zone', ir.zones), ('address', ir.addresses),
        ('address_group', ir.address_groups), ('service', ir.services), ('service_group', ir.service_groups),
        ('schedule', ir.schedules), ('policy', ir.policies), ('nat', ir.nat), ('route', ir.routes)]
    for kind, category in categories:
        for item in category:
            item.source_name = item.source_name or item.name
            item.identity = f'{item.scope}:{item.source_name}'
            item.source_location = f'line {item.line}' if item.line else item.identity
            if kind == 'interface':
                item.dependencies = list(filter(None, [item.parent, *item.members]))
            elif kind == 'zone':
                item.dependencies = item.interfaces.copy()
            elif kind in {'address_group', 'service_group'}:
                item.dependencies = item.members.copy()
            elif kind == 'policy':
                item.dependencies = list(dict.fromkeys(item.source_zones + item.destination_zones + item.sources + item.destinations + item.services + ([item.schedule] if item.schedule != 'always' else [])))
            elif kind == 'nat':
                item.dependencies = list(dict.fromkeys(item.source_zones + item.destination_zones + item.sources + item.destinations + ([item.service] if item.service != 'any' else []) + ([item.related_policy] if item.related_policy else [])))
            elif kind == 'route':
                item.dependencies = list(filter(None, [item.interface, item.router]))
            item.findings = [finding for finding in ir.findings if finding.entity == item.name]
            if any(f.severity == 'BLOCKED' for f in item.findings):
                item.translation_status = 'BLOCKED'
            elif item.findings:
                item.translation_status = 'REVIEW_REQUIRED'
    return ir
