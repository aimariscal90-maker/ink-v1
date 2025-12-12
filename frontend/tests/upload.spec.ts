/// <reference types="node" />
/// <reference types="node" />
import { test, expect } from '@playwright/test';
import * as path from 'path';

test('upload file and check CORS header', async ({ page, baseURL }) => {
  const url = baseURL ?? 'http://127.0.0.1:5173';
  await page.goto(url);

  // In ESM environments `__dirname` may be undefined; use process.cwd() to resolve repo paths
  const filePath = path.resolve(process.cwd(), 'backend/tests/files/sample.pdf');

  // Set the file on input
  await page.setInputFiles('input[type="file"]', filePath);

  // Start waiting for the network response
  const [response] = await Promise.all([
    page.waitForResponse((resp) => resp.url().includes('/api/v1/jobs') && resp.request().method() === 'POST'),
    page.click('button[type="submit"]'),
  ]);

  // Ensure we got a response and it contains the CORS header
  expect(response).toBeTruthy();

  const headers = response.headers();
  console.log('Response headers:', headers);

  expect(headers['access-control-allow-origin'] || headers['Access-Control-Allow-Origin']).toBeDefined();

  // Check that the UI shows a job id and status
  await expect(page.locator('text=Job ID:')).toBeVisible();
});
