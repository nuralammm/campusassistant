import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir:'./tests',timeout:45000,
  use:{baseURL:process.env.WEB_URL||'http://127.0.0.1:5173',
       launchOptions:process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-dev-shm-usage']}:{}},
  projects:[{name:'desktop',use:{...devices['Desktop Chrome']}},{name:'mobile',use:{...devices['Pixel 7'],deviceScaleFactor:1}}]
});
