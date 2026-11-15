import { cpSync, existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';

const output = resolve('.next/standalone');
if (!existsSync(resolve(output, 'server.js'))) throw new Error('Run npm run build before npm start.');
cpSync('.next/static', resolve(output, '.next/static'), { recursive: true });
if (existsSync('public')) cpSync('public', resolve(output, 'public'), { recursive: true });
const child = spawn(process.execPath, [resolve(output, 'server.js')], {
  stdio: 'inherit', env: { ...process.env, HOSTNAME: process.env.HOSTNAME || '127.0.0.1', PORT: process.env.PORT || '3000' }
});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
child.on('exit', code => process.exit(code ?? 0));
