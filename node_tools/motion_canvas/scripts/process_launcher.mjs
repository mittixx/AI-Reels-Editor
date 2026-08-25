/** Build an explicit, shell-free npm launcher for the Vite preview process. */
const quoteForCmd = value => `"${String(value).replace(/"/g, '""')}"`;

export const buildNpmServeLaunchSpec = ({platform = process.platform, comSpec, runtimeRoot, port}) => {
  // Vite's CLI contract is `vite [root]`: runtimeRoot is the project root for
  // this isolated render job, not an entry-file argument. Its public/ folder
  // supplies the job-specific motion_input.json requested by the scene.
  const npmArgs = ['run', 'serve', '--', runtimeRoot, '--port', String(port), '--strictPort'];
  if (platform === 'win32') {
    // npm.cmd is a batch file. Node cannot execute it directly with shell:false;
    // cmd.exe is intentionally the narrow launcher, with autorun disabled.
    const command = comSpec || process.env.ComSpec || 'C:\\Windows\\System32\\cmd.exe';
    const commandLine = `npm.cmd run serve -- ${quoteForCmd(runtimeRoot)} --port ${Number(port)} --strictPort`;
    return {command, args: ['/d', '/s', '/c', commandLine], shell: false};
  }
  return {command: 'npm', args: npmArgs, shell: false};
};
