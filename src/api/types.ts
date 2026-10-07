export type PreviewStatus = 'READY' | 'REVIEW_REQUIRED' | 'BLOCKED'
export type ProjectStatus = 'EMPTY' | 'SOURCE_READY' | 'PREVIEW_READY' | 'PREVIEW_REVIEW_REQUIRED' | 'PREVIEW_BLOCKED' | 'CANDIDATE_READY'

export interface ProjectState {
  project_id: string
  state: ProjectStatus
  source_available: boolean
  source_filename: string | null
  source_size_bytes: number | null
  target_profile_id: string | null
  source_profile_id: string | null
  source_panos_train: string | null
  target_panos_train: string | null
  preview_available: boolean
  preview_status: PreviewStatus | null
  candidate_available: boolean
  candidate_sha256: string | null
  candidate_size_bytes: number | null
}

export interface InventorySummary {
  physical_interfaces: number
  subinterfaces: number
  aggregate_interfaces: number
  vlan_interfaces: number
  loopbacks: number
  zones: number
  virtual_routers: number
  static_routes: number
  address_objects: number
  service_objects: number
  security_rules: number
  nat_rules: number
  parser_warnings: number
}

export interface ParserWarning { code: string; object_type: string; object_name: string | null; field: string; message: string }
export interface DependencySummary {
  zone_references: number
  virtual_router_references: number
  static_route_references: number
  nat_references: number
  aggregate_memberships: number
  child_count: number
}
export interface PhysicalInterfaceView {
  name: string
  mode: string
  ip_addresses: string[]
  management_profile: string | null
  aggregate_group: string | null
  subinterface_count: number
  subinterface_names: string[]
  zone_names: string[]
  dependency_count: number
  dependency_summary: DependencySummary
}
export interface InventoryView {
  platform: { vendor: string; config_version: string | null; detail_version: string | null; source_format: string }
  summary: InventorySummary
  physical_interfaces: PhysicalInterfaceView[]
  parser_warnings: ParserWarning[]
}
export interface HardwareProfileSummary { id: string; vendor: string; model: string; series: string | null; profile_status: string; target_render_support?: 'SUPPORTED' | 'ANALYSIS_ONLY'; interface_count: number; verified_at: string | null; candidate_ready_interface_count: number; native_interface_count: number; conditional_interface_count: number; breakout_interface_count: number; supported_panos_trains: string[]; evidence_ids: string[] }
export interface HardwarePort { name: string; availability: 'NATIVE' | 'NATIVE_CONDITIONAL' | 'BREAKOUT_CHILD'; candidate_support: 'SUPPORTED' | 'CONDITIONAL' | 'BLOCKED'; required_condition: string; parent_interface: string | null; speed_capabilities: string[]; media_capabilities: string[]; evidence_ids: string[] }
export interface HardwareProfileDetail extends HardwareProfileSummary { interfaces: string[]; port_details: HardwarePort[]; first_supported_release: string | null; notes: string | null }
export interface EvidenceRecord { id: string; source_title: string; source_url: string; source_type: string; checked_at: string; scope: string; summary: string; status: string }
export interface CompatibilityFinding { code: string; severity: 'INFO' | 'WARNING' | 'ERROR'; message: string; source_interface: string | null; target_interface: string | null; evidence_ids: string[] }
export interface InterfaceAssessment { source_interface: string; target_interface: string; explicit_mapping: boolean; configured_source_speed: string | null; status: PreviewStatus; findings: CompatibilityFinding[]; evidence_ids: string[] }
export interface CompatibilityAssessment { platform: { status: PreviewStatus; effective_source_version: string | null; source_version_status: string; target_version_status: string; findings: CompatibilityFinding[] }; hardware: { status: PreviewStatus; effective_assignments: InterfaceAssessment[]; findings: CompatibilityFinding[] }; status: PreviewStatus; findings: CompatibilityFinding[]; evidence_ids: string[] }
export interface InterfaceMapping { source_interface: string; target_interface: string; target_settings?: { link_speed: '40G' | '100G' } }
export interface MigrationFinding { code: string; severity: 'INFO' | 'WARNING' | 'ERROR'; scope: string; source_interface: string | null; target_interface: string | null; object_type: string | null; object_name: string | null; message: string }
export interface ReferenceChange { reference_type: string; object_type: string; object_name: string; scope: string; field: string; old_value: string; new_value: string; action: string; status: string }
export interface MappingImpact { source_interface: string; target_interface: string; mapping_status: string; derived_subinterfaces: { source_interface: string; target_interface: string; tag: number | null }[]; reference_changes: ReferenceChange[]; findings: MigrationFinding[] }
export interface MigrationPreview {
  mappings: InterfaceMapping[]
  impacts: MappingImpact[]
  findings: MigrationFinding[]
  summary: { submitted_mappings: number; valid_mappings: number; derived_subinterface_mappings: number; zone_reference_changes: number; virtual_router_reference_changes: number; static_route_reference_changes: number; nat_reference_changes: number; aggregate_membership_changes: number; review_findings: number; blocking_findings: number }
  status: PreviewStatus
  overall_status?: PreviewStatus
  platform_assessment?: CompatibilityAssessment['platform'] | null
  hardware_assessment?: CompatibilityAssessment['hardware'] | null
}
export interface RenderFinding { code: string; severity: 'INFO' | 'WARNING' | 'ERROR'; message: string }
export interface TransformationOperation { sequence: number; operation_type: string; source_value: string; target_value: string; object_type: string; object_name: string; scope: string; field: string; expected_occurrences: number }
export interface TransformationPlan { source_sha256: string; source_inventory_sha256: string; target_profile_vendor: string; target_profile_model: string; target_profile_status: string; preview_status: PreviewStatus; operations: TransformationOperation[]; findings: RenderFinding[]; status: PreviewStatus }
export interface SemanticChange { category: string; object_type: string; object_name: string; scope: string; old_value: string; new_value: string; status: string }
export interface SemanticMigrationDiff { changes: SemanticChange[] }
export interface CandidateMetadata {
  status: PreviewStatus
  candidate_available: boolean
  candidate_sha256: string | null
  candidate_size_bytes: number | null
  preview_status: PreviewStatus
  plan_status: PreviewStatus
  validation: { candidate_parse_ok: boolean; expected_inventory_match: boolean; preservation_audit_ok: boolean; operations_planned: number; operations_applied: number; valid: boolean } | null
  semantic_diff: SemanticMigrationDiff | null
  findings: RenderFinding[]
  plan: TransformationPlan | null
  summary: MigrationPreview['summary']
  source_profile_id: string | null
  target_profile_id: string | null
  source_profile_status: string | null
  target_profile_status: string | null
  effective_panos_version: string | null
  platform_assessment_status: string | null
  hardware_assessment_status: string | null
  evidence_ids: string[]
}
export interface ApiError { error: { code: string; message: string } }
