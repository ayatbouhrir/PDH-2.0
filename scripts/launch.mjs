import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const windows = process.platform === 'win32';
const command = windows ? 'powershell.exe' : 'sh';
const args = windows
  ? ['-NoProfile', '-File', path.join(root, 'scripts', 'bootstrap-windows.ps1')]
  : [path.join(root, 'run.sh')];
const child = spawn(command, [...args, ...process.argv.slice(2)], {
  cwd: root,
  stdio: 'inherit',
  windowsHide: true,
});
child.on('error', (error) => {
  console.error(`Impossible de lancer le projet : ${error.message}`);
  process.exitCode = 1;
});
child.on('exit', (code) => { process.exitCode = code ?? 1; });
