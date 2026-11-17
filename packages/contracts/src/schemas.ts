/**
 * Single source of truth for every payload that crosses a RevenueOS boundary.
 * TypeScript types are inferred from these schemas; JSON Schema is generated
 * from them (scripts/generate.ts) and Python pydantic models are generated from
 * that JSON Schema, so both languages validate the same contract.
 *
 * Conditional rules (high-risk calls need an approval, an LLM verifier cannot
 * PASS, a verified claim needs sources) are expressed as unions of strict
 * objects, which survive the JSON Schema to pydantic step intact.
 */
import { z } from "zod";

export const Sha256 = z.string().regex(/^[0-9a-f]{64}$/);
export const Uuid = z.uuid();
export const RiskLow = z.enum(["low", "medium"]);
export const RiskHigh = z.enum(["high", "critical"]);
export const TaskState = z.enum([
  "DRAFT", "RESEARCHED", "PLANNED", "AWAITING_APPROVAL", "EXECUTING", "EVIDENCE_SUBMITTED",
  "VERIFYING", "QC_PASSED", "COMPLETED", "BLOCKED", "FAILED_QC", "CANCELLED", "BUDGET_HALTED",
  "AWAITING_HUMAN_APPROVAL",
]);
export const OracleTier = z.enum(["L1", "L2", "L3", "L4"]);
const Traceparent = z.string().regex(/^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$/);

const toolCallBase = {
  task_id: Uuid,
  agent_id: Uuid,
  server: z.string().min(1),
  tool: z.string().min(1),
  args: z.record(z.string(), z.unknown()),
  traceparent: Traceparent.optional(),
};

/** MCP tool-call envelope. High and critical calls must carry an approval (INV-06). */
export const ToolCallEnvelope = z.union([
  z.strictObject({ ...toolCallBase, risk_class: RiskLow, approval_id: Uuid.optional() }),
  z.strictObject({ ...toolCallBase, risk_class: RiskHigh, approval_id: Uuid }),
]);

/** Immutable receipt for one tool call (INV-02). */
export const Receipt = z.strictObject({
  tool_call_id: Uuid,
  task_id: Uuid,
  agent_id: Uuid,
  server: z.string().min(1),
  tool: z.string().min(1),
  args_hash: Sha256,
  result_hash: Sha256.optional(),
  latency_ms: z.int().nonnegative(),
  cost: z.number().nonnegative(),
  risk_class: z.enum(["low", "medium", "high", "critical"]),
  approval_id: Uuid.optional(),
  verdict: z.string().min(1),
  trace_id: z.string().regex(/^[0-9a-f]{32}$/).optional(),
});

export const A2AMessage = z.strictObject({
  from_agent: Uuid,
  to_agent: Uuid,
  task_id: Uuid,
  intent: z.enum(["delegate", "result", "question", "veto", "handoff"]),
  body: z.record(z.string(), z.unknown()),
  budget_slice: z.number().nonnegative().optional(),
  traceparent: Traceparent.optional(),
});

export const TaskCommand = z.strictObject({
  task_id: Uuid,
  actor: z.string().min(1),
  command: z.enum(["create", "transition", "assign", "attach_evidence", "cancel", "pause", "resume", "run_eval"]),
  to_state: TaskState.optional(),
  payload: z.record(z.string(), z.unknown()).optional(),
});

export const ApprovalRequest = z.strictObject({
  task_id: Uuid,
  requested_by: z.string().min(1),
  server: z.string().min(1),
  tool: z.string().min(1),
  args_hash: Sha256,
  args_preview: z.record(z.string(), z.unknown()),
  risk_class: RiskHigh,
  expires_at: z.iso.datetime({ offset: true }),
});

const claimBase = { text: z.string().min(1), confidence: z.number().min(0).max(1).optional() };
export const Claim = z.union([
  z.strictObject({ ...claimBase, label: z.literal("verified"), source_ids: z.array(z.string().min(1)).min(1) }),
  z.strictObject({ ...claimBase, label: z.enum(["inferred", "missing"]), source_ids: z.array(z.string().min(1)).optional() }),
]);
export const PremiseBundle = z.strictObject({
  research_run_id: Uuid,
  claims: z.array(Claim).min(1),
  missing_data: z.array(z.string()),
});

const verificationBase = {
  task_id: Uuid,
  verifier_agent_id: Uuid,
  method: z.enum(["gitreins", "veripipe", "evalforge", "manual"]),
  tier: OracleTier,
  details: z.record(z.string(), z.unknown()).optional(),
};
/** An LLM verifier may veto but never confirm (INV-04). */
export const Verification = z.union([
  z.strictObject({ ...verificationBase, method_class: z.enum(["deterministic", "structural", "terminal_state", "reproduction"]),
                   verdict: z.enum(["PASS", "FAIL", "VETO", "DO_NOT_FILE"]) }),
  z.strictObject({ ...verificationBase, method_class: z.literal("llm"), verdict: z.enum(["FAIL", "VETO", "DO_NOT_FILE"]) }),
]);

export const Trajectory = z.strictObject({
  task_id: Uuid,
  verification_id: Uuid,
  steps: z.array(z.strictObject({ tool_call_id: Uuid })).min(1),
  reward: z.number(),
  cohort: z.enum(["canary", "holdout"]).optional(),
});

export const SkillRecall = z.strictObject({
  agent_id: Uuid,
  task_class: z.string().min(1),
  skills: z.array(z.strictObject({ skill_id: Uuid, version: z.int().positive(), instructions: z.string().min(1) })),
  cohort: z.enum(["canary", "holdout"]).optional(),
});

export const TimelineEvent = z.strictObject({
  thing_type: z.enum(["service", "repo", "customer", "job", "agent", "campaign", "website", "task", "project"]),
  thing_id: z.string().min(1),
  event_type: z.string().min(1),
  payload: z.record(z.string(), z.unknown()),
});

/** GET /health on every service. */
export const HealthResponse = z.strictObject({
  service: z.string().min(1),
  status: z.enum(["ok", "degraded"]),
  version: z.string().min(1),
  uptime_s: z.number().nonnegative().optional(),
  checks: z.record(z.string(), z.string()),
});

/** POST /v1/probe (api -> orchestrator -> MCP): end-to-end trace probe. */
export const ProbeRequest = z.strictObject({ task_id: Uuid, agent_id: Uuid, message: z.string().max(200) });
export const ProbeResponse = z.strictObject({ trace_id: z.string().regex(/^[0-9a-f]{32}$/), echo: z.string() });

/** Result of `revenueos audit verify`. */
export const AuditVerifyResult = z.union([
  z.strictObject({ status: z.literal("intact"), rows: z.int().nonnegative(), head: Sha256.nullable() }),
  z.strictObject({ status: z.literal("tampered"), rows: z.int().nonnegative(),
                   first_broken: z.strictObject({ id: Uuid, seq: z.int().positive(), actor: z.string(), action: z.string(),
                                                  target: z.string(), created_at: z.string() }) }),
]);

/** Egress decision recorded by the Envoy ext_authz service. */
export const EgressDecision = z.strictObject({
  agent_id: Uuid,
  task_id: Uuid.optional(),
  host: z.string().min(1),
  method: z.string().min(1),
  decision: z.enum(["allow", "deny"]),
  reason: z.string().min(1),
  injected_secrets: z.int().nonnegative(),
});

export const contracts = {
  ToolCallEnvelope, Receipt, A2AMessage, TaskCommand, ApprovalRequest, PremiseBundle, Verification, Trajectory,
  SkillRecall, TimelineEvent, HealthResponse, ProbeRequest, ProbeResponse, AuditVerifyResult, EgressDecision,
} as const;
export type ContractName = keyof typeof contracts;

export type ToolCallEnvelope = z.infer<typeof ToolCallEnvelope>;
export type Receipt = z.infer<typeof Receipt>;
export type A2AMessage = z.infer<typeof A2AMessage>;
export type TaskCommand = z.infer<typeof TaskCommand>;
export type ApprovalRequest = z.infer<typeof ApprovalRequest>;
export type PremiseBundle = z.infer<typeof PremiseBundle>;
export type Verification = z.infer<typeof Verification>;
export type Trajectory = z.infer<typeof Trajectory>;
export type SkillRecall = z.infer<typeof SkillRecall>;
export type TimelineEvent = z.infer<typeof TimelineEvent>;
export type HealthResponse = z.infer<typeof HealthResponse>;
export type ProbeRequest = z.infer<typeof ProbeRequest>;
export type ProbeResponse = z.infer<typeof ProbeResponse>;
export type AuditVerifyResult = z.infer<typeof AuditVerifyResult>;
export type EgressDecision = z.infer<typeof EgressDecision>;

/** Validate at a boundary; throws ZodError with every issue on rejection. */
export function validate<N extends ContractName>(name: N, payload: unknown): z.infer<(typeof contracts)[N]> {
  return contracts[name].parse(payload) as z.infer<(typeof contracts)[N]>;
}
