export type PreviewStatus = 'READY' | 'REVIEW_REQUIRED' | 'BLOCKED'
export type TargetRenderSupport = 'SUPPORTED' | 'SCOPED' | 'ANALYSIS_ONLY'
export type RequiredCondition = 'NONE' | 'BREAKOUT_MODE' | 'MANUAL_NATIVE_PORT_SPEED' | 'AUTO_ONLY_LINK_FIELDS_ABSENT' | 'OPTIC_CONTEXT_LINK_FIELDS_ABSENT' | 'TARGET_LINK_SERIALIZATION_UNVERIFIED'
export type TargetOpticRate = '1G' | '10G' | '40G' | '100G'
export type ProjectStatus = 'EMPTY' | 'SOURCE_READY' | 'SOURCE_INTEGRITY_FAILED' | 'PREVIEW_READY' | 'PREVIEW_REVIEW_REQUIRED' | 'PREVIEW_BLOCKED' | 'CANDIDATE_READY'

export interface SourceProvenance {
  origin: 'FILE_UPLOADED' | 'API_COLLECTED'
  snapshot_kind: 'UNVERIFIED' | 'RUNNING'
  sha256: string
  received_at_utc: string
  serial: string | null
  model: string | null
  panos_version: string | null
  hostname: string | null
}

export interface SourceUpload {
  project_id: string
  filename: string
  size_bytes: number
  provenance: SourceProvenance
}

export interface SourceConnectionInput {
  host: string
  port: number
  api_key: string
  ca_certificate_pem?: string | null
}

export interface SourceDeviceIdentity {
  hostname: string
  serial: string
  model: string
  panos_version: string
}

export interface SourceConnectionTest {
  host: string
  port: number
  tested_at_utc: string
  tls_verification: 'CA_VERIFIED'
  identity: SourceDeviceIdentity
}

export interface ProjectState {
  project_id: string
  state: ProjectStatus
  source_available: boolean
  source_filename: string | null
  source_size_bytes: number | null
  source_provenance: SourceProvenance | null
  active_package_id: string | null
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

export interface TargetBaseline {
  baseline_id: string
  serial: string
  model: string
  hostname: string
  panos_version: string
  multi_vsys: boolean | null
  operational_mode: string | null
  sha256: string
  artifact_format: 'AES_256_GCM_V1' | null
  artifact_size_bytes: number | null
  observed_at_utc: string
}

export interface TargetPackageChange { scope: string; object_name: string; action: 'ADDED' | 'REPLACED' }
export interface TargetPackageFinding { code: string; severity: 'INFO' | 'WARNING' | 'ERROR'; scope: string; message: string; requires_acceptance: boolean }
export interface DeploymentPackage {
  package_id: string
  target_baseline_sha256: string | null
  target_serial: string | null
  candidate_sha256: string | null
  deployable_candidate_sha256: string | null
  target_changes: TargetPackageChange[]
  target_preservation: Record<string, 'PRESERVED'>
  target_findings: TargetPackageFinding[]
  review_id: string | null
  review_sha256: string | null
  status: string
}

export interface TargetPreflight {
  target_serial: string
  package_id: string | null
  observed_at_utc: string
  status: 'BLOCKED' | 'INCOMPLETE' | 'PASSED'
  checks: Record<string, 'CLEAR' | 'BLOCKED' | 'NOT_CHECKED'>
  blockers: string[]
  deployment_allowed: boolean
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
  link_state: string | null
  link_speed: string | null
  link_duplex: string | null
  link_speed_explicit: boolean
  link_duplex_explicit: boolean
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
export interface HardwareProfileSummary { id: string; vendor: string; model: string; series: string | null; profile_status: string; target_render_support?: TargetRenderSupport; interface_count: number; verified_at: string | null; candidate_ready_interface_count: number; native_interface_count: number; conditional_interface_count: number; breakout_interface_count: number; supported_panos_trains: string[]; evidence_ids: string[] }
export interface HardwarePort { name: string; availability: 'NATIVE' | 'NATIVE_CONDITIONAL' | 'BREAKOUT_CHILD'; candidate_support: 'SUPPORTED' | 'CONDITIONAL' | 'BLOCKED'; required_condition: RequiredCondition; parent_interface: string | null; speed_capabilities: string[]; media_capabilities: string[]; evidence_ids: string[] }
export interface HardwareProfileDetail extends HardwareProfileSummary { interfaces: string[]; port_details: HardwarePort[]; first_supported_release: string | null; notes: string | null }
export interface EvidenceRecord { id: string; source_title: string; source_url: string; source_type: string; checked_at: string; scope: string; summary: string; status: string }
export interface CompatibilityFinding { code: string; severity: 'INFO' | 'WARNING' | 'ERROR'; message: string; source_interface: string | null; target_interface: string | null; evidence_ids: string[] }
export interface InterfaceAssessment { source_interface: string; target_interface: string; explicit_mapping: boolean; configured_source_speed: string | null; source_speed_capabilities: string[]; target_speed_capabilities: string[]; source_media_capabilities: string[]; target_media_capabilities: string[]; target_availability: HardwarePort['availability'] | null; candidate_support: HardwarePort['candidate_support'] | null; status: PreviewStatus; findings: CompatibilityFinding[]; evidence_ids: string[] }
export interface CompatibilityAssessment { platform: { status: PreviewStatus; effective_source_version: string | null; source_version_status: string; target_version_status: string; findings: CompatibilityFinding[] }; hardware: { status: PreviewStatus; effective_assignments: InterfaceAssessment[]; findings: CompatibilityFinding[] }; status: PreviewStatus; findings: CompatibilityFinding[]; evidence_ids: string[] }
export interface InterfaceMapping { source_interface: string; target_interface: string; target_settings?: { link_speed?: '40G' | '100G'; optic_rate?: TargetOpticRate } }
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
  deployment_plan?: DeploymentPlan | null
}
export interface RenderFinding { code: string; severity: 'INFO' | 'WARNING' | 'ERROR'; message: string }
export interface TransformationOperation { sequence: number; operation_type: string; source_value: string; target_value: string; object_type: string; object_name: string; scope: string; field: string; expected_occurrences: number }
export interface TransformationPlan { source_sha256: string; source_inventory_sha256: string; target_profile_vendor: string; target_profile_model: string; target_profile_status: string; preview_status: PreviewStatus; operations: TransformationOperation[]; findings: RenderFinding[]; status: PreviewStatus }
export type RequirementCategory = 'PHYSICAL_OPTIC' | 'CABLING' | 'REMOTE_PEER' | 'INTERFACE_VALIDATION' | 'DEPENDENCY_BOUNDARY' | 'CONFIGURATION_VALIDATION' | 'ROLLBACK_PREPARATION' | 'POST_CHANGE_VERIFICATION'
export type RequirementPhase = 'PRE_CHANGE' | 'CUTOVER' | 'POST_CHANGE'
export type VerificationStatus = 'NOT_VERIFIED' | 'ENGINEER_ACTION_REQUIRED' | 'BLOCKED' | 'INFORMATIONAL'
export interface DeploymentRequirement { id: string; category: RequirementCategory; phase: RequirementPhase; source_interface: string | null; target_interface: string | null; title: string; description: string; status: VerificationStatus; target_port_type: string | null; target_rate_capabilities: string[]; selected_optic_rate: TargetOpticRate | null; source_configured_speed: string | null; finding_codes: string[]; evidence_ids: string[]; operator_action_required: boolean }
export interface DeploymentBlocker { code: string; message: string; source_interface: string | null; target_interface: string | null; evidence_ids: string[] }
export interface DeploymentPlan { source_profile_id: string; target_profile_id: string; target_render_support: TargetRenderSupport; source_panos_train: string; target_panos_train: string; assessment_status: PreviewStatus; candidate_validation: { candidate_parse_ok: boolean; expected_inventory_match: boolean; preservation_audit_ok: boolean; operations_applied: number; valid: boolean } | null; physical_verification_status: VerificationStatus; configuration_operations: TransformationOperation[]; deployment_requirements: DeploymentRequirement[]; blockers: DeploymentBlocker[]; review_findings: DeploymentBlocker[]; evidence_ids: string[]; unavailable_evidence_ids: string[] }
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
  target_render_support: TargetRenderSupport | null
  effective_panos_version: string | null
  platform_assessment_status: string | null
  hardware_assessment_status: string | null
  evidence_ids: string[]
  deployment_plan?: DeploymentPlan | null
}
export interface ApiError { error: { code: string; message: string } }
