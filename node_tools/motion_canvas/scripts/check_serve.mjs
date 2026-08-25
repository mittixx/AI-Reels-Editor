import {createServer} from 'vite';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const server = await createServer({
  root,
  configFile: path.join(root, 'vite.config.ts'),
  logLevel: 'error',
  server: {host: '127.0.0.1', port: 0, strictPort: true},
});

try {
  await server.listen();
  const address = server.httpServer?.address();
  if (!address || typeof address === 'string') {
    throw new Error('Motion Canvas preview server did not bind a TCP port');
  }
  const url = `http://127.0.0.1:${address.port}/`;
  const response = await fetch(url, {signal: AbortSignal.timeout(5000)});
  if (!response.ok) {
    throw new Error(`Motion Canvas preview root returned HTTP ${response.status}`);
  }
  process.stdout.write(`Motion Canvas preview check passed on ${url} (HTTP ${response.status})\n`);
} finally {
  await server.close();
}
