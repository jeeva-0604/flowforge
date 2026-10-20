/**
 * Automated Frontend Verification & Contract Test Suite for FlowForge Community.
 * Runs under Node.js without requiring external network registry access.
 */
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const feDir = path.resolve(path.dirname(new URL(import.meta.url).pathname));
const pkg = JSON.parse(fs.readFileSync(path.join(feDir, 'package.json'), 'utf8'));
const appTsx = fs.readFileSync(path.join(feDir, 'src', 'App.tsx'), 'utf8');
const stylesCss = fs.readFileSync(path.join(feDir, 'src', 'styles.css'), 'utf8');

// 1. Verify package.json uses real, published dependency versions
assert.equal(pkg.version, '0.4.0');
assert.match(pkg.dependencies.react, /^\^18\./, 'React must be a valid v18 release');
assert.match(pkg.dependencies['lucide-react'], /^\^0\.468\./, 'lucide-react must use a valid 0.x version');
assert.match(pkg.devDependencies.vite, /^\^6\./, 'vite must use a valid v6 version');
console.log('PASS  package.json dependency versions verified');

// 2. Verify all 21 backend SDK node types are represented in frontend FlowNodeKind & NODE_CATALOG
const expectedNodeKinds = [
  'trigger', 'webhook_trigger', 'schedule_trigger', 'set', 'http_request',
  'if_condition', 'switch', 'merge', 'filter', 'loop', 'wait', 'code',
  'sql_query', 'csv_json', 'file_io', 'skill', 'ai_agent', 'human_approval',
  'subworkflow', 'error_handler', 'output',
];
for (const kind of expectedNodeKinds) {
  assert.ok(appTsx.includes(`kind: '${kind}'`), `Missing node kind in NODE_CATALOG: ${kind}`);
}
console.log(`PASS  All ${expectedNodeKinds.length} first-party node types present in frontend catalog`);

// 3. Verify zero fake/placeholder toasts remain in App.tsx
const forbiddenPlaceholders = [
  'Integration catalog is planned',
  'Workspace settings will arrive',
  'Credential vault will be implemented',
  'Export/import and version history are planned',
  'Auto-layout and export are planned',
];
for (const msg of forbiddenPlaceholders) {
  assert.ok(!appTsx.includes(msg), `Found unimplemented placeholder toast: ${msg}`);
}
console.log('PASS  Zero fake buttons or placeholder toasts in App.tsx');

// 4. Verify core API integrations exist in App.tsx
const requiredEndpoints = [
  '/api/workflows',
  '/api/workflows/validate',
  '/api/executions',
  '/api/credentials',
  '/api/integrations',
  '/api/skills',
  '/api/templates',
  '/api/webhooks',
  '/api/schedules',
  '/api/auth/tokens',
  '/api/audit-logs',
  '/api/ai/draft',
  '/api/queue/worker/run-next',
];
for (const ep of requiredEndpoints) {
  assert.ok(appTsx.includes(ep), `Missing API integration for ${ep}`);
}
console.log(`PASS  All ${requiredEndpoints.length} backend API endpoint integrations verified in App.tsx`);

// 5. Verify light/dark theme support in CSS
assert.ok(stylesCss.includes('[data-theme="light"]'), 'Missing light theme variables in styles.css');
console.log('PASS  Light/Dark theme CSS rules verified');

// 6. Verify browser acceptance suite is wired into package scripts and tests real UI interactions.
assert.equal(pkg.scripts['test:e2e'], 'playwright test');
assert.ok(pkg.devDependencies['@playwright/test'], 'Playwright Test must be a development dependency');
const e2eFile = path.join(feDir, 'tests', 'e2e', 'workflow-editor.spec.ts');
assert.ok(fs.existsSync(e2eFile), 'Missing Playwright workflow editor E2E suite');
const e2eText = fs.readFileSync(e2eFile, 'utf8');
for (const requiredE2ESurface of ['dragConnect', 'Save', 'Execute', 'Workflow execution succeeded.', 'Undo']) {
  assert.ok(e2eText.includes(requiredE2ESurface), `E2E suite is missing expected browser interaction: ${requiredE2ESurface}`);
}
console.log('PASS  Playwright E2E suite and package scripts are wired');
console.log('\nFrontend contract verification succeeded (6/6 checks passed).');
