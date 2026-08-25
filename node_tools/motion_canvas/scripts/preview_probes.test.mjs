import assert from 'node:assert/strict';
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import test from 'node:test';
import {probePreviewResources} from './preview_probes.mjs';

test('reports HTTP status for Vite document and Motion Canvas entries', async () => {
  const server = http.createServer((request, response) => {
    const statuses = {'/': 200, '/src/main.ts': 200, '/src/project.ts': 404, '/motion_input.json': 200};
    response.writeHead(statuses[request.url] ?? 404, {'content-type': 'text/plain'});
    response.end(request.url);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const address = server.address();
    const probes = await probePreviewResources(`http://127.0.0.1:${address.port}`);

    assert.deepEqual(probes.map(item => [new URL(item.url).pathname, item.status]), [
      ['/', 200],
      ['/src/main.ts', 200],
      ['/src/project.ts', 404],
      ['/motion_input.json', 200],
    ]);
  } finally {
    await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});

test('Motion Canvas template never requests public motion input path', async () => {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const sources = await Promise.all([
    readFile(path.join(root, 'src', 'main.ts'), 'utf8'),
    readFile(path.join(root, 'src', 'project.ts'), 'utf8'),
    readFile(path.join(root, 'src', 'scenes', 'asset.tsx'), 'utf8'),
  ]);
  assert.equal(sources.join('\n').includes('/public/motion_input.json'), false);
  assert.equal(sources.join('\n').includes("'/motion_input.json'"), true);
});
