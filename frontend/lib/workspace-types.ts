import type { Repository } from "@/lib/types";
import type { ChatFeedbackRecord } from "@/components/feedback-controls";

export type Issue = {
  id: string;
  number: number;
  title: string;
  state: string;
  labels?: string[];
  body?: string | null;
  author?: string | null;
  assignees?: string[];
  created_at?: string | null;
  updated_at?: string | null;
};

export type PRFile = {
  id: string;
  filename: string;
  status: string;
  additions: number;
  deletions: number;
  patch?: string | null;
};

export type PullRequest = {
  id: string;
  number: number;
  title: string;
  state: string;
  body?: string | null;
  author?: string | null;
  base_branch?: string | null;
  head_branch?: string | null;
  merged_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  files?: PRFile[];
};

export type WorkflowRun = {
  id: string;
  name: string;
  status: string;
  conclusion?: string | null;
  html_url?: string | null;
  logs_text?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type WorkflowPlanClaim = {
  target_type: string;
  target_id?: string | null;
  allowed_sources?: string[];
  write_intent?: boolean;
  reason?: string;
};

export type WorkflowPlanTask = {
  id: string;
  agent_name: string;
  task_type: string;
  objective: string;
  dependencies?: string[];
  claim: WorkflowPlanClaim;
  critical?: boolean;
};

export type WorkflowPlan = {
  workflow_id: string;
  goal: string;
  trigger_message: string;
  acceptance_criteria?: string[];
  tasks: WorkflowPlanTask[];
  max_parallel_tasks?: number;
  requires_human_confirmation?: boolean;
  created_at?: string;
};

export type ChatResponse = {
  route: string;
  tool_calls: ToolCallTrace[];
  agent_events?: Array<Record<string, unknown>>;
  answer: string;
  citations: Array<Record<string, string>>;
  compression_stats?: Record<string, unknown>;
  progressive_compaction?: Record<string, unknown>;
  model_usage?: Array<Record<string, unknown>>;
  context_diagnostics?: Record<string, unknown>;
};

export type ChatPlanResponse = {
  route: string;
  conversation_id: string;
  answer: string;
  plan: WorkflowPlan;
  tool_calls: ToolCallTrace[];
  agent_events?: Array<Record<string, unknown>>;
};

export type ChatStreamFinal = ChatResponse & {
  run_id: string;
  message_id: string;
};

export type ChatStreamDelta = {
  content?: string;
};

export type ChatStreamToolUse = {
  id?: string;
  tool_name?: string;
  arguments?: Record<string, unknown>;
  skill_name?: string;
  skill_title?: string;
  skill_version?: string;
  skill_steps?: string[];
  skill_activation_mode?: string;
  skill_activation_reason?: string;
  skill_instruction_digest?: string;
};

export type ChatStreamToolResult = {
  tool_use_id?: string;
  tool_name?: string;
  status?: string;
  route?: string;
  content?: unknown;
  error?: string;
  skill_name?: string;
  skill_title?: string;
  skill_version?: string;
  skill_steps?: string[];
  skill_activation_mode?: string;
  skill_activation_reason?: string;
  skill_instruction_digest?: string;
};

export type PromptRecommendationsResponse = {
  agent: string;
  suggestions: string[];
};

export type DuplicateCandidate = {
  issue_id: string;
  title: string;
  score: number;
};

export type IssueEvidence = {
  source_type: string;
  title: string;
  snippet: string;
  reference?: string | null;
  confidence?: number | null;
};

export type IssueDrafts = {
  clarification_comment?: string | null;
  task_breakdown?: string | null;
};

export type IssueAnalysisResult = {
  summary: string;
  conclusion: "进入开发" | "等待澄清" | "关闭" | "拆分" | "合并到已有 Issue" | string;
  conclusion_reason: string;
  category: string;
  priority: "P0" | "P1" | "P2" | "P3" | string;
  complexity: "S" | "M" | "L" | "XL" | string;
  suggested_owner: string;
  owner_reason: string;
  duplicate_candidates?: DuplicateCandidate[];
  evidence?: IssueEvidence[];
  checklist?: string[];
  action_items?: string[];
  drafts?: IssueDrafts;
  confidence: number;
};

export type IssueAnalysisResponse = {
  analysis_id: string;
  result: IssueAnalysisResult;
};

export type PRAnalysisResult = {
  summary: string;
  plan?: string[];
  executed_steps?: string[];
  merge_recommendation: "建议合入" | "修改后合入" | "暂缓" | "拒绝" | string;
  recommendation_reason?: string;
  key_changes?: string[];
  risk_points?: string[];
  blocking_issues?: string[];
  review_checklist?: string[];
  test_suggestions?: string[];
  files_need_attention?: string[];
  review_comments?: string[];
  confidence: number;
};

export type PRAnalysisResponse = {
  analysis_id: string;
  result: PRAnalysisResult;
};

export type CIAnalysisResult = {
  failure_summary: string;
  failure_type: "test" | "build" | "lint" | "dependency" | "permission" | "environment" | "unknown" | string;
  plan?: string[];
  executed_steps?: string[];
  first_error?: string | null;
  root_cause?: string;
  possible_causes?: string[];
  fix_steps?: string[];
  debug_steps?: string[];
  related_files?: string[];
  is_merge_blocking: boolean;
  blocking_reason?: string;
  confidence: number;
};

export type CIAnalysisResponse = {
  analysis_id: string;
  result: CIAnalysisResult;
};

export type IssueAnalysisTraceItem = {
  id: string;
  kind: "step" | "tool" | "thinking" | "result" | "error" | string;
  title: string;
  content: string;
  status?: "running" | "done" | "error" | string;
};

export type ChatHistoryMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  route?: string | null;
  tool_calls?: ToolCallTrace[];
  agent_events?: Array<Record<string, unknown>>;
  compression_stats?: Record<string, unknown>;
  progressive_compaction?: Record<string, unknown>;
  model_usage?: Array<Record<string, unknown>>;
  context_diagnostics?: Record<string, unknown>;
  created_at?: string | null;
};

export type RepoConnectResult = {
  repo_id: string;
  full_name: string;
  provider: string;
  api_base_url?: string | null;
  clone_url?: string | null;
  local_path?: string | null;
  checkout_mode?: string;
  default_branch?: string | null;
  connected: boolean;
  demo_mode: boolean;
  message: string;
  sync_status?: string;
  synced?: Record<string, number>;
};

export type ProjectConversation = {
  id: string;
  repo_id: string;
  title: string;
  status: string;
  message_count: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ConversationDeleteResult = {
  deleted: string;
  active_conversation_id: string;
  conversations: ProjectConversation[];
};

export type ChatMessage = {
  id: string;
  messageId?: string;
  role: "user" | "assistant";
  content: string;
  route?: string;
  toolCalls?: ToolCallTrace[];
  traceItems?: ChatTraceItem[];
  traceCollapsed?: boolean;
  responsePending?: boolean;
  compressionStats?: Record<string, unknown>;
  progressiveCompaction?: Record<string, unknown>;
  modelUsage?: Array<Record<string, unknown>>;
  contextDiagnostics?: Record<string, unknown>;
  contextCollapsed?: boolean;
  workflowPlan?: WorkflowPlan;
  planSourceMessage?: string;
  planStatus?: "ready" | "executing" | "done" | "error";
  feedback?: ChatFeedbackRecord;
};

export type ToolCallTrace = {
  tool_name: string;
  status: string;
  error?: string;
  tool_use_id?: string;
  skill_name?: string;
  skill_title?: string;
  skill_version?: string;
  skill_steps?: string[];
  skill_activation_mode?: string;
  skill_activation_reason?: string;
  skill_instruction_digest?: string;
};

export type ChatTraceItem = {
  id: string;
  kind: "thinking" | "tool" | "error" | string;
  title: string;
  content: string;
  status?: "running" | "done" | "error" | string;
  toolUseId?: string;
  skillName?: string;
  skillTitle?: string;
  skillVersion?: string;
  skillSteps?: string[];
  skillActivationMode?: string;
  skillActivationReason?: string;
  skillInstructionDigest?: string;
  evidenceCount?: number;
};

export type SkillManifest = {
  name: string;
  title: string;
  version: string;
  description: string;
  category: string;
  entrypoint: string;
  tools: string[];
  input_modes: string[];
  triggers: string[];
  workflow_steps: string[];
  output_contract: string;
  safety_level: string;
};

export type SkillResponse = {
  manifest: SkillManifest;
  path: string;
  instructions?: string | null;
};

export type McpRuntime = {
  status: string;
  server_name: string;
  server_version: string;
  protocol_version: string;
  transport: string;
  tools: Array<{
    name: string;
    description: string;
    input_schema: {
      required?: string[];
      properties?: Record<string, unknown>;
    };
  }>;
};

export type WorkspaceSelection =
  | { type: "issue"; id: string }
  | { type: "pr"; id: string }
  | { type: "ci"; id: string };

export type WorkspaceItem = {
  id: string;
  title: string;
  meta: string;
  detail?: string | null;
  badges?: string[];
  selected: boolean;
  onClick: () => void;
};

export type TeamMember = {
  id: string;
  name: string;
  role: string;
  strengths: string;
  techStack: string;
};

export type TeamMemberDraft = Omit<TeamMember, "id">;

export type MemoryNote = {
  id: string;
  title: string;
  content: string;
};

export type MemoryNoteDraft = Omit<MemoryNote, "id">;

export type KnowledgeItem = {
  id: string;
  document_ids: string[];
  source_type: "memory_note" | "knowledge_file" | "team_member" | "weekly_report" | string;
  title: string;
  content_preview: string;
  metadata?: Record<string, unknown>;
  chunk_count: number;
  created_at?: string | null;
};

export type ProjectIndexStatus = "missing" | "stale" | "building" | "ready" | "failed";

export type ProjectIndexSummary = {
  projectName?: string;
  rootPath?: string;
  techStack?: string[];
  dirStructure?: string[];
  docsList?: Array<{ path: string; tier: string; source_type?: string }>;
  tierCoverage?: Record<string, number>;
  sourceTypeCoverage?: Record<string, number>;
  docsIndexed?: number;
  indexPolicy?: {
    mode?: "auto" | "allowlist";
    include?: string[];
    exclude?: string[];
    includeManifests?: boolean;
    configPath?: string | null;
  };
  excludedFiles?: number;
  excludedPaths?: string[];
  discoveryTruncated?: boolean;
};

export type ProjectIndexState = {
  repo_id: string;
  status: ProjectIndexStatus;
  fingerprint: string;
  docs_indexed: number;
  docs_total: number;
  error_message?: string | null;
  summary_json?: ProjectIndexSummary | null;
  snoozed_until?: string | null;
  last_scan_at?: string | null;
};

export type RecallEvent = {
  id: string;
  tool_name: string;
  query: string;
  scope: string;
  mode: string;
  status: string;
  result_count: number;
  results: Array<Record<string, unknown>>;
  citations: Array<Record<string, unknown>>;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
};

export type MemoryStatus = {
  repo_id: string;
  index: Record<string, unknown>;
  documents: Record<string, unknown>;
  evidence: Record<string, unknown>;
  recall: Record<string, unknown>;
  candidates: Record<string, unknown>;
  vector: Record<string, unknown>;
};

export type MemoryCandidate = {
  id: string;
  kind: string;
  title: string;
  content: string;
  status: string;
  source: string;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  reviewed_at?: string | null;
};

export type MemorySearchResult = {
  title: string;
  source_type: string;
  source_id: string;
  snippet: string;
  score?: number;
  metadata?: Record<string, unknown>;
  retrieval?: Record<string, unknown>;
};

export type KnowledgeGraphNode = {
  id: string;
  type: string;
  title: string;
  subtitle?: string;
  metadata?: Record<string, unknown>;
  highlighted?: boolean;
};

export type KnowledgeGraphEdge = {
  id: string;
  from_type: string;
  from_id: string;
  to_type: string;
  to_id: string;
  relation: string;
  confidence: number;
  source: string;
  metadata?: Record<string, unknown>;
};

export type KnowledgeGraphResponse = {
  repo_id: string;
  center_type?: string | null;
  center_id?: string | null;
  depth: number;
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
  stats: Record<string, unknown>;
};

export type AddProjectStatus = {
  type: "success" | "error";
  title: string;
  detail?: string;
};

export type AddProjectSource = "remote" | "local";

export type PromptSuggestionState = {
  suggestions: string[];
  exclude: string[];
};
