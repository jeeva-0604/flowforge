import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  Handle,
  Position,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  type NodeChange,
  type EdgeChange,
} from '@xyflow/react';
import {
  Activity, AlertCircle, ArrowDown, ArrowLeft, ArrowRight, Bot, Braces, Check,
  ChevronDown, ChevronLeft, ChevronRight, Clock, Code2, Copy, Database, Download,
  FileText, Filter, GitBranch, GitMerge, Globe, History, KeyRound, Layers3,
  LayoutDashboard, LoaderCircle, Moon, Play, Plus, Redo2, RefreshCw, Repeat,
  RotateCcw, Save, Search, Settings2, ShieldCheck, Sparkles, Split, Sun,
  Table, Trash2, Undo2, Upload, Webhook, Workflow, X, Zap,
} from 'lucide-react';

export type FlowNodeKind =
  | 'trigger'
  | 'webhook_trigger'
  | 'schedule_trigger'
  | 'set'
  | 'http_request'
  | 'if_condition'
  | 'switch'
  | 'merge'
  | 'filter'
  | 'loop'
  | 'wait'
  | 'code'
  | 'sql_query'
  | 'csv_json'
  | 'file_io'
  | 'skill'
  | 'ai_agent'
  | 'human_approval'
  | 'subworkflow'
  | 'error_handler'
  | 'output';

type FlowNodeData = {
  label: string;
  config: Record<string, unknown>;
  kind: FlowNodeKind;
  subtitle?: string;
  runStatus?: string;
  runDurationMs?: number;
  hasValidationError?: boolean;
  retry_policy?: { max_attempts: number; backoff_ms: number; backoff_multiplier: number };
  on_error?: 'fail' | 'continue_with_error' | 'fallback_value';
};

type WorkflowRecord = {
  id: string;
  name: string;
  description: string;
  tags: string[];
  folder: string;
  is_active: boolean;
  environment: 'dev' | 'staging' | 'prod';
  version: number;
  definition: {
    schema_version?: string;
    nodes: Array<{
      id: string;
      type: FlowNodeKind;
      config?: Record<string, unknown>;
      position?: { x: number; y: number };
      retry_policy?: { max_attempts: number; backoff_ms: number; backoff_multiplier: number };
      on_error?: 'fail' | 'continue_with_error' | 'fallback_value';
    }>;
    edges: Array<{ source: string; target: string; source_handle?: string | null; label?: string | null }>;
  };
  created_at: string;
  updated_at: string;
};

type NodeRunTrace = {
  node_id: string;
  node_type: string;
  status: string;
  attempts: number;
  started_at: string;
  finished_at: string;
  duration_ms: number;
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown> | null;
  error: string | null;
  branch_taken: string | null;
};

type ExecutionRecord = {
  id: string;
  workflow_id: string;
  workflow_version: number;
  trigger_type: string;
  status: string;
  input_data: Record<string, unknown>;
  result_data: Record<string, unknown> | null;
  node_runs: NodeRunTrace[];
  checkpoint_state?: Record<string, unknown> | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
};

type WorkflowVersionRecord = {
  id: string;
  workflow_id: string;
  version: number;
  name: string;
  environment: string;
  comment: string;
  definition: Record<string, unknown>;
  created_at: string;
};

type ValidationIssue = {
  severity: 'error' | 'warning';
  code: string;
  message: string;
  node_id?: string | null;
};

type CredentialRecord = {
  id: string;
  name: string;
  kind: string;
  description: string;
  field_names: string[];
  key_fingerprint: string;
  created_at: string;
};

type IntegrationSpec = {
  type: FlowNodeKind;
  version: string;
  display_name: string;
  category: string;
  description: string;
  documentation: string;
  color: string;
  is_trigger: boolean;
  output_handles: string[];
};

type SkillRecord = {
  id: string;
  version: string;
  name: string;
  category: string;
  description: string;
  permissions: string[];
  integrity_hash: string;
  example_input: Record<string, unknown>;
};

type TemplateRecord = {
  id: string;
  name: string;
  category: string;
  tags: string[];
  description: string;
  sample_payload: Record<string, unknown>;
};

type WebhookRecord = {
  id: string;
  workflow_id: string;
  path_slug: string;
  has_secret: boolean;
  is_active: boolean;
  created_at: string;
};

type ScheduleRecord = {
  id: string;
  workflow_id: string;
  cron_expr: string;
  interval_seconds: number;
  is_active: boolean;
  next_run_at: string;
};

type ApiTokenRecord = {
  id: string;
  name: string;
  token_prefix: string;
  role: string;
  scopes: string[];
  is_revoked: boolean;
  created_at: string;
};

type AuditLogRecord = {
  id: string;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string;
  details: Record<string, unknown>;
  created_at: string;
};

type ActiveView =
  | 'overview'
  | 'editor'
  | 'executions'
  | 'credentials'
  | 'integrations'
  | 'templates'
  | 'governance';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

const NODE_CATALOG: Array<{
  kind: FlowNodeKind;
  label: string;
  subtitle: string;
  category: 'Triggers' | 'Core Flow' | 'Data & Storage' | 'Code & Files' | 'AI & Governance';
  defaultConfig: Record<string, unknown>;
}> = [
  { kind: 'trigger', label: 'Manual Trigger', subtitle: 'Start a test run', category: 'Triggers', defaultConfig: {} },
  { kind: 'webhook_trigger', label: 'Webhook Trigger', subtitle: 'HTTP POST ingress', category: 'Triggers', defaultConfig: { path_slug: 'orders-hook', require_signature: true } },
  { kind: 'schedule_trigger', label: 'Schedule Trigger', subtitle: 'Recurring cron/interval', category: 'Triggers', defaultConfig: { cron_expr: '*/5 * * * *', interval_seconds: 300 } },
  { kind: 'set', label: 'Set Fields', subtitle: 'Transform & map JSON', category: 'Core Flow', defaultConfig: { values: { message: 'Hello {{ $input.user }}', priority: 1 }, keep_only_set: false } },
  { kind: 'if_condition', label: 'IF Condition', subtitle: 'True / False routing', category: 'Core Flow', defaultConfig: { field: 'priority', operator: 'gte', value: 1 } },
  { kind: 'switch', label: 'Switch Router', subtitle: 'Multi-case branch', category: 'Core Flow', defaultConfig: { field: 'tier', cases: ['gold', 'silver'] } },
  { kind: 'merge', label: 'Merge Branches', subtitle: 'Combine upstream paths', category: 'Core Flow', defaultConfig: { mode: 'shallow_merge' } },
  { kind: 'filter', label: 'Filter Items', subtitle: 'Filter array elements', category: 'Core Flow', defaultConfig: { list_field: 'items', item_field: 'active', operator: 'eq', value: true, output_field: 'filtered_items' } },
  { kind: 'loop', label: 'Loop / Batch', subtitle: 'Bounded array transform', category: 'Core Flow', defaultConfig: { list_field: 'items', template: { item: '{{ $item }}' }, max_iterations: 100, output_field: 'results' } },
  { kind: 'wait', label: 'Wait / Delay', subtitle: 'Bounded pause (ms)', category: 'Core Flow', defaultConfig: { delay_ms: 25 } },
  { kind: 'subworkflow', label: 'Sub-Workflow', subtitle: 'Invoke child workflow', category: 'Core Flow', defaultConfig: { subworkflow_id: '', output_field: 'subworkflow_result' } },
  { kind: 'error_handler', label: 'Error Fallback', subtitle: 'Recover upstream errors', category: 'Core Flow', defaultConfig: { fallback_values: { recovered: true } } },
  { kind: 'http_request', label: 'HTTP Request', subtitle: 'SSRF-guarded API call', category: 'Data & Storage', defaultConfig: { method: 'GET', url: 'mock://status.local/health', response_field: 'http', timeout_seconds: 10 } },
  { kind: 'sql_query', label: 'SQL Query', subtitle: 'Parameterized :param SQL', category: 'Data & Storage', defaultConfig: { query: 'SELECT :user AS operator, 1 AS ok', params: { user: '{{ $input.user }}' }, output_field: 'rows' } },
  { kind: 'csv_json', label: 'CSV / JSON', subtitle: 'Parse or format CSV', category: 'Data & Storage', defaultConfig: { mode: 'csv_to_json', source_field: 'csv_text', target_field: 'records', delimiter: ',' } },
  { kind: 'code', label: 'Code (Isolated)', subtitle: 'Sandboxed Python transform', category: 'Code & Files', defaultConfig: { code: "result = {**data, 'computed': True}", timeout_seconds: 3.0 } },
  { kind: 'file_io', label: 'Sandboxed File I/O', subtitle: 'Read/write permitted dir', category: 'Code & Files', defaultConfig: { operation: 'write_json', path: 'artifact.json', target_field: 'file_data' } },
  { kind: 'skill', label: 'FlowForge Skill', subtitle: 'Integrity-verified skill', category: 'AI & Governance', defaultConfig: { skill_id: 'csv-json-transformation-helper', skill_input: {}, output_field: 'skill_output' } },
  { kind: 'ai_agent', label: 'AI Transform', subtitle: 'Provider-independent AI', category: 'AI & Governance', defaultConfig: { provider: 'local', prompt: 'Summarize payload', required_keys: ['summary'], output_field: 'ai_result' } },
  { kind: 'human_approval', label: 'Human Approval', subtitle: 'Pause for operator review', category: 'AI & Governance', defaultConfig: { message: 'Approve production action?', auto_approve_in_test: false } },
  { kind: 'output', label: 'Output', subtitle: 'Return final result', category: 'Core Flow', defaultConfig: { select_fields: [] } },
];

const TRIGGER_KINDS = new Set<FlowNodeKind>(['trigger', 'webhook_trigger', 'schedule_trigger']);

const starterNodes: Node<FlowNodeData>[] = [
  { id: 'trigger_1', type: 'flowNode', position: { x: 80, y: 180 }, data: { kind: 'trigger', label: 'Manual Trigger', subtitle: 'Starts a test run', config: {} } },
  { id: 'http_1', type: 'flowNode', position: { x: 330, y: 180 }, data: { kind: 'http_request', label: 'Check Service', subtitle: 'SSRF-guarded API call', config: { method: 'GET', url: 'mock://status.local/health', response_field: 'http' }, retry_policy: { max_attempts: 2, backoff_ms: 100, backoff_multiplier: 2.0 } } },
  { id: 'if_1', type: 'flowNode', position: { x: 580, y: 180 }, data: { kind: 'if_condition', label: 'Is Healthy?', subtitle: 'http.ok == true', config: { field: 'http.ok', operator: 'eq', value: true } } },
  { id: 'set_1', type: 'flowNode', position: { x: 830, y: 120 }, data: { kind: 'set', label: 'Enrich Payload', subtitle: 'Transform data', config: { values: { message: 'Hello {{ $input.user }}', service_healthy: true } } } },
  { id: 'output_1', type: 'flowNode', position: { x: 1080, y: 180 }, data: { kind: 'output', label: 'Output', subtitle: 'Return the result', config: {} } },
];

const starterEdges: Edge[] = [
  { id: 'e-1', source: 'trigger_1', target: 'http_1', type: 'smoothstep' },
  { id: 'e-2', source: 'http_1', target: 'if_1', type: 'smoothstep' },
  { id: 'e-3', source: 'if_1', target: 'set_1', sourceHandle: 'true', label: 'true', type: 'smoothstep' },
  { id: 'e-4', source: 'set_1', target: 'output_1', type: 'smoothstep' },
];

function nodeIconFor(kind: FlowNodeKind) {
  switch (kind) {
    case 'trigger': return <Play size={16} />;
    case 'webhook_trigger': return <Webhook size={16} />;
    case 'schedule_trigger': return <Clock size={16} />;
    case 'set': return <Braces size={16} />;
    case 'http_request': return <Globe size={16} />;
    case 'if_condition': return <Split size={16} />;
    case 'switch': return <GitBranch size={16} />;
    case 'merge': return <GitMerge size={16} />;
    case 'filter': return <Filter size={16} />;
    case 'loop': return <Repeat size={16} />;
    case 'wait': return <Clock size={16} />;
    case 'code': return <Code2 size={16} />;
    case 'sql_query': return <Database size={16} />;
    case 'csv_json': return <Table size={16} />;
    case 'file_io': return <FileText size={16} />;
    case 'skill': return <Sparkles size={16} />;
    case 'ai_agent': return <Bot size={16} />;
    case 'human_approval': return <ShieldCheck size={16} />;
    case 'subworkflow': return <Layers3 size={16} />;
    case 'error_handler': return <AlertCircle size={16} />;
    case 'output': return <ArrowRight size={16} />;
  }
}

function CustomFlowNode({ id, data, selected }: NodeProps<Node<FlowNodeData>>) {
  const isTrigger = TRIGGER_KINDS.has(data.kind);
  const statusClass = data.runStatus ? ` status-${data.runStatus}` : '';
  const errClass = data.hasValidationError ? ' has-validation-error' : '';
  const className = `flow-node node-${data.kind}${selected ? ' selected' : ''}${statusClass}${errClass}`;

  return (
    <div className={className} data-testid={`node-${id}`} data-node-kind={data.kind}>
      {!isTrigger && <Handle type="target" position={Position.Left} className="node-handle" data-testid={`target-handle-${id}`} />}
      <div className="node-topline">
        <span className={`node-icon ${data.kind}`}>{nodeIconFor(data.kind)}</span>
        <span className="node-type">{data.kind.replace('_', ' ').toUpperCase()}</span>
        {data.runStatus && <span className={`node-run-badge ${data.runStatus}`}>{data.runStatus}</span>}
      </div>
      <div className="node-title">{data.label}</div>
      <div className="node-subtitle">{data.subtitle ?? 'Configure node'}</div>
      <div className="node-bottomline">
        <span className={`node-state-dot ${data.runStatus ?? ''}`} />
        <span>{data.runStatus ? `${data.runStatus}${data.runDurationMs !== undefined ? ` · ${data.runDurationMs.toFixed(1)}ms` : ''}` : 'Ready'}</span>
      </div>
      {data.kind === 'if_condition' ? (
        <>
          <Handle type="source" id="true" position={Position.Right} style={{ top: '36%' }} className="node-handle handle-true" data-testid={`source-handle-${id}-true`} />
          <Handle type="source" id="false" position={Position.Right} style={{ top: '72%' }} className="node-handle handle-false" data-testid={`source-handle-${id}-false`} />
        </>
      ) : (
        data.kind !== 'output' && <Handle type="source" position={Position.Right} className="node-handle" data-testid={`source-handle-${id}-default`} />
      )}
    </div>
  );
}

const nodeTypes = { flowNode: CustomFlowNode };

function stamp(value?: string | null) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function errorMessage(value: unknown) {
  return value instanceof Error ? value.message : 'Something went wrong. Check the backend logs.';
}

function Editor() {
  const { fitView } = useReactFlow();
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeView, setActiveView] = useState<ActiveView>('editor');
  const [environmentFilter, setEnvironmentFilter] = useState<'all' | 'dev' | 'staging' | 'prod'>('all');

  const [nodes, setNodes] = useState<Node<FlowNodeData>[]>(starterNodes);
  const [edges, setEdges] = useState<Edge[]>(starterEdges);
  const [historyPast, setHistoryPast] = useState<Array<{ nodes: Node<FlowNodeData>[]; edges: Edge[] }>>([]);
  const [historyFuture, setHistoryFuture] = useState<Array<{ nodes: Node<FlowNodeData>[]; edges: Edge[] }>>([]);
  const [isDirty, setIsDirty] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>('http_1');
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [workflowName, setWorkflowName] = useState('Resilient Service Health Pipeline');
  const [workflowEnv, setWorkflowEnv] = useState<'dev' | 'staging' | 'prod'>('dev');
  const [workflowVersion, setWorkflowVersion] = useState<number>(1);

  const [workflows, setWorkflows] = useState<WorkflowRecord[]>([]);
  const [executions, setExecutions] = useState<ExecutionRecord[]>([]);
  const [activeExecution, setActiveExecution] = useState<ExecutionRecord | null>(null);
  const [selectedTraceNodeId, setSelectedTraceNodeId] = useState<string | null>(null);
  const [versions, setVersions] = useState<WorkflowVersionRecord[]>([]);
  const [versionDiff, setVersionDiff] = useState<Record<string, unknown> | null>(null);
  const [validationIssues, setValidationIssues] = useState<ValidationIssue[]>([]);
  const [diagnosisResult, setDiagnosisResult] = useState<Record<string, unknown> | null>(null);

  const [credentials, setCredentials] = useState<CredentialRecord[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationSpec[]>([]);
  const [skills, setSkills] = useState<SkillRecord[]>([]);
  const [templates, setTemplates] = useState<TemplateRecord[]>([]);
  const [webhooks, setWebhooks] = useState<WebhookRecord[]>([]);
  const [schedules, setSchedules] = useState<ScheduleRecord[]>([]);
  const [tokens, setTokens] = useState<ApiTokenRecord[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([]);
  const [diagnostics, setDiagnostics] = useState<Record<string, any> | null>(null);

  const [testInput, setTestInput] = useState('{
  "user": "Jeeva",
  "service": "payments-api"
}');
  const [executionMode, setExecutionMode] = useState<'sync' | 'queued'>('sync');
  const [drawerTab, setDrawerTab] = useState<'settings' | 'runs' | 'validation' | 'versions'>('settings');
  const [paletteCategory, setPaletteCategory] = useState<string>('All');
  const [paletteSearch, setPaletteSearch] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error' | 'info'; message: string } | null>({
    kind: 'info',
    message: 'FlowForge v0.4.0 ready. Save, validate, or run the workflow.',
  });
  const [apiOnline, setApiOnline] = useState(false);

  // Forms for auxiliary views
  const [newCredName, setNewCredName] = useState('');
  const [newCredKind, setNewCredKind] = useState('http_bearer');
  const [newCredSecret, setNewCredSecret] = useState('');
  const [aiPrompt, setAiPrompt] = useState('Trigger a webhook, call an HTTP API endpoint, check if condition is true, and output');
  const [skillOutput, setSkillOutput] = useState<Record<string, unknown> | null>(null);
  const [newWebhookSlug, setNewWebhookSlug] = useState('orders-incoming');
  const [newWebhookSecret, setNewWebhookSecret] = useState('');
  const [newScheduleCron, setNewScheduleCron] = useState('*/5 * * * *');
  const [newTokenName, setNewTokenName] = useState('CI Automation Token');
  const [newTokenRole, setNewTokenRole] = useState<'viewer' | 'editor' | 'admin'>('editor');
  const [newlyCreatedTokenValue, setNewlyCreatedTokenValue] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const pushHistory = useCallback(() => {
    setHistoryPast((prev) => [...prev.slice(-24), { nodes, edges }]);
    setHistoryFuture([]);
    setIsDirty(true);
  }, [nodes, edges]);

  const undo = () => {
    if (historyPast.length === 0) return;
    const previous = historyPast[historyPast.length - 1];
    setHistoryPast((prev) => prev.slice(0, -1));
    setHistoryFuture((prev) => [{ nodes, edges }, ...prev]);
    setNodes(previous.nodes);
    setEdges(previous.edges);
    setIsDirty(true);
  };

  const redo = () => {
    if (historyFuture.length === 0) return;
    const next = historyFuture[0];
    setHistoryFuture((prev) => prev.slice(1));
    setHistoryPast((prev) => [...prev, { nodes, edges }]);
    setNodes(next.nodes);
    setEdges(next.edges);
    setIsDirty(true);
  };

  const selectedNode = useMemo(() => nodes.find((node) => node.id === selectedId) ?? null, [nodes, selectedId]);
  const selectedData = selectedNode?.data;

  const nodeChanges = useCallback((changes: NodeChange[]) => {
    setNodes((current) => applyNodeChanges(changes, current) as Node<FlowNodeData>[]);
  }, []);
  const edgeChanges = useCallback((changes: EdgeChange[]) => {
    setEdges((current) => applyEdgeChanges(changes, current));
    setIsDirty(true);
  }, []);
  const onConnect = useCallback((connection: Connection) => {
    pushHistory();
    const label = connection.sourceHandle && connection.sourceHandle !== 'default' ? connection.sourceHandle : undefined;
    setEdges((current) => addEdge({ ...connection, label, type: 'smoothstep', animated: false }, current));
  }, [pushHistory]);

  const definitionFromCanvas = useCallback(() => ({
    schema_version: '1.0',
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.data.kind,
      config: { ...node.data.config, label: node.data.label, subtitle: node.data.subtitle },
      position: node.position,
      retry_policy: node.data.retry_policy,
      on_error: node.data.on_error ?? 'fail',
    })),
    edges: edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      source_handle: edge.sourceHandle ?? null,
      label: typeof edge.label === 'string' ? edge.label : null,
    })),
  }), [nodes, edges]);

  const loadWorkspaceData = useCallback(async () => {
    try {
      const [wfRes, exRes, diagRes, credRes, intRes, skRes, tplRes, whRes, schRes, tokRes, audRes] = await Promise.all([
        fetch(`${API_BASE}/api/workflows`),
        fetch(`${API_BASE}/api/executions?limit=25`),
        fetch(`${API_BASE}/api/system/diagnostics`),
        fetch(`${API_BASE}/api/credentials`),
        fetch(`${API_BASE}/api/integrations`),
        fetch(`${API_BASE}/api/skills`),
        fetch(`${API_BASE}/api/templates`),
        fetch(`${API_BASE}/api/webhooks`),
        fetch(`${API_BASE}/api/schedules`),
        fetch(`${API_BASE}/api/auth/tokens`),
        fetch(`${API_BASE}/api/audit-logs?limit=30`),
      ]);
      if (wfRes.ok) {
        setWorkflows(await wfRes.json());
        setApiOnline(true);
      }
      if (exRes.ok) setExecutions(await exRes.json());
      if (diagRes.ok) setDiagnostics(await diagRes.json());
      if (credRes.ok) setCredentials(await credRes.json());
      if (intRes.ok) setIntegrations(await intRes.json());
      if (skRes.ok) setSkills(await skRes.json());
      if (tplRes.ok) setTemplates(await tplRes.json());
      if (whRes.ok) setWebhooks(await whRes.json());
      if (schRes.ok) setSchedules(await schRes.json());
      if (tokRes.ok) setTokens(await tokRes.json());
      if (audRes.ok) setAuditLogs(await audRes.json());
    } catch {
      setApiOnline(false);
    }
  }, []);

  const loadVersions = useCallback(async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/workflows/${id}/versions`);
      if (res.ok) setVersions(await res.json());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { void loadWorkspaceData(); }, [loadWorkspaceData]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 5500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const validateCanvasGraph = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/workflows/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(definitionFromCanvas()),
      });
      const report = await response.json();
      if (response.ok && Array.isArray(report.issues)) {
        setValidationIssues(report.issues);
        const badNodeIds = new Set(report.issues.map((i: ValidationIssue) => i.node_id).filter(Boolean));
        setNodes((curr) => curr.map((n) => ({ ...n, data: { ...n.data, hasValidationError: badNodeIds.has(n.id) } })));
        setDrawerTab('validation');
        setNotice({
          kind: report.valid ? 'ok' : 'error',
          message: report.valid ? `Graph is valid (${report.topological_order.length} ordered steps).` : `Found ${report.issues.length} validation issue(s).`,
        });
      } else {
        setValidationIssues([{ severity: 'error', code: 'SCHEMA_ERROR', message: JSON.stringify(report.detail ?? report) }]);
        setDrawerTab('validation');
      }
    } catch (error) {
      setNotice({ kind: 'error', message: errorMessage(error) });
    }
  };

  const autoLayoutCanvas = () => {
    pushHistory();
    const incomingCount: Record<string, number> = {};
    const adj: Record<string, string[]> = {};
    nodes.forEach((n) => { incomingCount[n.id] = 0; adj[n.id] = []; });
    edges.forEach((e) => {
      if (adj[e.source] && incomingCount[e.target] !== undefined) {
        adj[e.source].push(e.target);
        incomingCount[e.target] += 1;
      }
    });
    const depthMap: Record<string, number> = {};
    const queue = Object.keys(incomingCount).filter((id) => incomingCount[id] === 0);
    queue.forEach((id) => { depthMap[id] = 0; });
    while (queue.length > 0) {
      const curr = queue.shift()!;
      for (const nxt of adj[curr] ?? []) {
        depthMap[nxt] = Math.max(depthMap[nxt] ?? 0, (depthMap[curr] ?? 0) + 1);
        incomingCount[nxt] -= 1;
        if (incomingCount[nxt] <= 0) queue.push(nxt);
      }
    }
    const columns: Record<number, string[]> = {};
    nodes.forEach((n) => {
      const col = depthMap[n.id] ?? 0;
      columns[col] = columns[col] ?? [];
      columns[col].push(n.id);
    });
    setNodes((curr) =>
      curr.map((n) => {
        const col = depthMap[n.id] ?? 0;
        const rowIdx = columns[col].indexOf(n.id);
        return { ...n, position: { x: 80 + col * 260, y: 120 + rowIdx * 160 } };
      })
    );
    setTimeout(() => fitView({ padding: 0.22 }), 60);
    setNotice({ kind: 'ok', message: 'Applied topological DAG auto-layout.' });
  };

  const updateSelectedNode = (update: (data: FlowNodeData) => FlowNodeData) => {
    if (!selectedId) return;
    setIsDirty(true);
    setNodes((current) => current.map((node) => (node.id === selectedId ? { ...node, data: update(node.data) } : node)));
  };

  const addNode = (kind: FlowNodeKind) => {
    if (TRIGGER_KINDS.has(kind) && nodes.some((node) => TRIGGER_KINDS.has(node.data.kind))) {
      setNotice({ kind: 'error', message: 'A workflow must contain exactly one trigger node.' });
      return;
    }
    pushHistory();
    const spec = NODE_CATALOG.find((item) => item.kind === kind) ?? NODE_CATALOG[3];
    const id = `${kind}_${Math.random().toString(36).slice(2, 7)}`;
    const newNode: Node<FlowNodeData> = {
      id,
      type: 'flowNode',
      position: { x: 200 + Math.round(Math.random() * 180), y: 120 + Math.round(Math.random() * 220) },
      data: {
        kind,
        label: spec.label,
        subtitle: spec.subtitle,
        config: structuredClone(spec.defaultConfig),
      },
    };
    setNodes((current) => [...current, newNode]);
    setSelectedId(id);
    setDrawerTab('settings');
    setActiveView('editor');
  };

  const duplicateSelectedNode = () => {
    if (!selectedNode || TRIGGER_KINDS.has(selectedNode.data.kind)) {
      setNotice({ kind: 'error', message: 'Select a non-trigger node to duplicate.' });
      return;
    }
    pushHistory();
    const id = `${selectedNode.data.kind}_${Math.random().toString(36).slice(2, 7)}`;
    const copy: Node<FlowNodeData> = {
      id,
      type: 'flowNode',
      position: { x: selectedNode.position.x + 40, y: selectedNode.position.y + 60 },
      data: structuredClone(selectedNode.data),
    };
    copy.data.label = `${copy.data.label} (Copy)`;
    setNodes((curr) => [...curr, copy]);
    setSelectedId(id);
  };

  const applyDefinitionToCanvas = (
    def: WorkflowRecord['definition'],
    meta?: { id: string | null; name: string; env?: 'dev' | 'staging' | 'prod'; version?: number }
  ) => {
    const restored = (def.nodes ?? []).map((item, index) => {
      const cat = NODE_CATALOG.find((c) => c.kind === item.type);
      return {
        id: item.id,
        type: 'flowNode',
        position: item.position ?? { x: 90 + index * 250, y: 180 },
        data: {
          kind: item.type,
          label: String(item.config?.label ?? cat?.label ?? item.type),
          subtitle: String(item.config?.subtitle ?? cat?.subtitle ?? 'Configure step'),
          config: item.config ?? {},
          retry_policy: item.retry_policy,
          on_error: item.on_error ?? 'fail',
        },
      };
    }) as Node<FlowNodeData>[];
    const restoredEdges: Edge[] = (def.edges ?? []).map((e, idx) => ({
      id: `edge-${idx}-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      sourceHandle: e.source_handle ?? undefined,
      label: e.label ?? e.source_handle ?? undefined,
      type: 'smoothstep',
    }));
    setNodes(restored);
    setEdges(restoredEdges);
    if (meta) {
      setWorkflowId(meta.id);
      setWorkflowName(meta.name);
      if (meta.env) setWorkflowEnv(meta.env);
      if (meta.version) setWorkflowVersion(meta.version);
    }
    setSelectedId(restored[0]?.id ?? null);
    setIsDirty(false);
    setTimeout(() => fitView({ padding: 0.22 }), 80);
  };

  const saveWorkflow = async () => {
    setBusy('save');
    try {
      const payload = {
        name: workflowName.trim() || 'Untitled workflow',
        environment: workflowEnv,
        comment: workflowId ? `Saved revision from editor` : 'Initial workflow creation',
        definition: definitionFromCanvas(),
      };
      const url = workflowId ? `${API_BASE}/api/workflows/${workflowId}` : `${API_BASE}/api/workflows`;
      const response = await fetch(url, {
        method: workflowId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail ?? result));
      setWorkflowId(result.id);
      setWorkflowName(result.name);
      setWorkflowVersion(result.version ?? 1);
      setIsDirty(false);
      setNotice({ kind: 'ok', message: `Saved “${result.name}” (v${result.version ?? 1}).` });
      await loadWorkspaceData();
      await loadVersions(result.id);
    } catch (error) {
      setNotice({ kind: 'error', message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  };

  const openWorkflow = async (id: string) => {
    setBusy('load');
    try {
      const response = await fetch(`${API_BASE}/api/workflows/${id}`);
      const result: WorkflowRecord = await response.json();
      if (!response.ok) throw new Error('Could not load workflow.');
      applyDefinitionToCanvas(result.definition, {
        id: result.id,
        name: result.name,
        env: result.environment ?? 'dev',
        version: result.version ?? 1,
      });
      setActiveExecution(null);
      setActiveView('editor');
      await loadVersions(result.id);
      setNotice({ kind: 'ok', message: `Loaded “${result.name}” (v${result.version}).` });
    } catch (error) {
      setNotice({ kind: 'error', message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  };

  const decorateCanvasWithExecution = (exec: ExecutionRecord) => {
    const traceMap = new Map<string, NodeRunTrace>();
    (exec.node_runs ?? []).forEach((nr) => traceMap.set(nr.node_id, nr));
    setNodes((curr) =>
      curr.map((n) => {
        const trace = traceMap.get(n.id);
        return {
          ...n,
          data: {
            ...n.data,
            runStatus: trace?.status,
            runDurationMs: trace?.duration_ms,
          },
        };
      })
    );
  };

  const executeWorkflow = async () => {
    if (!workflowId) {
      setNotice({ kind: 'info', message: 'Save the workflow before executing it.' });
      return;
    }
    setBusy('run');
    setDiagnosisResult(null);
    try {
      const input = JSON.parse(testInput || '{}');
      if (input === null || Array.isArray(input) || typeof input !== 'object') {
        throw new Error('Test input must be a JSON object.');
      }
      const response = await fetch(`${API_BASE}/api/workflows/${workflowId}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input, mode: executionMode }),
      });
      const result: ExecutionRecord = await response.json();
      if (!response.ok) throw new Error(typeof (result as any).detail === 'string' ? (result as any).detail : 'Execution failed.');
      setActiveExecution(result);
      setSelectedTraceNodeId(result.node_runs?.[0]?.node_id ?? null);
      decorateCanvasWithExecution(result);
      setDrawerTab('runs');
      await loadWorkspaceData();
      setNotice({
        kind: result.status === 'succeeded' ? 'ok' : result.status === 'waiting_approval' ? 'info' : 'error',
        message:
          result.status === 'succeeded'
            ? 'Workflow execution succeeded.'
            : result.status === 'waiting_approval'
            ? 'Execution paused at Human Approval checkpoint.'
            : result.error ?? 'Workflow execution failed.',
      });
    } catch (error) {
      setNotice({ kind: 'error', message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  };

  const approveOrRejectExecution = async (approved: boolean) => {
    if (!activeExecution) return;
    setBusy('approve');
    try {
      const res = await fetch(`${API_BASE}/api/executions/${activeExecution.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved, comment: approved ? 'Approved in UI' : 'Rejected in UI', reviewer: 'local-operator' }),
      });
      const updated: ExecutionRecord = await res.json();
      if (!res.ok) throw new Error('Approval action failed');
      setActiveExecution(updated);
      decorateCanvasWithExecution(updated);
      await loadWorkspaceData();
      setNotice({ kind: updated.status === 'succeeded' ? 'ok' : 'info', message: `Execution ${updated.status}.` });
    } catch (error) {
      setNotice({ kind: 'error', message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  };

  const replayFromNode = async (fromNodeId?: string) => {
    if (!activeExecution) return;
    setBusy('replay');
    try {
      const res = await fetch(`${API_BASE}/api/executions/${activeExecution.id}/replay`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_node_id: fromNodeId ?? null }),
      });
      const replayed: ExecutionRecord = await res.json();
      if (!res.ok) throw new Error('Replay failed');
      setActiveExecution(replayed);
      decorateCanvasWithExecution(replayed);
      await loadWorkspaceData();
      setNotice({ kind: 'ok', message: `Replayed execution (${replayed.status}).` });
    } catch (error) {
      setNotice({ kind: 'error', message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  };

  const diagnoseExecution = async () => {
    if (!activeExecution) return;
    const res = await fetch(`${API_BASE}/api/executions/${activeExecution.id}/diagnose`);
    if (res.ok) {
      setDiagnosisResult(await res.json());
    }
  };

  const exportWorkflowJson = () => {
    const blob = new Blob(
      [JSON.stringify({ format: 'flowforge-workflow-export', format_version: '1.0', workflow: { name: workflowName, environment: workflowEnv, definition: definitionFromCanvas() } }, null, 2)],
      { type: 'application/json' }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${workflowName.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'workflow'}.flowforge.json`;
    a.click();
    URL.revokeObjectURL(url);
    setNotice({ kind: 'ok', message: 'Exported workflow JSON.' });
  };

  const importWorkflowJson = (rawText: string) => {
    try {
      const parsed = JSON.parse(rawText);
      const wfBlock = parsed.workflow ?? parsed;
      if (!wfBlock.definition) throw new Error('Missing workflow.definition');
      applyDefinitionToCanvas(wfBlock.definition, {
        id: null,
        name: wfBlock.name ?? 'Imported Workflow',
        env: wfBlock.environment ?? 'dev',
        version: 1,
      });
      setIsDirty(true);
      setNotice({ kind: 'ok', message: 'Imported workflow onto canvas. Click Save to persist.' });
    } catch (error) {
      setNotice({ kind: 'error', message: errorMessage(error) });
    }
  };

  const promoteCurrentWorkflow = async (targetEnv: 'dev' | 'staging' | 'prod') => {
    if (!workflowId) return;
    const res = await fetch(`${API_BASE}/api/workflows/${workflowId}/promote`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_environment: targetEnv, comment: `Promoted to ${targetEnv}` }),
    });
    if (res.ok) {
      const updated: WorkflowRecord = await res.json();
      setWorkflowEnv(updated.environment);
      setWorkflowVersion(updated.version);
      await loadWorkspaceData();
      await loadVersions(workflowId);
      setNotice({ kind: 'ok', message: `Promoted workflow to ${targetEnv.toUpperCase()} (v${updated.version}).` });
    }
  };

  const filteredPalette = NODE_CATALOG.filter((item) => {
    const matchCat = paletteCategory === 'All' || item.category === paletteCategory;
    const matchSearch =
      !paletteSearch ||
      item.label.toLowerCase().includes(paletteSearch.toLowerCase()) ||
      item.kind.toLowerCase().includes(paletteSearch.toLowerCase());
    return matchCat && matchSearch;
  });

  const matchingWorkflows = workflows.filter((wf) => {
    const matchName = wf.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchEnv = environmentFilter === 'all' || wf.environment === environmentFilter;
    return matchName && matchEnv;
  });

  const selectedTrace = (activeExecution?.node_runs ?? []).find((nr) => nr.node_id === selectedTraceNodeId) ?? activeExecution?.node_runs?.[0] ?? null;

  return (
    <div className="app-shell">
      <aside className="rail">
        <div className="brand-mark" title="FlowForge Community v0.4.0"><Workflow size={21} strokeWidth={2.2} /></div>
        <div className="rail-divider" />
        <button className={`rail-button ${activeView === 'overview' ? 'active' : ''}`} title="Overview Dashboard" onClick={() => setActiveView('overview')}><LayoutDashboard size={18} /></button>
        <button className={`rail-button ${activeView === 'editor' ? 'active' : ''}`} title="Workflow Editor" onClick={() => setActiveView('editor')}><Workflow size={18} /></button>
        <button className={`rail-button ${activeView === 'executions' ? 'active' : ''}`} title="Executions & Queue" onClick={() => setActiveView('executions')}><History size={18} /></button>
        <button className={`rail-button ${activeView === 'credentials' ? 'active' : ''}`} title="Credentials Vault" onClick={() => setActiveView('credentials')}><KeyRound size={18} /></button>
        <button className={`rail-button ${activeView === 'integrations' ? 'active' : ''}`} title="Integrations & Skills" onClick={() => setActiveView('integrations')}><Layers3 size={18} /></button>
        <button className={`rail-button ${activeView === 'templates' ? 'active' : ''}`} title="Templates & AI Studio" onClick={() => setActiveView('templates')}><Sparkles size={18} /></button>
        <div className="rail-spacer" />
        <button className="rail-button" title="Toggle Light/Dark Theme" onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}>
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <button className={`rail-button ${activeView === 'governance' ? 'active' : ''}`} title="Webhooks, Schedules & Security Audit" onClick={() => setActiveView('governance')}><Settings2 size={18} /></button>
        <button className="rail-button" title={sidebarCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'} onClick={() => setSidebarCollapsed((c) => !c)}>
          {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </aside>

      {!sidebarCollapsed && (
        <aside className="workspace-sidebar">
          <div className="workspace-head">
            <div className="workspace-symbol"><Zap size={15} fill="currentColor" /></div>
            <div><strong>FlowForge</strong><span>Community Platform v0.3</span></div>
            <select
              className="env-switcher"
              aria-label="Environment filter"
              value={environmentFilter}
              onChange={(e) => setEnvironmentFilter(e.target.value as any)}
            >
              <option value="all">All envs</option>
              <option value="dev">DEV</option>
              <option value="staging">STAGING</option>
              <option value="prod">PROD</option>
            </select>
          </div>

          <div className="workspace-nav">
            <span className="nav-heading">PLATFORM</span>
            <button className={`nav-item ${activeView === 'overview' ? 'selected' : ''}`} onClick={() => setActiveView('overview')}><LayoutDashboard size={15} /> Overview</button>
            <button className={`nav-item ${activeView === 'editor' ? 'selected' : ''}`} onClick={() => setActiveView('editor')}><Workflow size={15} /> Workflow Editor <span className="nav-count">{workflows.length}</span></button>
            <button className={`nav-item ${activeView === 'executions' ? 'selected' : ''}`} onClick={() => setActiveView('executions')}><History size={15} /> Executions & Queue <span className="nav-count">{executions.length}</span></button>
            <button className={`nav-item ${activeView === 'credentials' ? 'selected' : ''}`} onClick={() => setActiveView('credentials')}><ShieldCheck size={15} /> Credentials Vault <span className="nav-count">{credentials.length}</span></button>
            <button className={`nav-item ${activeView === 'integrations' ? 'selected' : ''}`} onClick={() => setActiveView('integrations')}><Layers3 size={15} /> SDK & Skills <span className="nav-count">{integrations.length + skills.length}</span></button>
            <button className={`nav-item ${activeView === 'templates' ? 'selected' : ''}`} onClick={() => setActiveView('templates')}><Sparkles size={15} /> Templates & AI <span className="nav-count">{templates.length}</span></button>
            <button className={`nav-item ${activeView === 'governance' ? 'selected' : ''}`} onClick={() => setActiveView('governance')}><Settings2 size={15} /> Triggers & Security</button>
          </div>

          <div className="saved-section">
            <div className="saved-heading">
              <span className="nav-heading">YOUR WORKFLOWS</span>
              <button title="New workflow" onClick={() => { applyDefinitionToCanvas({ nodes: starterNodes.map((n) => ({ id: n.id, type: n.data.kind, config: n.data.config, position: n.position })), edges: starterEdges.map((e) => ({ source: e.source, target: e.target, source_handle: e.sourceHandle })) }, { id: null, name: 'Untitled workflow', env: 'dev', version: 1 }); setActiveView('editor'); }}>
                <Plus size={14} />
              </button>
            </div>
            <label className="search-box">
              <Search size={13} />
              <input value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder="Search workflows..." />
            </label>
            <div className="workflow-list">
              {matchingWorkflows.map((wf) => (
                <button key={wf.id} className={`workflow-list-item ${wf.id === workflowId ? 'current' : ''}`} onClick={() => void openWorkflow(wf.id)}>
                  <span className="workflow-list-icon"><Workflow size={14} /></span>
                  <span className="workflow-list-text">
                    <strong>{wf.name}</strong>
                    <small>{(wf.environment ?? 'dev').toUpperCase()} · v{wf.version ?? 1} · {stamp(wf.updated_at)}</small>
                  </span>
                </button>
              ))}
              {matchingWorkflows.length === 0 && (
                <div className="empty-list">{apiOnline ? 'No matching workflows' : 'Start FastAPI backend on :8000'}</div>
              )}
            </div>
          </div>

          <div className="sidebar-footer">
            <div className={`api-indicator ${apiOnline ? 'online' : ''}`} />
            <div>
              <strong>{apiOnline ? 'API Connected' : 'API Offline'}</strong>
              <span>{apiOnline ? `v0.4.0 · ${diagnostics?.security?.ssrf_private_ip_blocked ? 'SSRF Guard Active' : 'Local Mode'}` : 'Run uvicorn on :8000'}</span>
            </div>
          </div>
        </aside>
      )}

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>FlowForge</span>
            <ArrowRight size={13} />
            <span className="crumb-current">{activeView.toUpperCase()}</span>
            <span className="draft-pill">{workflowId ? `SAVED · v${workflowVersion}` : 'DRAFT'}</span>
            <span className={`env-badge env-${workflowEnv}`}>{workflowEnv.toUpperCase()}</span>
            {isDirty && <span className="unsaved-pill">UNSAVED EDITS</span>}
          </div>
          <div className="topbar-actions">
            <button className="btn btn-quiet" onClick={() => void loadWorkspaceData()} title="Refresh workspace state"><RefreshCw size={14} /> Refresh</button>
            <button className="btn btn-quiet" onClick={() => void validateCanvasGraph()} title="Validate workflow graph"><ShieldCheck size={14} /> Validate</button>
            <button className="btn btn-quiet" onClick={exportWorkflowJson} title="Export workflow JSON"><Download size={14} /> Export</button>
            <button className="btn btn-secondary" onClick={() => void saveWorkflow()} disabled={busy !== null}>
              <Save size={14} /> {busy === 'save' ? 'Saving…' : 'Save'}
            </button>
            <button className="btn btn-primary" onClick={() => void executeWorkflow()} disabled={busy !== null || !workflowId}>
              {busy === 'run' ? <LoaderCircle size={15} className="spinning" /> : <Play size={14} fill="currentColor" />}
              {busy === 'run' ? 'Running…' : 'Execute'}
            </button>
          </div>
        </header>

        {activeView === 'editor' && (
          <>
            <div className="editor-heading">
              <div>
                <div className="title-row">
                  <input
                    className="workflow-title-input"
                    value={workflowName}
                    onChange={(e) => { setWorkflowName(e.target.value); setIsDirty(true); }}
                    aria-label="Workflow name"
                  />
                  {workflowId && (
                    <div className="promote-group">
                      {(['dev', 'staging', 'prod'] as const).map((env) => (
                        <button
                          key={env}
                          className={`btn btn-quiet small ${workflowEnv === env ? 'active-env-btn' : ''}`}
                          onClick={() => void promoteCurrentWorkflow(env)}
                        >
                          {env.toUpperCase()}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div className="meta-line">
                  <span className="meta-dot" />
                  {workflowId ? `Workflow ID: ${workflowId.slice(0, 8)} · Revision v${workflowVersion}` : 'Unsaved draft'}
                  <span className="meta-separator">·</span> {nodes.length} nodes
                  <span className="meta-separator">·</span> {edges.length} connections
                </div>
              </div>
              <div className="view-actions">
                <button className="btn btn-quiet small" onClick={undo} disabled={historyPast.length === 0} title="Undo"><Undo2 size={13} /> Undo</button>
                <button className="btn btn-quiet small" onClick={redo} disabled={historyFuture.length === 0} title="Redo"><Redo2 size={13} /> Redo</button>
                <button className="btn btn-quiet small" onClick={autoLayoutCanvas} title="Topological Auto-Layout"><GitBranch size={13} /> Auto-Layout</button>
                <button className="btn btn-quiet small" onClick={duplicateSelectedNode} title="Duplicate selected node"><Copy size={13} /> Duplicate</button>
              </div>
            </div>

            <div className="editor-stage">
              <div className="canvas-toolbar">
                <div className="canvas-label">
                  <span className="canvas-live-dot" /> VISUAL DAG CANVAS
                  <span className="label-divider" />
                  <span className="subtle-label">Connect handles · True (top-right) / False (bottom-right) on IF nodes</span>
                </div>
                <div className="canvas-tool-actions">
                  <button title="Fit workflow to view" onClick={() => fitView({ padding: 0.22 })}><ArrowDown size={14} /></button>
                  <button title="Auto-layout graph" onClick={autoLayoutCanvas}><GitBranch size={14} /></button>
                  <button title="Validate graph" onClick={() => void validateCanvasGraph()}><ShieldCheck size={14} /></button>
                </div>
              </div>

              <div className="node-palette">
                <div className="palette-title">NODE LIBRARY ({filteredPalette.length})</div>
                <input
                  className="palette-search"
                  placeholder="Filter nodes..."
                  value={paletteSearch}
                  onChange={(e) => setPaletteSearch(e.target.value)}
                />
                <div className="palette-cats">
                  {['All', 'Triggers', 'Core Flow', 'Data & Storage', 'Code & Files', 'AI & Governance'].map((cat) => (
                    <button
                      key={cat}
                      className={`cat-chip ${paletteCategory === cat ? 'active' : ''}`}
                      onClick={() => setPaletteCategory(cat)}
                    >
                      {cat === 'All' ? 'All' : cat.split(' ')[0]}
                    </button>
                  ))}
                </div>
                <div className="palette-scroll">
                  {filteredPalette.map((item) => (
                    <button key={item.kind} data-testid={`palette-node-${item.kind}`} onClick={() => addNode(item.kind)}>
                      <span className={`palette-icon ${item.kind}`}>{nodeIconFor(item.kind)}</span>
                      <span>
                        <strong>{item.label}</strong>
                        <small>{item.subtitle}</small>
                      </span>
                      <Plus size={13} className="palette-plus" />
                    </button>
                  ))}
                </div>
              </div>

              <div className="flow-canvas" data-testid="workflow-canvas">
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  nodeTypes={nodeTypes}
                  onNodesChange={nodeChanges}
                  onEdgesChange={edgeChanges}
                  onConnect={onConnect}
                  onNodeClick={(_, node) => { setSelectedId(node.id); setDrawerTab('settings'); }}
                  onPaneClick={() => setSelectedId(null)}
                  fitView
                  fitViewOptions={{ padding: 0.22 }}
                  snapToGrid
                  snapGrid={[16, 16]}
                  deleteKeyCode={['Backspace', 'Delete']}
                  defaultEdgeOptions={{ type: 'smoothstep' }}
                  proOptions={{ hideAttribution: false }}
                >
                  <Background variant={BackgroundVariant.Dots} gap={19} size={1} color="#303742" />
                  <Controls position="bottom-left" showInteractive={false} />
                  <MiniMap position="bottom-right" pannable zoomable maskColor="rgba(8, 11, 17, 0.72)" />
                </ReactFlow>
              </div>
            </div>

            <div className="bottom-drawer">
              <div className="drawer-tabs">
                <button className={drawerTab === 'settings' ? 'active' : ''} onClick={() => setDrawerTab('settings')}>
                  <Settings2 size={13} /> Node Inspector
                </button>
                <button className={drawerTab === 'runs' ? 'active' : ''} onClick={() => setDrawerTab('runs')}>
                  <History size={13} /> Execution & Step Trace {executions.length > 0 && <span className="run-count">{executions.length}</span>}
                </button>
                <button className={drawerTab === 'validation' ? 'active' : ''} onClick={() => setDrawerTab('validation')}>
                  <ShieldCheck size={13} /> Validation {validationIssues.length > 0 && <span className="run-count">{validationIssues.length}</span>}
                </button>
                <button className={drawerTab === 'versions' ? 'active' : ''} onClick={() => { setDrawerTab('versions'); if (workflowId) void loadVersions(workflowId); }}>
                  <RotateCcw size={13} /> Versions & Diffs {versions.length > 0 && <span className="run-count">{versions.length}</span>}
                </button>
              </div>

              {drawerTab === 'settings' && (
                <div className="inspector-content">
                  {selectedNode && selectedData ? (
                    <>
                      <div className="inspector-title">
                        <span className={`node-icon ${selectedData.kind}`}>{nodeIconFor(selectedData.kind)}</span>
                        <div>
                          <strong>{selectedData.label}</strong>
                          <span>{selectedData.kind} · ID: {selectedNode.id}</span>
                        </div>
                        <button
                          className="icon-btn"
                          title="Delete node"
                          onClick={() => {
                            if (TRIGGER_KINDS.has(selectedData.kind)) {
                              setNotice({ kind: 'error', message: 'The workflow needs one trigger node.' });
                              return;
                            }
                            pushHistory();
                            setNodes((curr) => curr.filter((n) => n.id !== selectedId));
                            setEdges((curr) => curr.filter((e) => e.source !== selectedId && e.target !== selectedId));
                            setSelectedId(null);
                          }}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>

                      <div className="inspector-fields">
                        <label>
                          Node Label
                          <input
                            value={selectedData.label}
                            onChange={(e) => updateSelectedNode((d) => ({ ...d, label: e.target.value, config: { ...d.config, label: e.target.value } }))}
                          />
                        </label>

                        {selectedData.kind === 'set' && (
                          <label>
                            Values (JSON with {'{{ $input.key }}'} expressions)
                            <textarea
                              className="code-input"
                              spellCheck={false}
                              defaultValue={JSON.stringify(selectedData.config.values ?? {}, null, 2)}
                              onBlur={(e) => {
                                try {
                                  const parsed = JSON.parse(e.target.value);
                                  updateSelectedNode((d) => ({ ...d, config: { ...d.config, values: parsed } }));
                                } catch {
                                  setNotice({ kind: 'error', message: 'Set Fields values must be valid JSON.' });
                                }
                              }}
                            />
                          </label>
                        )}

                        {selectedData.kind === 'http_request' && (
                          <>
                            <label>
                              HTTP Method & URL (use mock:// for local tests)
                              <div className="inline-row">
                                <select
                                  value={String(selectedData.config.method ?? 'GET')}
                                  onChange={(e) => updateSelectedNode((d) => ({ ...d, config: { ...d.config, method: e.target.value } }))}
                                >
                                  {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => <option key={m} value={m}>{m}</option>)}
                                </select>
                                <input
                                  value={String(selectedData.config.url ?? '')}
                                  onChange={(e) => updateSelectedNode((d) => ({ ...d, config: { ...d.config, url: e.target.value } }))}
                                />
                              </div>
                            </label>
                            <label>
                              Response Field & Credential
                              <div className="inline-row">
                                <input
                                  placeholder="response_field"
                                  value={String(selectedData.config.response_field ?? 'http')}
                                  onChange={(e) => updateSelectedNode((d) => ({ ...d, config: { ...d.config, response_field: e.target.value } }))}
                                />
                                <input
                                  placeholder="Credential name (optional)"
                                  value={String(selectedData.config.credential_name ?? '')}
                                  onChange={(e) => updateSelectedNode((d) => ({ ...d, config: { ...d.config, credential_name: e.target.value } }))}
                                />
                              </div>
                            </label>
                          </>
                        )}

                        {selectedData.kind === 'if_condition' && (
                          <label>
                            Condition (Field · Operator · Expected Value)
                            <div className="inline-row">
                              <input
                                placeholder="Field path (e.g. http.ok)"
                                value={String(selectedData.config.field ?? 'ok')}
                                onChange={(e) => updateSelectedNode((d) => ({ ...d, config: { ...d.config, field: e.target.value } }))}
                              />
                              <select
                                value={String(selectedData.config.operator ?? 'eq')}
                                onChange={(e) => updateSelectedNode((d) => ({ ...d, config: { ...d.config, operator: e.target.value } }))}
                              >
                                {['eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'contains', 'exists', 'regex'].map((op) => <option key={op} value={op}>{op}</option>)}
                              </select>
                              <input
                                placeholder="Compare value"
                                value={String(selectedData.config.value ?? 'true')}
                                onChange={(e) => {
                                  const raw = e.target.value;
                                  let parsed: unknown = raw;
                                  if (raw === 'true') parsed = true;
                                  else if (raw === 'false') parsed = false;
                                  else if (raw !== '' && !Number.isNaN(Number(raw))) parsed = Number(raw);
                                  updateSelectedNode((d) => ({ ...d, config: { ...d.config, value: parsed } }));
                                }}
                              />
                            </div>
                          </label>
                        )}

                        {selectedData.kind === 'sql_query' && (
                          <label>
                            Parameterized SQL Query (use :param bindings)
                            <textarea
                              className="code-input"
                              spellCheck={false}
                              value={String(selectedData.config.query ?? 'SELECT :val AS echoed')}
                              onChange={(e) => updateSelectedNode((d) => ({ ...d, config: { ...d.config, query: e.target.value } }))}
                            />
                          </label>
                        )}

                        {selectedData.kind === 'code' && (
                          <label>
                            Isolated Python Code (`data` dict in, assign `result` dict out)
                            <textarea
                              className="code-input"
                              spellCheck={false}
                              value={String(selectedData.config.code ?? "result = {**data, 'computed': True}")}
                              onChange={(e) => updateSelectedNode((d) => ({ ...d, config: { ...d.config, code: e.target.value } }))}
                            />
                          </label>
                        )}

                        {selectedData.kind === 'skill' && (
                          <label>
                            FlowForge Skill Package
                            <select
                              value={String(selectedData.config.skill_id ?? 'csv-json-transformation-helper')}
                              onChange={(e) => updateSelectedNode((d) => ({ ...d, config: { ...d.config, skill_id: e.target.value } }))}
                            >
                              {skills.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.id})</option>)}
                            </select>
                          </label>
                        )}

                        <label>
                          Error Handling & Max Attempts
                          <div className="inline-row">
                            <select
                              value={selectedData.on_error ?? 'fail'}
                              onChange={(e) => updateSelectedNode((d) => ({ ...d, on_error: e.target.value as any }))}
                            >
                              <option value="fail">Stop on error</option>
                              <option value="continue_with_error">Continue with _node_errors</option>
                              <option value="fallback_value">Emit fallback_values</option>
                            </select>
                            <input
                              type="number"
                              min={1}
                              max={5}
                              value={selectedData.retry_policy?.max_attempts ?? 1}
                              onChange={(e) =>
                                updateSelectedNode((d) => ({
                                  ...d,
                                  retry_policy: { max_attempts: Number(e.target.value) || 1, backoff_ms: 100, backoff_multiplier: 2.0 },
                                }))
                              }
                            />
                          </div>
                        </label>
                      </div>
                    </>
                  ) : (
                    <div className="empty-inspector">
                      <Settings2 size={22} />
                      <strong>Select any node on the canvas to configure its parameters, retry policy, and error handling.</strong>
                    </div>
                  )}
                </div>
              )}

              {drawerTab === 'runs' && (
                <div className="runs-content">
                  <div className="runs-left">
                    <div className="runs-heading">
                      <div><strong>Trigger Payload</strong><span>Mode: {executionMode}</span></div>
                      <select value={executionMode} onChange={(e) => setExecutionMode(e.target.value as any)}>
                        <option value="sync">Sync execution</option>
                        <option value="queued">Worker Queue</option>
                      </select>
                    </div>
                    <textarea className="test-input code-input" spellCheck={false} value={testInput} onChange={(e) => setTestInput(e.target.value)} />
                    <div className="inline-row">
                      <button className="btn btn-primary small" onClick={() => void executeWorkflow()} disabled={!workflowId || busy !== null}>
                        <Play size={13} fill="currentColor" /> Execute Now
                      </button>
                      {activeExecution?.status === 'waiting_approval' && (
                        <>
                          <button className="btn btn-secondary small" onClick={() => void approveOrRejectExecution(true)}>Approve</button>
                          <button className="btn btn-quiet small" onClick={() => void approveOrRejectExecution(false)}>Reject</button>
                        </>
                      )}
                      {activeExecution?.status === 'failed' && (
                        <button className="btn btn-secondary small" onClick={() => void diagnoseExecution()}>Diagnose Failure</button>
                      )}
                    </div>
                  </div>

                  <div className="runs-right">
                    <div className="runs-heading">
                      <div>
                        <strong>Step-by-Step Node Trace ({activeExecution?.node_runs?.length ?? 0} steps)</strong>
                        <span>{activeExecution ? `Run ${activeExecution.id.slice(0, 8)} · ${stamp(activeExecution.started_at)}` : 'Run workflow to inspect node traces'}</span>
                      </div>
                      {activeExecution && <span className={`status-pill ${activeExecution.status}`}>{activeExecution.status}</span>}
                    </div>

                    {activeExecution ? (
                      <div className="trace-split">
                        <div className="trace-step-list">
                          {(activeExecution.node_runs ?? []).map((nr) => (
                            <button
                              key={nr.node_id}
                              className={`trace-step-btn ${selectedTrace?.node_id === nr.node_id ? 'active' : ''}`}
                              onClick={() => setSelectedTraceNodeId(nr.node_id)}
                            >
                              <span className={`history-status ${nr.status}`} />
                              <strong>{nr.node_id}</strong>
                              <small>{nr.status} · {nr.duration_ms.toFixed(1)}ms</small>
                            </button>
                          ))}
                        </div>
                        <div className="trace-detail">
                          {selectedTrace ? (
                            <>
                              <div className="trace-detail-head">
                                <span>Node <b>{selectedTrace.node_id}</b> ({selectedTrace.node_type}) · Attempts: {selectedTrace.attempts}</span>
                                <button className="btn btn-quiet small" onClick={() => void replayFromNode(selectedTrace.node_id)}>
                                  <RotateCcw size={12} /> Replay from step
                                </button>
                              </div>
                              <pre className="result-json">
                                {JSON.stringify(
                                  {
                                    status: selectedTrace.status,
                                    branch_taken: selectedTrace.branch_taken,
                                    error: selectedTrace.error,
                                    output_data: selectedTrace.output_data,
                                    final_workflow_result: activeExecution.result_data,
                                    diagnosis: diagnosisResult,
                                  },
                                  null,
                                  2
                                )}
                              </pre>
                            </>
                          ) : (
                            <pre className="result-json">{JSON.stringify(activeExecution.result_data ?? { error: activeExecution.error }, null, 2)}</pre>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="result-empty"><Code2 size={22} /><span>Per-node input/output traces will appear here after execution.</span></div>
                    )}
                  </div>

                  <div className="history-strip">
                    <div className="history-strip-header">
                      <strong>Recent Runs</strong>
                      <button onClick={() => void loadWorkspaceData()}>Refresh</button>
                    </div>
                    {executions.slice(0, 6).map((run) => (
                      <button
                        key={run.id}
                        className="history-row"
                        onClick={() => {
                          setActiveExecution(run);
                          setSelectedTraceNodeId(run.node_runs?.[0]?.node_id ?? null);
                          decorateCanvasWithExecution(run);
                        }}
                      >
                        <span className={`history-status ${run.status}`} />
                        <span>{stamp(run.started_at)}</span>
                        <span className={`history-state ${run.status}`}>{run.status}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {drawerTab === 'validation' && (
                <div className="inspector-content">
                  <div className="inspector-title">
                    <ShieldCheck size={16} />
                    <div>
                      <strong>Workflow Graph & Schema Validation</strong>
                      <span>Checks cycles, disconnected nodes, trigger rules, and required node fields</span>
                    </div>
                    <button className="btn btn-secondary small" onClick={() => void validateCanvasGraph()}>Run Check</button>
                  </div>
                  {validationIssues.length === 0 ? (
                    <div className="field-helper" style={{ marginTop: 10 }}>
                      <Check size={15} /> No validation errors found. All nodes are reachable from the trigger and acyclic.
                    </div>
                  ) : (
                    <div className="issues-list">
                      {validationIssues.map((iss, i) => (
                        <div key={i} className="issue-item">
                          <strong>[{iss.code}] {iss.node_id ? `Node ${iss.node_id}: ` : ''}</strong> {iss.message}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {drawerTab === 'versions' && (
                <div className="inspector-content">
                  <div className="inspector-title">
                    <RotateCcw size={16} />
                    <div>
                      <strong>Workflow Revision History & Structural Diffs</strong>
                      <span>Every save or environment promotion creates an immutable snapshot</span>
                    </div>
                  </div>
                  <div className="versions-grid">
                    <div className="versions-list">
                      {versions.map((v) => (
                        <div key={v.id} className="version-row">
                          <span><b>v{v.version}</b> ({v.environment.toUpperCase()}) — {v.comment} · {stamp(v.created_at)}</span>
                          <div className="inline-row">
                            {v.version > 1 && (
                              <button
                                className="btn btn-quiet small"
                                onClick={async () => {
                                  if (!workflowId) return;
                                  const r = await fetch(`${API_BASE}/api/workflows/${workflowId}/versions/${v.version - 1}/diff/${v.version}`);
                                  if (r.ok) setVersionDiff(await r.json());
                                }}
                              >
                                Diff vs v{v.version - 1}
                              </button>
                            )}
                            <button
                              className="btn btn-secondary small"
                              onClick={async () => {
                                if (!workflowId) return;
                                const r = await fetch(`${API_BASE}/api/workflows/${workflowId}/versions/${v.version}/restore`, { method: 'POST' });
                                if (r.ok) {
                                  await openWorkflow(workflowId);
                                  setNotice({ kind: 'ok', message: `Restored workflow to revision v${v.version}.` });
                                }
                              }}
                            >
                              Restore
                            </button>
                          </div>
                        </div>
                      ))}
                      {versions.length === 0 && <div className="empty-list">Save the workflow to record v1.</div>}
                    </div>
                    {versionDiff && <pre className="result-json">{JSON.stringify(versionDiff, null, 2)}</pre>}
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {activeView === 'overview' && (
          <div className="page-view">
            <h2>Platform Overview & Runtime Diagnostics</h2>
            <div className="kpi-grid">
              <div className="kpi-card"><span>Workflows</span><strong>{diagnostics?.counts?.workflows ?? workflows.length}</strong><small>Persisted in DB</small></div>
              <div className="kpi-card"><span>Succeeded Runs</span><strong>{diagnostics?.counts?.executions_succeeded ?? 0}</strong><small>Deterministic DAG</small></div>
              <div className="kpi-card"><span>Queue Jobs</span><strong>{diagnostics?.queue?.total ?? 0}</strong><small>Queued: {diagnostics?.queue?.queued ?? 0} · Dead-letter: {diagnostics?.queue?.dead_letter ?? 0}</small></div>
              <div className="kpi-card"><span>SDK & Verified Skills</span><strong>{(diagnostics?.counts?.integrations ?? 21) + (diagnostics?.counts?.skills ?? 6)}</strong><small>21 Nodes · 6 SHA-256 Skills</small></div>
            </div>
            <div className="panel-card">
              <h3>Background Worker & Queue Controls</h3>
              <p>Process queued jobs, recover stale worker leases, or trigger due schedule jobs directly:</p>
              <div className="inline-row">
                <button className="btn btn-primary" onClick={async () => { await fetch(`${API_BASE}/api/queue/worker/run-next`, { method: 'POST' }); await loadWorkspaceData(); setNotice({ kind: 'ok', message: 'Worker processed next available job.' }); }}>
                  <Play size={14} /> Run Next Queue Job
                </button>
                <button className="btn btn-secondary" onClick={async () => { await fetch(`${API_BASE}/api/queue/worker/recover-stale`, { method: 'POST' }); await loadWorkspaceData(); setNotice({ kind: 'ok', message: 'Recovered stale worker leases.' }); }}>
                  <RefreshCw size={14} /> Recover Stale Leases
                </button>
                <button className="btn btn-secondary" onClick={async () => { await fetch(`${API_BASE}/api/schedules/tick`, { method: 'POST' }); await loadWorkspaceData(); setNotice({ kind: 'ok', message: 'Evaluated active schedules.' }); }}>
                  <Clock size={14} /> Tick Schedules Now
                </button>
              </div>
            </div>
          </div>
        )}

        {activeView === 'executions' && (
          <div className="page-view">
            <h2>Execution History & Step Inspector</h2>
            <div className="panel-card">
              {executions.map((ex) => (
                <div key={ex.id} className="version-row">
                  <span>
                    <span className={`status-pill ${ex.status}`}>{ex.status}</span>{' '}
                    <b>{ex.id.slice(0, 8)}</b> · Workflow {ex.workflow_id.slice(0, 8)} (v{ex.workflow_version}) · {ex.node_runs?.length ?? 0} node traces · {stamp(ex.started_at)}
                  </span>
                  <div className="inline-row">
                    <button className="btn btn-secondary small" onClick={() => { setActiveExecution(ex); setActiveView('editor'); setDrawerTab('runs'); }}>Inspect Trace</button>
                  </div>
                </div>
              ))}
              {executions.length === 0 && <div className="empty-list">No executions recorded yet.</div>}
            </div>
          </div>
        )}

        {activeView === 'credentials' && (
          <div className="page-view">
            <h2>Encrypted Credentials Vault (Fernet AES-128-CBC + PBKDF2-SHA256)</h2>
            <div className="panel-card">
              <h3>Store New Encrypted Credential</h3>
              <div className="inline-row">
                <input placeholder="Credential name (e.g. prod_api_token)" value={newCredName} onChange={(e) => setNewCredName(e.target.value)} />
                <select value={newCredKind} onChange={(e) => setNewCredKind(e.target.value)}>
                  <option value="http_bearer">HTTP Bearer Token</option>
                  <option value="http_header">API Key Header</option>
                  <option value="database_url">Database Connection</option>
                  <option value="ai_api_key">AI Provider Key</option>
                </select>
                <input type="password" placeholder="Secret token / value" value={newCredSecret} onChange={(e) => setNewCredSecret(e.target.value)} />
                <button
                  className="btn btn-primary"
                  onClick={async () => {
                    if (!newCredName || !newCredSecret) return;
                    const res = await fetch(`${API_BASE}/api/credentials`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ name: newCredName, kind: newCredKind, description: 'Stored via Vault UI', data: { token: newCredSecret } }),
                    });
                    if (res.ok) {
                      setNewCredName('');
                      setNewCredSecret('');
                      await loadWorkspaceData();
                      setNotice({ kind: 'ok', message: 'Credential encrypted and stored.' });
                    }
                  }}
                >
                  Encrypt & Save
                </button>
              </div>
            </div>
            <div className="panel-card">
              <h3>Stored Credentials (Secrets Redacted)</h3>
              {credentials.map((c) => (
                <div key={c.id} className="version-row">
                  <span><b>{c.name}</b> ({c.kind}) · Fields: {c.field_names.join(', ')} · Key: <code>{c.key_fingerprint}</code></span>
                  <button className="btn btn-quiet small" onClick={async () => { await fetch(`${API_BASE}/api/credentials/${c.id}`, { method: 'DELETE' }); await loadWorkspaceData(); }}><Trash2 size={13} /> Delete</button>
                </div>
              ))}
              {credentials.length === 0 && <div className="empty-list">No credentials stored yet.</div>}
            </div>
          </div>
        )}

        {activeView === 'integrations' && (
          <div className="page-view">
            <h2>First-Party Integration SDK ({integrations.length} Nodes) & Verified Skills ({skills.length})</h2>
            <div className="panel-card">
              <h3>Curated FlowForge Skills (SHA-256 Verified)</h3>
              {skills.map((s) => (
                <div key={s.id} className="version-row">
                  <div>
                    <strong>{s.name}</strong> (<code>{s.id}@{s.version}</code>) — {s.description}
                    <div><small>Integrity: <code>{s.integrity_hash.slice(0, 28)}…</code> · Permissions: {s.permissions.join(', ')}</small></div>
                  </div>
                  <button
                    className="btn btn-secondary small"
                    onClick={async () => {
                      const r = await fetch(`${API_BASE}/api/skills/${s.id}/execute`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(s.example_input),
                      });
                      if (r.ok) setSkillOutput(await r.json());
                    }}
                  >
                    Run Sample
                  </button>
                </div>
              ))}
              {skillOutput && <pre className="result-json">{JSON.stringify(skillOutput, null, 2)}</pre>}
            </div>
          </div>
        )}

        {activeView === 'templates' && (
          <div className="page-view">
            <h2>Workflow Templates & AI Workflow Drafter</h2>
            <div className="panel-card">
              <h3>AI-Assisted Workflow Drafting (Validated Drafts, Optional Provider)</h3>
              <div className="inline-row">
                <input
                  style={{ flex: 1 }}
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  placeholder="Describe the automation workflow you want to build..."
                />
                <button
                  className="btn btn-primary"
                  onClick={async () => {
                    const r = await fetch(`${API_BASE}/api/ai/draft`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ prompt: aiPrompt, provider: 'local' }),
                    });
                    if (r.ok) {
                      const draft = await r.json();
                      applyDefinitionToCanvas(draft.definition, { id: null, name: draft.suggested_name, env: 'dev', version: 1 });
                      setIsDirty(true);
                      setActiveView('editor');
                      setNotice({ kind: 'ok', message: 'AI draft validated and loaded onto canvas. Review and click Save.' });
                    }
                  }}
                >
                  <Sparkles size={14} /> Generate Validated Draft
                </button>
              </div>
            </div>

            <div className="panel-card">
              <h3>Verified First-Party Workflow Templates</h3>
              {templates.map((tpl) => (
                <div key={tpl.id} className="version-row">
                  <div>
                    <strong>{tpl.name}</strong> ({tpl.category}) — {tpl.description}
                  </div>
                  <button
                    className="btn btn-secondary small"
                    onClick={async () => {
                      const r = await fetch(`${API_BASE}/api/templates/${tpl.id}/instantiate`, { method: 'POST' });
                      if (r.ok) {
                        const created: WorkflowRecord = await r.json();
                        await loadWorkspaceData();
                        await openWorkflow(created.id);
                      }
                    }}
                  >
                    Use Template
                  </button>
                </div>
              ))}
            </div>

            <div className="panel-card">
              <h3>Import Workflow JSON</h3>
              <textarea
                className="code-input"
                style={{ width: '100%', height: 90 }}
                placeholder="Paste exported .flowforge.json here and press Import..."
                onBlur={(e) => { if (e.target.value.trim()) importWorkflowJson(e.target.value); }}
              />
            </div>
          </div>
        )}

        {activeView === 'governance' && (
          <div className="page-view">
            <h2>Webhooks, Schedules, API Tokens & Security Audit Trail</h2>
            <div className="panel-card">
              <h3>Register Webhook Endpoint & Schedule Trigger (Current Workflow)</h3>
              <div className="inline-row">
                <input placeholder="Webhook slug" value={newWebhookSlug} onChange={(e) => setNewWebhookSlug(e.target.value)} />
                <input placeholder="Optional HMAC secret" value={newWebhookSecret} onChange={(e) => setNewWebhookSecret(e.target.value)} />
                <button
                  className="btn btn-secondary"
                  disabled={!workflowId}
                  onClick={async () => {
                    if (!workflowId) return;
                    const r = await fetch(`${API_BASE}/api/webhooks`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ workflow_id: workflowId, path_slug: newWebhookSlug, secret: newWebhookSecret || null }),
                    });
                    if (r.ok) { await loadWorkspaceData(); setNotice({ kind: 'ok', message: `Webhook /api/webhooks/ingest/${newWebhookSlug} created.` }); }
                  }}
                >
                  Add Webhook
                </button>
                <input placeholder="Cron expr" value={newScheduleCron} onChange={(e) => setNewScheduleCron(e.target.value)} />
                <button
                  className="btn btn-secondary"
                  disabled={!workflowId}
                  onClick={async () => {
                    if (!workflowId) return;
                    const r = await fetch(`${API_BASE}/api/schedules`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ workflow_id: workflowId, cron_expr: newScheduleCron, interval_seconds: 300, input_template: { scheduled: true } }),
                    });
                    if (r.ok) { await loadWorkspaceData(); setNotice({ kind: 'ok', message: 'Schedule registered.' }); }
                  }}
                >
                  Add Schedule
                </button>
              </div>
              {webhooks.map((w) => (
                <div key={w.id} className="version-row">
                  <span>Webhook <code>/api/webhooks/ingest/{w.path_slug}</code> · HMAC Secret: {w.has_secret ? 'Enabled' : 'None'}</span>
                  <button className="btn btn-quiet small" onClick={async () => { await fetch(`${API_BASE}/api/webhooks/${w.id}`, { method: 'DELETE' }); await loadWorkspaceData(); }}>Delete</button>
                </div>
              ))}
              {schedules.map((s) => (
                <div key={s.id} className="version-row">
                  <span>Schedule <code>{s.cron_expr}</code> ({s.interval_seconds}s) · Next: {stamp(s.next_run_at)}</span>
                  <button className="btn btn-quiet small" onClick={async () => { await fetch(`${API_BASE}/api/schedules/${s.id}`, { method: 'DELETE' }); await loadWorkspaceData(); }}>Delete</button>
                </div>
              ))}
            </div>

            <div className="panel-card">
              <h3>Scoped API Tokens (RBAC)</h3>
              <div className="inline-row">
                <input placeholder="Token description" value={newTokenName} onChange={(e) => setNewTokenName(e.target.value)} />
                <select value={newTokenRole} onChange={(e) => setNewTokenRole(e.target.value as any)}>
                  <option value="viewer">Viewer (read-only)</option>
                  <option value="editor">Editor (read/write/execute)</option>
                  <option value="admin">Admin (all scopes)</option>
                </select>
                <button
                  className="btn btn-primary"
                  onClick={async () => {
                    const scopes = newTokenRole === 'viewer' ? ['workflows:read'] : newTokenRole === 'editor' ? ['workflows:read', 'workflows:write', 'workflows:execute'] : ['admin:*'];
                    const r = await fetch(`${API_BASE}/api/auth/tokens`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ name: newTokenName, role: newTokenRole, scopes }),
                    });
                    if (r.ok) {
                      const created = await r.json();
                      setNewlyCreatedTokenValue(created.token);
                      await loadWorkspaceData();
                    }
                  }}
                >
                  Create Token
                </button>
              </div>
              {newlyCreatedTokenValue && (
                <div className="field-helper" style={{ marginTop: 8 }}>
                  <KeyRound size={15} /> Copy new token now (shown once): <code>{newlyCreatedTokenValue}</code>
                </div>
              )}
              {tokens.map((t) => (
                <div key={t.id} className="version-row">
                  <span><b>{t.name}</b> (<code>{t.token_prefix}…</code>) · Role: {t.role} · Status: {t.is_revoked ? 'REVOKED' : 'ACTIVE'}</span>
                  {!t.is_revoked && (
                    <button className="btn btn-quiet small" onClick={async () => { await fetch(`${API_BASE}/api/auth/tokens/${t.id}/revoke`, { method: 'POST' }); await loadWorkspaceData(); }}>Revoke</button>
                  )}
                </div>
              ))}
            </div>

            <div className="panel-card">
              <h3>Immutable Security & Operational Audit Log</h3>
              {auditLogs.slice(0, 12).map((log) => (
                <div key={log.id} className="version-row">
                  <span><b>{log.action}</b> on {log.resource_type} (<code>{log.resource_id.slice(0, 8)}</code>) by {log.actor}</span>
                  <small>{stamp(log.created_at)}</small>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {notice && (
        <div className={`toast ${notice.kind}`}>
          <span className="toast-icon">{notice.kind === 'ok' ? <Check size={16} /> : notice.kind === 'error' ? <AlertCircle size={16} /> : <Sparkles size={16} />}</span>
          <span>{notice.message}</span>
          <button onClick={() => setNotice(null)} aria-label="Dismiss notification"><X size={14} /></button>
        </div>
      )}

      <div className="statusbar">
        <span><span className={`api-dot ${apiOnline ? 'online' : ''}`} /> {apiOnline ? 'Connected to FlowForge Control Plane' : 'Disconnected from API'}</span>
        <span>Apache-2.0 provisional · SSRF & Subprocess Isolation Enabled</span>
        <span>FlowForge Community <b>0.4.0</b></span>
      </div>
    </div>
  );
}

export default function App() {
  return <ReactFlowProvider><Editor /></ReactFlowProvider>;
}
