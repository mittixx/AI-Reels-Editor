import {readdir, stat} from 'node:fs/promises';
import path from 'node:path';

const exists = async target => stat(target).then(info => info.isFile()).catch(() => false);

const listFiles = async (jobRoot, directory = jobRoot) => {
  const entries = await readdir(directory, {withFileTypes: true});
  const files = [];
  for (const entry of entries) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await listFiles(jobRoot, target));
    else files.push(path.relative(jobRoot, target).split(path.sep).join('/'));
  }
  return files.sort();
};

/** Return the actual isolated Vite project layout for a Motion Canvas job. */
export const readJobLayout = async jobRoot => ({
  job_root: jobRoot,
  vite_root: jobRoot,
  files: await listFiles(jobRoot),
  has_index_html: await exists(path.join(jobRoot, 'index.html')),
  has_main_ts: await exists(path.join(jobRoot, 'src', 'main.ts')),
  has_project_ts: await exists(path.join(jobRoot, 'src', 'project.ts')),
  has_motion_input: await exists(path.join(jobRoot, 'public', 'motion_input.json')),
});
