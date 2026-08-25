/** Build an explicit launcher for the root project's local Vite binary. */
const quoteForCmd = value => `"${String(value).replace(/"/g, '""')}"`;

export const buildNpmServeLaunchSpec = ({platform = process.platform, comSpec, runtimeRoot, root, port}) => {
  // Vite's CLI contract is `vite [root]`: runtimeRoot is the project root for
  // this isolated render job, not an entry-file argument. Its public/ folder
  // supplies the job-specific motion_input.json requested by the scene.
  const configPath = `${runtimeRoot}/vite.config.ts`;
  const viteBin = `${root}/node_modules/.bin/vite`;
  const viteArgs = ['--host', '127.0.0.1', '--config', configPath, '--port', String(port), '--strictPort'];
  if (platform === 'win32') {
    // npm.cmd is a batch file. Node cannot execute it directly with shell:false;
    // cmd.exe is intentionally the narrow launcher, with autorun disabled.
    const command = comSpec || process.env.ComSpec || 'C:\\Windows\\System32\\cmd.exe';
    const commandLine = `call ${quoteForCmd(`${viteBin}.cmd`)} --host 127.0.0.1 --config ${quoteForCmd(configPath)} --port ${Number(port)} --strictPort`;
    return {command, args: ['/d', '/s', '/c', commandLine], shell: false};
  }
  return {command: viteBin, args: viteArgs, shell: false};
};
