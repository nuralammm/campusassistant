import { defineConfig, devices } from '@playwright/test';
export default defineConfig({ testDir: './tests', use: { baseURL: process.env.WEB_URL || 'http://127.0.0.1:5173' }, projects: [{name: 'desktop', use: {...devices['Desktop Chrome']}}, {name: 'mobile', use: {...devices['iPhone 13'], defaultBrowserType: 'chromium'}}] });
