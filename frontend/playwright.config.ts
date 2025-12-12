import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests',
  timeout: 60_000,
  use: {
    headless: true,
    baseURL: 'http://127.0.0.1:5173',
    viewport: { width: 1280, height: 800 },
    // Run tests against local frontend which proxies /api to backend.
    // Also set CLI env so that the app uses relative api URL (Vite env fallback).
    env: {
      VITE_API_BASE_URL: '',
    },
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
  webServer: {
    command: "sh -c 'cd ../backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 & cd ../frontend && VITE_API_BASE_URL= npm run dev'",
    port: 5173,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
