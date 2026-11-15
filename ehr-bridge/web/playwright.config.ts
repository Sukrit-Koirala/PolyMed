import {defineConfig,devices} from '@playwright/test';
export default defineConfig({testDir:'./tests',workers:1,fullyParallel:false,timeout:45000,reporter:'list',use:{baseURL:'http://127.0.0.1:3200',trace:'retain-on-failure',screenshot:'only-on-failure'},projects:[{name:'browser',use:{...devices['Desktop Chrome'],...(process.platform==='win32'?{channel:'msedge'}:{})}}]});
