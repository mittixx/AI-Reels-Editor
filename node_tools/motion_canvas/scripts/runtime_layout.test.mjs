import assert from 'node:assert/strict';
import {mkdtemp, mkdir, rm, symlink, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {readJobLayout} from './runtime_layout.mjs';

test('reports Motion Canvas job files from the actual job root', async () => {
  const jobRoot = await mkdtemp(path.join(tmpdir(), 'motion-canvas-layout-'));
  try {
    await mkdir(path.join(jobRoot, 'src'));
    await mkdir(path.join(jobRoot, 'public'));
    await writeFile(path.join(jobRoot, 'index.html'), '<!doctype html>', 'utf8');
    await writeFile(path.join(jobRoot, 'src', 'main.ts'), 'export {};', 'utf8');
    await writeFile(path.join(jobRoot, 'src', 'project.ts'), 'export {};', 'utf8');
    await writeFile(path.join(jobRoot, 'public', 'motion_input.json'), '{}', 'utf8');

    const layout = await readJobLayout(jobRoot);

    assert.equal(layout.vite_root, jobRoot);
    assert.equal(layout.has_index_html, true);
    assert.equal(layout.has_main_ts, true);
    assert.equal(layout.has_project_ts, true);
    assert.equal(layout.has_motion_input, true);
    assert.deepEqual(layout.files, [
      'index.html',
      'public/motion_input.json',
      'src/main.ts',
      'src/project.ts',
    ]);
  } finally {
    await rm(jobRoot, {recursive: true, force: true});
  }
});

test('Windows-compatible job link exposes root Vite dependencies without copying', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'motion-canvas-root-'));
  const jobRoot = await mkdtemp(path.join(tmpdir(), 'motion-canvas-job-'));
  try {
    await mkdir(path.join(root, 'node_modules', 'vite'), {recursive: true});
    await mkdir(path.join(root, 'node_modules', 'esbuild'), {recursive: true});
    await symlink(path.join(root, 'node_modules'), path.join(jobRoot, 'node_modules'), process.platform === 'win32' ? 'junction' : 'dir');
    const layout = await readJobLayout(jobRoot);
    assert.equal(await import('node:fs/promises').then(({stat}) => stat(path.join(jobRoot, 'node_modules', 'vite')).then(() => true)), true);
    assert.equal(layout.job_root, jobRoot);
  } finally {
    await rm(root, {recursive: true, force: true});
    await rm(jobRoot, {recursive: true, force: true});
  }
});
