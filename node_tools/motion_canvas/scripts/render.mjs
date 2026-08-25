import {spawn} from 'node:child_process';
import {cp, mkdir, readFile, readdir, rm, stat, writeFile} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {buildNpmServeLaunchSpec} from './process_launcher.mjs';
import {probePreviewResources} from './preview_probes.mjs';
import {readJobLayout} from './runtime_layout.mjs';

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
await cp(path.join(root, 'index.html'), path.join(runtimeRoot, 'index.html'));
await cp(path.join(root, 'vite.config.ts'), path.join(runtimeRoot, 'vite.config.ts'));
await cp(path.join(root, 'tsconfig.json'), path.join(runtimeRoot, 'tsconfig.json'));
await writeFile(path.join(runtimeRoot, 'public', 'motion_input.json'), JSON.stringify(job, null, 2), 'utf8');
const jobLayout = await readJobLayout(runtimeRoot);
const jobLayoutDebug = `MOTION_CANVAS_JOB_LAYOUT_DEBUG ${JSON.stringify(jobLayout)}`;
process.stderr.write(`${jobLayoutDebug}\n`);
const port = 9200 + Math.floor(Math.random() * 500);
const launch = buildNpmServeLaunchSpec({runtimeRoot, root, port});
const expectedUrl = `http://127.0.0.1:${port}`;
const launchDebug = JSON.stringify({command: launch.command, args: launch.args, cwd: root});
process.stderr.write(`MOTION_CANVAS_PREVIEW_DEBUG launch=${launchDebug}\n`);
process.stderr.write(`MOTION_CANVAS_PREVIEW_DEBUG spawn_command=${launch.command}\n`);
process.stderr.write(`MOTION_CANVAS_PREVIEW_DEBUG spawn_args=${JSON.stringify(launch.args)}\n`);
process.stderr.write(`MOTION_CANVAS_PREVIEW_DEBUG port=${port} expected_url=${expectedUrl}\n`);
process.stderr.write(`PREVIEW_URL_DEBUG ${JSON.stringify({expected_url: expectedUrl, port})}\n`);
const server = spawn(launch.command, launch.args, {cwd: path.resolve(root), env: {...process.env, MOTION_CANVAS_VITE_ROOT: runtimeRoot, NODE_PATH: path.join(root, 'node_modules')}, stdio: ['ignore', 'pipe', 'pipe'], shell: false});
process.stderr.write(`SERVER_PROCESS_PID ${server.pid ?? 'unavailable'}\n`);
let serverStdout = '';
let serverStderr = '';
let stdoutReceived = false;
let stderrReceived = false;
let serverLaunchError;
let serverExitCode;
let previewResourceProbes = [];
const exists = async target => stat(target).then(() => true).catch(() => false);
const readDebugText = async target => readFile(target, 'utf8').catch(error => `<unavailable: ${error.message}>`);
const jobFailureDebug = async () => ({
  job_root: runtimeRoot,
  cwd: root,
  files: (await readJobLayout(runtimeRoot)).files,
  vite_config_ts: await readDebugText(path.join(runtimeRoot, 'vite.config.ts')),
  package_json: await readDebugText(path.join(runtimeRoot, 'package.json')),
  job_node_modules_vite: await exists(path.join(runtimeRoot, 'node_modules', 'vite')),
  job_node_modules_esbuild: await exists(path.join(runtimeRoot, 'node_modules', 'esbuild')),
  root_node_modules_vite: await exists(path.join(root, 'node_modules', 'vite')),
  root_node_modules_esbuild: await exists(path.join(root, 'node_modules', 'esbuild')),
});
server.stdout.on('data', chunk => {
  serverStdout += String(chunk);
  if (!stdoutReceived) {
    stdoutReceived = true;
    process.stderr.write('MOTION_CANVAS_PREVIEW_DEBUG stdout_received=true\n');
  }
});
server.stderr.on('data', chunk => {
  serverStderr += String(chunk);
  if (!stderrReceived) {
    stderrReceived = true;
    process.stderr.write('MOTION_CANVAS_PREVIEW_DEBUG stderr_received=true\n');
  }
});
server.once('error', error => { serverLaunchError = error; });
server.once('exit', code => { serverExitCode = code; });

const recordPreviewResourceProbes = async () => {
  const probes = await probePreviewResources(expectedUrl);
  process.stderr.write(`MOTION_CANVAS_PREVIEW_RESOURCE_HTTP_DEBUG ${JSON.stringify(probes)}\n`);
  return probes;
};

const waitForPreview = async () => {
  const deadline = Date.now() + 60000;
  let lastProbeError = '';
  let lastProbeStatus = null;
  let lastProbeBody = '';
  let probeReported = false;
  while (Date.now() < deadline) {
    if (serverLaunchError) throw new Error(`Motion Canvas server launch failed: ${serverLaunchError.message}`);
    if (serverExitCode !== undefined) {
      throw new Error(
        `MOTION_CANVAS_SERVER_BOOT_ERROR exit_code=${serverExitCode}; ` +
        `stdout=${serverStdout}; stderr_first_2000=${serverStderr.slice(0, 2000)}; ` +
        `stderr_last_2000=${serverStderr.slice(-2000)}`,
      );
    }
    try {
      const response = await fetch(expectedUrl, {signal: AbortSignal.timeout(1000)});
      const body = (await response.text()).slice(0, 500);
      lastProbeStatus = response.status;
      lastProbeBody = body;
      if (!probeReported) {
        probeReported = true;
        previewResourceProbes = await recordPreviewResourceProbes();
        process.stderr.write(`MOTION_CANVAS_RESOURCE_CHECK ${JSON.stringify(previewResourceProbes)}\n`);
        process.stderr.write(
          `MOTION_CANVAS_PREVIEW_HTTP_DEBUG ${JSON.stringify({url: expectedUrl, status: response.status, response_text: body})}\n`,
        );
      }
      if (response.ok) {
        process.stderr.write(`MOTION_CANVAS_PREVIEW_DEBUG preview_ready=true status=${response.status}\n`);
        return;
      }
      lastProbeError = `HTTP ${response.status}`;
    } catch (error) {
      lastProbeError = error instanceof Error ? error.message : String(error);
    }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error(
    `Motion Canvas preview timeout; port=${port}; expected_url=${expectedUrl}; ` +
    `launch=${launchDebug}; stdout_received=${stdoutReceived}; stderr_received=${stderrReceived}; ` +
    `last_probe_error=${lastProbeError}; last_probe_status=${lastProbeStatus}; ` +
    `last_probe_response_text=${JSON.stringify(lastProbeBody)}; ` +
    `MOTION_CANVAS_RESOURCE_CHECK=${JSON.stringify(previewResourceProbes)}; ` +
    `SERVER_STDOUT_LAST_LINES=${JSON.stringify(serverStdout.split(/\r?\n/).filter(Boolean).slice(-20))}; ` +
    `SERVER_STDERR_LAST_LINES=${JSON.stringify(serverStderr.split(/\r?\n/).filter(Boolean).slice(-20))}; ` +
    `PREVIEW_URL_DEBUG=${expectedUrl}; SERVER_PROCESS_PID=${server.pid ?? 'unavailable'}; ${jobLayoutDebug}`,
  );
};
const started = waitForPreview();
let browser;
let failed = false;
try {
  await started;
  process.stderr.write('MOTION_CANVAS_HTTP_PROBE_START\n');
  previewResourceProbes = await recordPreviewResourceProbes();
  process.stderr.write('MOTION_CANVAS_HTTP_PROBE_DONE\n');
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
} catch (error) {
  failed = true;
  const diagnostic = await jobFailureDebug();
  const debug = `MOTION_CANVAS_JOB_FAILURE_DEBUG ${JSON.stringify(diagnostic)}`;
  process.stderr.write(`${debug}\n`);
  throw new Error(`${error instanceof Error ? error.message : String(error)}; ${debug}`);
} finally {
  if (browser) await browser.close();
  server.kill();
  if (!failed) await rm(runtimeRoot, {recursive: true, force: true});
  else process.stderr.write(`MOTION_CANVAS_JOB_PRESERVED ${runtimeRoot}\n`);
}
