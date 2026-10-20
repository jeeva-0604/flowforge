import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const apiBaseURL = (process.env.FLOWFORGE_E2E_API_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, '');

async function dragConnect(page: Page, sourceTestId: string, targetTestId: string) {
  const source = page.getByTestId(sourceTestId);
  const target = page.getByTestId(targetTestId);
  await expect(source).toBeVisible();
  await expect(target).toBeVisible();
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  expect(sourceBox, `Could not measure source handle ${sourceTestId}`).not.toBeNull();
  expect(targetBox, `Could not measure target handle ${targetTestId}`).not.toBeNull();
  if (!sourceBox || !targetBox) throw new Error('Flow canvas handle has no browser bounding box.');

  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, { steps: 18 });
  await page.mouse.up();
}

async function cleanupWorkflow(request: APIRequestContext, workflowId: string | null) {
  if (!workflowId) return;
  const response = await request.delete(`${apiBaseURL}/api/workflows/${workflowId}`);
  // Treat an already removed workflow as clean-up success. Other errors should
  // be visible but must not hide a failure that occurred earlier in the test.
  if (!response.ok() && response.status() !== 404) {
    console.warn(`FlowForge E2E cleanup failed (${response.status()}): ${await response.text()}`);
  }
}

test('canvas connections persist across save/load and the saved workflow executes', async ({ page, request }) => {
  const health = await request.get(`${apiBaseURL}/health`);
  expect(health.ok(), `FlowForge API is not reachable at ${apiBaseURL}; start FastAPI first.`).toBeTruthy();

  let workflowId: string | null = null;
  const workflowName = `Playwright acceptance ${new Date().toISOString()} ${Math.random().toString(16).slice(2, 6)}`;
  try {
    await page.goto('/');
    await expect(page.getByText('API Connected')).toBeVisible();

    // The New Workflow action lays down the real starter graph with manual
    // trigger -> HTTP mock -> IF -> Set Fields -> Output.
    await page.getByTitle('New workflow').click();
    await page.getByLabel('Workflow name').fill(workflowName);
    await expect(page.getByTestId('workflow-canvas')).toBeVisible();
    await expect(page.getByTestId('node-if_1')).toBeVisible();
    await expect(page.getByTestId('node-output_1')).toBeVisible();

    // Exercise a real React Flow pointer connection rather than editing edge
    // JSON through the API. The FALSE branch also points to Output.
    await dragConnect(page, 'source-handle-if_1-false', 'target-handle-output_1');
    await expect(page.locator('.meta-line')).toContainText('5 connections');

    const [createResponse] = await Promise.all([
      page.waitForResponse((response) =>
        response.url() === `${apiBaseURL}/api/workflows` &&
        response.request().method() === 'POST',
      ),
      page.getByRole('button', { name: 'Save', exact: true }).click(),
    ]);
    expect(createResponse.ok(), `Workflow save failed: ${await createResponse.text()}`).toBeTruthy();
    const saved = await createResponse.json() as { id: string; version: number };
    workflowId = saved.id;
    expect(workflowId).toBeTruthy();
    expect(saved.version).toBe(1);
    await expect(page.getByText(new RegExp(`Saved .*${workflowName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}.*v1`))).toBeVisible();

    // Re-open the persisted workflow from the application sidebar. The edge
    // count proves canvas connections were saved into the workflow definition.
    await page.getByRole('button', { name: new RegExp(workflowName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).click();
    await expect(page.locator('.meta-line')).toContainText('5 connections');
    await expect(page.getByTestId('node-if_1')).toBeVisible();

    await page.getByRole('button', { name: 'Execute', exact: true }).click();
    await expect(page.getByText('Workflow execution succeeded.')).toBeVisible();
    await expect(page.locator('.status-pill.succeeded')).toBeVisible();
    await expect(page.getByText(/Step-by-Step Node Trace/)).toBeVisible();
    await expect(page.locator('.trace-step-btn')).toHaveCount(5);

    // Verify the server persisted an execution rather than only updating UI state.
    const executionList = await request.get(`${apiBaseURL}/api/executions?workflow_id=${workflowId}`);
    expect(executionList.ok(), `Could not query persisted executions: ${await executionList.text()}`).toBeTruthy();
    const executions = await executionList.json() as Array<{ workflow_id: string; status: string }>;
    expect(executions.some((item) => item.workflow_id === workflowId && item.status === 'succeeded')).toBeTruthy();
  } finally {
    await cleanupWorkflow(request, workflowId);
  }
});

test('node library actions are functional and undo restores the prior graph', async ({ page, request }) => {
  const health = await request.get(`${apiBaseURL}/health`);
  expect(health.ok(), `FlowForge API is not reachable at ${apiBaseURL}; start FastAPI first.`).toBeTruthy();

  await page.goto('/');
  await expect(page.getByText('API Connected')).toBeVisible();
  await page.getByTitle('New workflow').click();
  await expect(page.locator('.meta-line')).toContainText('5 nodes');
  await page.getByTestId('palette-node-wait').click();
  await expect(page.locator('.meta-line')).toContainText('6 nodes');
  await expect(page.getByTestId(/^node-wait_/)).toBeVisible();
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.locator('.meta-line')).toContainText('5 nodes');
});
