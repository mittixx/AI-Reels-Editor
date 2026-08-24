import {spawn} from 'node:child_process';
import {cp, mkdir, readFile, readdir, rm, stat, writeFile} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {buildNpmServeLaunchSpec} from './process_launcher.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const value = name => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };
const input = value('--input');
const output = value('--output');
const jobId = value('--job-id');
const supportedComponents = new Set([
  'AnimatedStat', 'AnimatedCounter', 'Comparison', 'ProcessFlow', 'Timeline', 'Quote',
  'CodeHighlight', 'FeatureList', 'ProductFeature', 'BeforeAfter', 'Callout', 'Chart', 'Diagram',
]);
const assertJob = candidate => {
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) throw new Error('Motion input must be an object');
  if (candidate.schema_version !== '1.3') throw new Error('Motion input has unsupported schema_version');
  if (typeof candidate.job_id !== 'string' || !candidate.job_id) throw new Error('Motion input is missing job_id');
  if (typeof candidate.component !== 'string' || !supportedComponents.has(candidate.component)) throw new Error('Motion input has unsupported component');
  if (!Number.isFinite(candidate.duration) || candidate.duration <= 0) throw new Error('Motion input has invalid duration');
  if (typeof candidate.preset !== 'string' || !candidate.preset.trim()) throw new Error('Motion input has invalid preset');
  if (!candidate.data || typeof candidate.data !== 'object' || Array.isArray(candidate.data)) throw new Error('Motion input has invalid data');
  return candidate;
};
if (!input || !output || !jobId) {
  process.stderr.write('Usage: npm run render:asset -- --input job.json --output motion.mp4 --job-id UNIQUE_ID\n');
  process.exit(2);
}
if (!/^[A-Za-z0-9_-]+$/.test(jobId)) throw new Error('job_id has unsafe characters');
const job = assertJob(JSON.parse(await readFile(path.resolve(input), 'utf8')));
if (job.job_id !== jobId) throw new Error('Input job_id does not match --job-id');
const runtimeRoot = path.join(root, '.render-jobs', jobId);
await rm(runtimeRoot, {recursive: true, force: true});
await mkdir(runtimeRoot, {recursive: true});
await cp(path.join(root, 'src'), path.join(runtimeRoot, 'src'), {recursive: true});
await cp(path.join(root, 'public'), path.join(runtimeRoot, 'public'), {recursive: true});
await cp(path.join(root, 'vite.config.ts'), path.join(runtimeRoot, 'vite.config.ts'));
await cp(path.join(root, 'tsconfig.json'), path.join(runtimeRoot, 'tsconfig.json'));
await writeFile(path.join(runtimeRoot, 'public', 'motion_input.json'), JSON.stringify(job, null, 2), 'utf8');
const port = 9200 + Math.floor(Math.random() * 500);
const launch = buildNpmServeLaunchSpec({runtimeRoot, port});
const server = spawn(launch.command, launch.args, {cwd: root, stdio: ['ignore', 'pipe', 'pipe'], shell: false});
let serverStdout = '';
let serverStderr = '';
const started = new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('Motion Canvas preview timeout')), 60000);
  const onData = chunk => { const value = String(chunk); if (value.includes(`localhost:${port}`) || value.includes(`127.0.0.1:${port}`)) { clearTimeout(timer); resolve(); } };
  server.stdout.on('data', chunk => { serverStdout += String(chunk); onData(chunk); });
  server.stderr.on('data', chunk => { serverStderr += String(chunk); onData(chunk); });
  server.once('error', error => { clearTimeout(timer); reject(new Error(`Motion Canvas server launch failed: ${error.message}`)); });
  server.once('exit', code => { clearTimeout(timer); reject(new Error(`Motion Canvas server exited: ${code}; stdout=${serverStdout.slice(-500)}; stderr=${serverStderr.slice(-500)}`)); });
});
let browser;
try {
  await started;
  browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  await page.goto(`http://127.0.0.1:${port}`, {waitUntil: 'networkidle', timeout: 90000});
  const settings = page.getByRole('button', {name: /video settings/i}).or(page.locator('[title*="Video Settings" i]'));
  if (await settings.count()) await settings.first().click();
  const render = page.getByRole('button', {name: /^render$/i}).or(page.getByText('RENDER', {exact: true}));
  const renderStarted = Date.now();
  await render.last().click({timeout: 30000});
  const findMp4 = async dir => {
    const found = [];
    for (const item of await readdir(dir, {withFileTypes: true}).catch(() => [])) {
      const full = path.join(dir, item.name);
      if (item.isDirectory()) found.push(...await findMp4(full)); else if (item.name.endsWith('.mp4')) found.push(full);
    }
    return found;
  };
  const deadline = Date.now() + 15 * 60 * 1000;
  let rendered;
  const waitForStableFile = async candidate => {
    let previous;
    let stable = 0;
    for (let attempt = 0; attempt < 8; attempt += 1) {
      const info = await stat(candidate);
      if (info.size <= 0 || info.mtimeMs < renderStarted - 1000) throw new Error(`Motion Canvas output is stale or empty for ${jobId}`);
      const current = `${info.size}:${info.mtimeMs}`;
      stable = current === previous ? stable + 1 : 0;
      if (stable >= 2) return info;
      previous = current;
      await new Promise(resolve => setTimeout(resolve, 350));
    }
    throw new Error(`Motion Canvas output did not stabilize for ${jobId}`);
  };
  const decodeCheck = target => new Promise((resolve, reject) => {
    const decoder = spawn('ffmpeg', ['-v', 'error', '-xerror', '-err_detect', 'explode', '-i', target, '-map', '0', '-f', 'null', '-'], {stdio: ['ignore', 'ignore', 'pipe']});
    let stderr = '';
    decoder.stderr.on('data', chunk => { stderr += String(chunk); });
    decoder.once('error', reject);
    decoder.once('exit', code => code === 0 ? resolve() : reject(new Error(`Motion Canvas output failed FFmpeg decode-check: ${stderr.slice(-500)}`)));
  });
  while (Date.now() < deadline) {
    const candidates = await findMp4(path.join(runtimeRoot, 'output'));
    const fresh = [];
    for (const candidate of candidates) {
      const info = await stat(candidate);
      if (info.size > 0 && info.mtimeMs >= renderStarted - 1000) fresh.push(candidate);
    }
    if (fresh.length > 1) throw new Error(`Motion Canvas produced ambiguous outputs for ${jobId}`);
    if (fresh.length === 1) {
      await waitForStableFile(fresh[0]);
      rendered = fresh[0];
      break;
    }
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  if (!rendered) throw new Error('Motion Canvas did not produce MP4');
  await mkdir(path.dirname(path.resolve(output)), {recursive: true});
  await cp(rendered, path.resolve(output));
  await waitForStableFile(path.resolve(output));
  await decodeCheck(path.resolve(output));
  process.stdout.write(JSON.stringify({success: true, job_id: jobId, output: path.resolve(output), component: job.component}) + '\n');
} finally {
  if (browser) await browser.close();
  server.kill();
  await rm(runtimeRoot, {recursive: true, force: true});
}
