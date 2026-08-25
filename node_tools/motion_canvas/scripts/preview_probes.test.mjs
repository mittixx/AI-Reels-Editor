import assert from 'node:assert/strict';
import http from 'node:http';
import test from 'node:test';
import {probePreviewResources} from './preview_probes.mjs';

test('reports HTTP status for Vite document and Motion Canvas entries', async () => {
  const server = http.createServer((request, response) => {
    const statuses = {'/': 200, '/src/main.ts': 200, '/src/project.ts': 404};
    response.writeHead(statuses[request.url] ?? 404, {'content-type': 'text/plain'});
    response.end(request.url);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const address = server.address();
    const probes = await probePreviewResources(`http://127.0.0.1:${address.port}`);

    assert.deepEqual(probes.map(item => [item.path, item.status]), [
      ['/', 200],
      ['/src/main.ts', 200],
      ['/src/project.ts', 404],
    ]);
  } finally {
    await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});
