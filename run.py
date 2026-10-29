#!/usr/bin/env python3
"""Prepare and run DAE-PFAS on Windows, macOS, and Linux without Docker.

Use run.cmd (Windows) or sh run.sh (macOS/Linux) even when Python is missing.
All application runtimes and PostgreSQL data are private to this checkout.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile

ROOT = Path(__file__).resolve().parent
NODE_VERSION = '24.19.0'
PG_VERSION = '18.6'
UV_VERSION = '0.12.19'
SOURCE_URL = 'https://pdh.cnrs.fr/download/full.csv'
USER_AGENT = 'DAE-PFAS-local-launcher/1.0'


class SetupError(RuntimeError):
    pass


def read_env(path):
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            name, value = line.split('=', 1)
            result[name.strip()] = value.strip().strip('"').strip("'")
    return result


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_text(url):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read().decode('utf-8')


def download(url, destination, *, expected_hash=None, limit=None):
    """Stream downloads; retain complete files only and cap ranged samples."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + '.part')
    for attempt in range(3):
        try:
            headers = {'User-Agent': USER_AGENT}
            if limit:
                headers['Range'] = f'bytes=0-{limit - 1}'
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response, part.open('wb') as output:
                count = 0
                expected_size = int(response.headers.get('Content-Length', 0))
                last_message = time.monotonic()
                while True:
                    remaining = min(1024 * 1024, limit - count) if limit else 1024 * 1024
                    if remaining <= 0:
                        break
                    chunk = response.read(remaining)
                    if not chunk:
                        break
                    output.write(chunk)
                    count += len(chunk)
                    if time.monotonic() - last_message > 10:
                        print(f'  {destination.name}: {count / 1024**2:.0f} Mo telecharges', flush=True)
                        last_message = time.monotonic()
                target_size = min(expected_size, limit) if limit and expected_size else expected_size
                if target_size and count != target_size:
                    raise SetupError(f'Telechargement incomplet: {destination.name} ({count}/{target_size} octets).')
                if not count:
                    raise SetupError(f'Telechargement vide: {destination.name}.')
            if expected_hash and sha256(part).lower() != expected_hash.lower():
                raise SetupError(f'Verification SHA256 echouee: {destination.name}.')
            part.replace(destination)
            return
        except (OSError, urllib.error.URLError, SetupError) as exc:
            if attempt == 2:
                raise SetupError(f'Impossible de telecharger {url}: {exc}') from exc
            time.sleep(attempt + 1)


def extract_archive(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                # Reject backslashes too: Windows treats them as path separators.
                name = member.filename.replace('\\', '/')
                target = (destination / name).resolve()
                if not target.is_relative_to(destination.resolve()) or re.match(r'^[A-Za-z]:', name):
                    raise SetupError('Chemin interdit dans une archive telechargee.')
            source.extractall(destination)
    else:
        with tarfile.open(archive) as source:
            source.extractall(destination, filter='data')


def system_target(system=None, machine=None):
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(machine)
    name = {'Windows': 'win', 'Darwin': 'darwin', 'Linux': 'linux'}.get(system)
    if not name or not arch:
        raise SetupError(f'Plateforme non prise en charge: {system}/{machine}. Systeme 64 bits requis.')
    if name == 'linux' and Path('/etc/alpine-release').exists():
        raise SetupError('PyTorch requiert une distribution Linux glibc; Alpine/musl non pris en charge.')
    return name, arch


def port_available(port):
    with socket.socket() as server:
        try:
            server.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def choose_port(preferred, upper):
    for port in range(preferred, upper + 1):
        if port_available(port):
            return port
    raise SetupError(f'Aucun port libre entre {preferred} et {upper}. Aucun processus existant arrete.')


@contextmanager
def setup_lock(local):
    """OS-managed lock: no stale lock after a crash, and no concurrent installs."""
    local.mkdir(parents=True, exist_ok=True)
    with (local / 'launcher.lock').open('a+b') as lock:
        lock.seek(0)
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SetupError('Une autre installation est en cours pour ce projet.') from exc
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class Launcher:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.local = self.root / '.local'
        self.tools = self.local / 'tools'
        if (not self.local.resolve().is_relative_to(self.root)
                or not (self.local / 'postgres').resolve().is_relative_to(self.local.resolve())):
            raise SetupError('Le dossier prive PostgreSQL doit rester dans le projet; lien vers un emplacement exterieur refuse.')
        self.system, self.arch = system_target()
        self.environment = os.environ.copy()
        self.environment.update({'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1', 'MPLBACKEND': 'Agg',
                                 'UV_LINK_MODE': 'copy', 'UV_HTTP_TIMEOUT': '120'})
        # Do not inherit database settings for unrelated work.
        for key in list(self.environment):
            if key.startswith('PG') or key.startswith('DB_'):
                self.environment.pop(key)
        self.python = None
        self.node = None
        self.npm_cli = None
        self.uv = None
        self.pg = None
        self.config = {}

    def command(self, args, *, cwd=None, capture=False, check=True, timeout=None, no_window=False, file_output=False):
        argv = [str(arg) for arg in args]
        process_options = {'creationflags': subprocess.CREATE_NO_WINDOW} if no_window and os.name == 'nt' else {}
        self.local.mkdir(parents=True, exist_ok=True)
        with (self.local / 'setup.log').open('a', encoding='utf-8') as log:
            log.write('\n$ ' + subprocess.list2cmdline(argv) + '\n')
            log.flush()
            if file_output:
                # pg_ctl can pass inherited pipe handles to the Windows server.
                # Wait for pg_ctl itself, without waiting for a daemon-held pipe EOF.
                position = log.tell()
                result = subprocess.run(argv, cwd=cwd or self.root, env=self.environment,
                                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                        timeout=timeout, **process_options)
                log.flush()
                with (self.local / 'setup.log').open(encoding='utf-8', errors='replace') as reader:
                    reader.seek(position)
                    output = reader.read()
                result = subprocess.CompletedProcess(argv, result.returncode, output)
                if not capture:
                    print(output, end='', flush=True)
            elif capture or timeout is not None:
                result = subprocess.run(argv, cwd=cwd or self.root, env=self.environment,
                                        text=True, encoding='utf-8', errors='replace',
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, **process_options)
                log.write(result.stdout or '')
                if not capture:
                    print(result.stdout or '', end='', flush=True)
            else:
                # Keep installation/build progress visible and retain the same output for diagnosis.
                child = subprocess.Popen(argv, cwd=cwd or self.root, env=self.environment,
                                         text=True, encoding='utf-8', errors='replace',
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **process_options)
                tail = []
                for line in child.stdout:
                    print(line, end='', flush=True)
                    log.write(line)
                    log.flush()
                    tail = (tail + [line])[-30:]
                child.stdout.close()
                result = subprocess.CompletedProcess(argv, child.wait(), ''.join(tail))
        if check and result.returncode:
            detail = (result.stdout or '')[-1600:]
            raise SetupError(f'Commande echouee ({Path(str(args[0])).name}, code {result.returncode}). {detail}')
        return result

    def ensure_uv(self):
        existing = shutil.which('uv')
        executable = 'uv.exe' if self.system == 'win' else 'uv'
        local_uv = self.tools / 'uv' / executable
        if existing or local_uv.exists():
            self.uv = Path(existing) if existing else local_uv
            return
        target = ('x86_64' if self.arch == 'x64' else 'aarch64') + {
            'win': '-pc-windows-msvc', 'darwin': '-apple-darwin', 'linux': '-unknown-linux-gnu'}[self.system]
        archive_name = f'uv-{target}.' + ('zip' if self.system == 'win' else 'tar.gz')
        base = f'https://github.com/astral-sh/uv/releases/download/{UV_VERSION}'
        expected = fetch_text(f'{base}/{archive_name}.sha256').split()[0]
        archive = self.tools / 'downloads' / archive_name
        print('Installation locale de uv...', flush=True)
        download(f'{base}/{archive_name}', archive, expected_hash=expected)
        extract_archive(archive, local_uv.parent)
        candidate = local_uv if local_uv.exists() else local_uv.parent / f'uv-{target}' / executable
        if not candidate.exists():
            raise SetupError('Archive uv incomplete.')
        candidate.chmod(candidate.stat().st_mode | 0o111)
        self.uv = candidate

    def ensure_node(self):
        existing = shutil.which('node')
        if existing:
            version = self.command([existing, '--version'], capture=True).stdout.strip()
            if re.match(r'^v(22|24)\.', version):
                npm = shutil.which('npm')
                candidates = [Path(existing).resolve().parent / 'node_modules/npm/bin/npm-cli.js',
                              Path(existing).resolve().parent.parent / 'lib/node_modules/npm/bin/npm-cli.js']
                if npm:
                    candidates.extend([Path(npm).resolve(), Path(npm).parent / 'node_modules/npm/bin/npm-cli.js'])
                for candidate in candidates:
                    if candidate.is_file() and candidate.suffix == '.js':
                        self.node, self.npm_cli = Path(existing), candidate
                        break
        if not self.node:
            stem = f'node-v{NODE_VERSION}-{self.system}-{self.arch}'
            name = stem + ('.zip' if self.system == 'win' else '.tar.gz')
            base = f'https://nodejs.org/dist/v{NODE_VERSION}'
            node_root = self.tools / 'node' / stem
            self.node = node_root / ('node.exe' if self.system == 'win' else 'bin/node')
            self.npm_cli = node_root / ('node_modules/npm/bin/npm-cli.js' if self.system == 'win' else 'lib/node_modules/npm/bin/npm-cli.js')
            if not self.node.exists() or not self.npm_cli.exists():
                sums = fetch_text(f'{base}/SHASUMS256.txt')
                expected = next((line.split()[0] for line in sums.splitlines() if line.split()[-1] == name), None)
                if not expected:
                    raise SetupError(f'Checksum officiel Node.js introuvable pour {name}.')
                archive = self.tools / 'downloads' / name
                print(f'Installation locale de Node.js {NODE_VERSION}...', flush=True)
                download(f'{base}/{name}', archive, expected_hash=expected)
                extract_archive(archive, node_root.parent)
        self.environment['PATH'] = str(self.node.parent) + os.pathsep + self.environment.get('PATH', '')
        print(f'Node.js: {self.command([self.node, "--version"], capture=True).stdout.strip()}', flush=True)

    def ensure_python_packages(self, repair=False):
        venv = self.root / '.venv'
        executable = Path('Scripts/python.exe' if self.system == 'win' else 'bin/python')
        if venv.exists() and not (venv / executable).exists():
            # A copied Windows venv cannot run on macOS/Linux, or vice versa.
            venv = self.local / f'venv-{self.system}-{self.arch}'
        self.python = venv / executable
        if self.python.exists():
            version = self.command([self.python, '-c', 'import sys; print(sys.version_info[:2])'], capture=True, check=False)
            if version.returncode or '(3, 12)' not in version.stdout:
                venv = self.local / f'venv-312-{self.system}-{self.arch}'
                self.python = venv / executable
        if not self.python.exists():
            self.command([self.uv, 'venv', '--python', '3.12', venv])
        requirements = self.root / 'backend/requirements-dev.txt'
        fingerprint = hashlib.sha256(requirements.read_bytes() + (self.root / 'backend/requirements.txt').read_bytes()
                                     + str(self.python).encode()).hexdigest()
        stamp = self.local / 'python-dependencies.json'
        installed = json.loads(stamp.read_text()) if stamp.exists() else {}
        probe = self.command([self.uv, 'pip', 'check', '--python', self.python], capture=True, check=False)
        if repair or installed.get('fingerprint') != fingerprint or probe.returncode:
            print('Installation des dependances Python (PyTorch CPU, analyses, tests)...', flush=True)
            if self.system != 'darwin':
                self.command([self.uv, 'pip', 'install', '--python', self.python, 'torch>=2.6,<3',
                              '--index-url', 'https://download.pytorch.org/whl/cpu', *(['--reinstall'] if repair else [])])
            elif self.arch == 'x64':
                print('Mac Intel: profil de compatibilite PyTorch 2.2.2 / NumPy 1.26 (anciens binaires officiels).', flush=True)
            reinstall = []
            if repair:
                # Preserve the CPU-only torch already installed from its specific index.
                installed_packages = json.loads(self.command([self.uv, 'pip', 'list', '--python', self.python, '--format', 'json'], capture=True).stdout)
                for package in installed_packages:
                    if package['name'] != 'torch' or self.system == 'darwin':
                        reinstall.extend(['--reinstall-package', package['name']])
            self.command([self.uv, 'pip', 'install', '--python', self.python, '-r', requirements, *reinstall])
            self.command([self.uv, 'pip', 'check', '--python', self.python])
            write_json(stamp, {'fingerprint': fingerprint})
        write_json(self.local / 'runtime.json', {'python': str(self.python), 'node': str(self.node)})

    def ensure_frontend_packages(self, repair=False):
        app = self.root / 'frontend'
        fingerprint = sha256(app / 'package-lock.json')
        stamp = self.local / 'node-dependencies.json'
        installed = json.loads(stamp.read_text()) if stamp.exists() else {}
        ready = (app / 'node_modules/vite/bin/vite.js').exists()
        if repair or not ready or installed.get('fingerprint') != fingerprint:
            print('Installation des dependances du site...', flush=True)
            # npm ci replaces node_modules. Stop only our verified processes before doing so.
            print(self.service_command('stop').stdout, end='', flush=True)
            self.command([self.node, self.npm_cli, 'ci', '--no-fund'], cwd=app)
            write_json(stamp, {'fingerprint': fingerprint})

    def pg_candidates(self):
        paths = []
        if os.environ.get('PFAS_PG_BIN'):
            paths.append(Path(os.environ['PFAS_PG_BIN']))
        executable = shutil.which('pg_ctl')
        if executable:
            paths.append(Path(executable).resolve().parent)
        if self.system == 'win':
            program_files = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'PostgreSQL'
            paths.extend(sorted(program_files.glob('*/bin'), reverse=True))
        else:
            for pattern in ('/usr/lib/postgresql/*/bin', '/usr/pgsql-*/bin',
                            '/opt/homebrew/opt/postgresql*/bin', '/usr/local/opt/postgresql*/bin',
                            '/Applications/Postgres.app/Contents/Versions/*/bin'):
                import glob
                paths.extend(Path(p) for p in sorted(glob.glob(pattern), reverse=True))
        paths.append(self.tools / 'postgres' / 'bin')
        paths.append(self.tools / 'postgres' / 'pgsql' / 'bin')
        return list(dict.fromkeys(paths))

    def ensure_postgres(self):
        data = self.local / 'postgres'
        major = (data / 'PG_VERSION').read_text().strip() if (data / 'PG_VERSION').exists() else None
        suffix = '.exe' if self.system == 'win' else ''
        for candidate in self.pg_candidates():
            ctl = candidate / f'pg_ctl{suffix}'
            if ctl.is_file() and (candidate / f'initdb{suffix}').is_file():
                version = self.command([ctl, '--version'], capture=True, check=False)
                match = re.search(r'PostgreSQL\)? (\d+)', version.stdout)
                if not version.returncode and match and ((major and match[1] == major) or (not major and int(match[1]) >= 16)):
                    self.pg = candidate
                    break
        if not self.pg:
            if major and major != PG_VERSION.split('.')[0]:
                raise SetupError(f'Cette base requiert PostgreSQL {major}. Installez ses binaires et indiquez PFAS_PG_BIN; aucune migration automatique des donnees.')
            print('Installation des binaires PostgreSQL reserves au projet...', flush=True)
            if self.system == 'win':
                if self.arch != 'x64':
                    raise SetupError('PostgreSQL Windows ARM64: installez des binaires compatibles et indiquez PFAS_PG_BIN.')
                name = f'postgresql-{PG_VERSION}-5-windows-x64-binaries.zip'
                archive = self.tools / 'downloads' / name
                download(f'https://get.enterprisedb.com/postgresql/{name}', archive)
                extract_archive(archive, self.tools / 'postgres')
                self.pg = self.tools / 'postgres' / 'pgsql' / 'bin'
                probe = self.command([self.pg / 'pg_ctl.exe', '--version'], capture=True, check=False)
                if probe.returncode & 0xFFFFFFFF == 0xC0000135:
                    self.ensure_windows_runtime()
                    self.command([self.pg / 'pg_ctl.exe', '--version'], capture=True)
                elif probe.returncode:
                    raise SetupError(f'Les binaires PostgreSQL ne peuvent pas demarrer (code {probe.returncode}). Verifiez Windows x64 et le journal de votre antivirus.')
            else:
                self.build_postgres()
        if not (self.pg / f'pg_ctl{suffix}').exists():
            raise SetupError('Binaires PostgreSQL incomplets; consultez .local/setup.log.')
        self.environment['PATH'] = str(self.pg) + os.pathsep + self.environment['PATH']

    def ensure_windows_runtime(self):
        print('Installation du runtime Microsoft Visual C++ manquant (une autorisation Windows peut etre demandee)...', flush=True)
        installer = self.tools / 'downloads' / 'vc_redist.x64.exe'
        download('https://aka.ms/vc14/vc_redist.x64.exe', installer)
        verify = self.tools / 'verify-microsoft.ps1'
        verify.write_text('''param([string]$Installer)
$signature = Get-AuthenticodeSignature -LiteralPath $Installer
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { exit 1 }
''', encoding='utf-8')
        self.command(['powershell.exe', '-NoProfile', '-File', verify, '-Installer', installer], capture=True)
        try:
            result = self.command([installer, '/install', '/quiet', '/norestart'], check=False)
        except OSError as exc:
            if getattr(exc, 'winerror', None) != 740:
                raise
            elevated = self.tools / 'install-microsoft-runtime.ps1'
            elevated.write_text('''param([string]$Installer)
$ErrorActionPreference = 'Stop'
$process = Start-Process -FilePath $Installer -ArgumentList '/install','/quiet','/norestart' -Verb RunAs -WindowStyle Hidden -Wait -PassThru
exit $process.ExitCode
''', encoding='utf-8')
            result = self.command(['powershell.exe', '-NoProfile', '-File', elevated, '-Installer', installer], check=False)
        if result.returncode not in (0, 3010, 1638):
            raise SetupError(f'Installation Microsoft Visual C++ refusee ou echouee (code {result.returncode}). Relancez apres installation du runtime officiel.')
        if result.returncode == 3010:
            print('Microsoft Visual C++ demande un redemarrage de Windows; aucun redemarrage automatique.', flush=True)

    def build_postgres(self):
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            raise SetupError('Lancez le projet avec un utilisateur normal. PostgreSQL refuse de fonctionner en root.')
        missing = [name for name in ('cc', 'make', 'bison', 'flex') if not shutil.which(name, path=self.environment['PATH'])]
        if missing:
            print('Outils de compilation manquants: ' + ', '.join(missing), flush=True)
            if self.system == 'darwin':
                brew = shutil.which('brew')
                if not brew:
                    raise SetupError('Installez les outils Apple (xcode-select --install) et Homebrew, puis relancez sh run.sh. Aucune base existante modifiee.')
                self.command([brew, 'install', 'bison', 'flex', 'make'])
                prefix = self.command([brew, '--prefix'], capture=True).stdout.strip()
                self.environment['PATH'] = os.pathsep.join([f'{prefix}/opt/bison/bin', f'{prefix}/opt/flex/bin', self.environment['PATH']])
            else:
                sudo = [] if (hasattr(os, 'geteuid') and os.geteuid() == 0) else ['sudo']
                if sudo and not shutil.which('sudo'):
                    raise SetupError('Outils cc/make/bison/flex requis. Demandez leur installation a votre administrateur, puis relancez.')
                if shutil.which('apt-get'):
                    self.command(sudo + ['apt-get', 'update'])
                    self.command(sudo + ['apt-get', 'install', '-y', 'build-essential', 'bison', 'flex', 'pkg-config'])
                elif shutil.which('dnf'):
                    self.command(sudo + ['dnf', 'install', '-y', 'gcc', 'make', 'bison', 'flex', 'pkgconf-pkg-config'])
                elif shutil.which('pacman'):
                    self.command(sudo + ['pacman', '-S', '--needed', '--noconfirm', 'gcc', 'make', 'bison', 'flex', 'pkgconf'])
                else:
                    raise SetupError('Gestionnaire systeme non pris en charge. Installez cc/make/bison/flex ou renseignez PFAS_PG_BIN.')
        name = f'postgresql-{PG_VERSION}.tar.gz'
        base = f'https://ftp.postgresql.org/pub/source/v{PG_VERSION}'
        expected = fetch_text(f'{base}/{name}.sha256').split()[0]
        archive = self.tools / 'downloads' / name
        download(f'{base}/{name}', archive, expected_hash=expected)
        build = self.tools / 'build'
        extract_archive(archive, build)
        source = build / f'postgresql-{PG_VERSION}'
        prefix = self.tools / 'postgres'
        self.command(['sh', './configure', f'--prefix={prefix}', '--without-readline', '--without-zlib', '--without-icu'], cwd=source)
        self.command(['make', f'-j{min(os.cpu_count() or 2, 8)}'], cwd=source)
        self.command(['make', 'install'], cwd=source)
        self.pg = prefix / 'bin'

    def pg_command(self, name, *args, **kwargs):
        suffix = '.exe' if self.system == 'win' else ''
        return self.command([self.pg / (name + suffix), *args], no_window=self.system == 'win',
                            file_output=name == 'pg_ctl' and 'start' in args, **kwargs)

    def save_config(self):
        path = self.local / 'project.env'
        path.write_text(''.join(f'{k}={v}\n' for k, v in self.config.items()), encoding='utf-8')
        if os.name != 'nt':
            path.chmod(0o600)
        self.environment.update(self.config)

    def ensure_database(self):
        data = self.local / 'postgres'
        existing = (data / 'PG_VERSION').exists()
        config_path = self.local / 'project.env'
        self.config = read_env(config_path)
        if not self.config:
            # Adopt the separate instance created by the previous project setup.
            previous = read_env(self.root / 'frontend/.env') if existing else {}
            if existing and not (previous.get('DB_HOST') == '127.0.0.1' and previous.get('DB_USER') == 'pfas_app'
                                 and previous.get('DB_NAME') == 'dae_pfas_local' and previous.get('DB_PORT') == '5434'):
                raise SetupError('Base locale existante sans configuration reconnue. Refus de reinitialiser ou de remplacer ses identifiants.')
            self.config = previous or {'DB_HOST': '127.0.0.1', 'DB_PORT': str(choose_port(5434, 5499)),
                                       'DB_NAME': 'dae_pfas_local', 'DB_USER': 'pfas_app',
                                       'DB_PASSWORD': secrets.token_hex(24)}
        if (self.config.get('DB_HOST') != '127.0.0.1' or self.config.get('DB_USER') != 'pfas_app'
                or self.config.get('DB_NAME') != 'dae_pfas_local' or not 5434 <= int(self.config.get('DB_PORT', '0')) <= 5499):
            raise SetupError('Configuration non locale refusee. Le lanceur ne modifie que sa base dediee.')
        self.config.update({'PFAS_PRECOMPUTED_SAINT': 'false', 'PFAS_PRESERVED_CACHE': 'false',
                            'ANALYSIS_CACHE_VERSION': self.config.get('ANALYSIS_CACHE_VERSION', 'local-' + secrets.token_hex(8)),
                            'ANALYSIS_CACHE_DIR': str(self.local / 'cache' / 'analysis'),
                            'PROPOS_CACHE_DIR': str(self.local / 'cache' / 'propos'),
                            'SAINT_LIVE_CACHE_DIR': str(self.local / 'cache' / 'saint')})
        self.save_config()
        if not existing:
            if not port_available(int(self.config['DB_PORT'])):
                self.config['DB_PORT'] = str(choose_port(5434, 5499))
                self.save_config()
            password_file = self.local / 'init-password.tmp'
            try:
                password_file.write_text(self.config['DB_PASSWORD'], encoding='utf-8')
                if os.name != 'nt':
                    password_file.chmod(0o600)
                self.pg_command('initdb', '-D', data, '-U', self.config['DB_USER'], '--auth=scram-sha-256',
                                f'--pwfile={password_file}', '--encoding=UTF8', '--locale=C')
            finally:
                password_file.unlink(missing_ok=True)
            with (data / 'postgresql.conf').open('a', encoding='utf-8') as output:
                output.write(f"\nlisten_addresses = '127.0.0.1'\nport = {self.config['DB_PORT']}\n")
        status = self.pg_command('pg_ctl', '-D', data, 'status', capture=True, check=False)
        if status.returncode:
            if not port_available(int(self.config['DB_PORT'])):
                raise SetupError(f"Port PostgreSQL {self.config['DB_PORT']} occupe. Aucun service existant arrete; consultez .local/postgres.log.")
            self.pg_command('pg_ctl', '-D', data, '-l', self.local / 'postgres.log', '-w', 'start')
        # Always inspect through this instance's own password; never use the user's PG* settings.
        self.environment['PGPASSWORD'] = self.config['DB_PASSWORD']
        try:
            check = self.pg_command('psql', '-h', '127.0.0.1', '-p', self.config['DB_PORT'], '-U', self.config['DB_USER'],
                                    '-w', '-d', 'postgres', '-tAc', "SELECT 1 FROM pg_database WHERE datname='dae_pfas_local'", capture=True)
            if check.stdout.strip() != '1':
                self.pg_command('createdb', '-h', '127.0.0.1', '-p', self.config['DB_PORT'], '-U', self.config['DB_USER'], '-w', 'dae_pfas_local')
        finally:
            self.environment.pop('PGPASSWORD', None)
        print(f"PostgreSQL prive: 127.0.0.1:{self.config['DB_PORT']} / dae_pfas_local", flush=True)

    def sql(self, statement):
        self.environment['PGPASSWORD'] = self.config['DB_PASSWORD']
        try:
            return self.pg_command('psql', '-h', '127.0.0.1', '-p', self.config['DB_PORT'], '-U', self.config['DB_USER'],
                                   '-w', '-d', self.config['DB_NAME'], '-tAc', statement, capture=True).stdout.strip()
        finally:
            self.environment.pop('PGPASSWORD', None)

    def ensure_data(self, mode, csv_path=None):
        tables = self.sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='pfas_points'")
        if tables == '1':
            manifest = self.local / 'data-import.json'
            previous = json.loads(manifest.read_text()) if manifest.exists() else {}
            if csv_path or (mode == 'full' and previous.get('isPartialExtract')):
                raise SetupError('Une base peuplee existe deja; les donnees ne seront pas remplacees. Pour un autre CSV ou le fichier complet, utilisez une copie neuve du projet sans .local/.venv/node_modules.')
            print('Donnees existantes conservees; aucun reimport ni remplacement.', flush=True)
        elif mode != 'none' or csv_path:
            if csv_path:
                source = Path(csv_path).expanduser().resolve()
                if not source.is_file():
                    raise SetupError(f'CSV introuvable: {source}')
            else:
                source = self.local / ('full.csv' if mode == 'full' else 'pfas-sample.csv')
                if not source.exists():
                    print('Telechargement du fichier COMPLET (environ 3,5 Go)...' if mode == 'full'
                          else 'Telechargement d\'un EXTRAIT reel PFAS (8 Mo)...', flush=True)
                    download(SOURCE_URL, source, limit=8 * 1024**2 if mode == 'sample' else None)
            args = [self.python, '-X', 'utf8', self.root / 'scripts/import_local_data.py', source,
                    '--config', self.local / 'project.env']
            if not csv_path and mode == 'sample':
                args.append('--partial')
            self.command(args)
        if self.sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='pfas_points'") == '1':
            self.command([self.python, '-X', 'utf8', self.root / 'scripts/index_local_nuts.py',
                          '--config', self.local / 'project.env'])

    def service_command(self, action):
        return self.command([self.python, self.root / 'scripts/service_control.py', action, '--root', self.root,
                             '--python', self.python, '--node', self.node], capture=True)

    def start_services(self, open_browser=True):
        if self.sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='pfas_points'") != '1':
            raise SetupError('Base vide. Relancez avec --data sample, --data full ou --csv chemin/mesures.csv.')
        # service_control chooses available ports or reuses only verified project processes.
        result = self.service_command('start')
        print(result.stdout, end='', flush=True)
        self.config = read_env(self.local / 'project.env')
        self.environment.update(self.config)
        frontend = self.config['PFAS_FRONTEND_URL']
        backend = self.config['PYTHON_API_URL']
        self.wait_for(backend + '/health', 'Service Python', timeout=300)
        self.wait_for(frontend + '/api/info', 'Site et connexion PostgreSQL', timeout=90)
        print(f'\nProjet pret: {frontend}/\nAPI: {backend}/docs', flush=True)
        print('Donnees et configuration conservees dans .local. Arret: --stop', flush=True)
        if open_browser:
            webbrowser.open(frontend)
        return frontend, backend

    def wait_for(self, url, label, timeout):
        deadline = time.monotonic() + timeout
        last = ''
        next_message = time.monotonic()
        while time.monotonic() < deadline:
            try:
                request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
                with urllib.request.urlopen(request, timeout=4) as response:
                    data = json.load(response)
                    if response.status == 200 and ('health' not in url or data.get('status') == 'ok'):
                        print(f'{label}: OK', flush=True)
                        return
            except (OSError, ValueError, urllib.error.URLError) as exc:
                last = str(exc)
            if time.monotonic() >= next_message:
                print(f'{label}: demarrage en cours... (journaux dans .local)', flush=True)
                next_message = time.monotonic() + 15
            time.sleep(1)
        raise SetupError(f'{label} indisponible: {last}. Consultez .local/backend-error.log et .local/frontend-error.log.')

    def checks(self):
        for task in ('check', 'build'):
            self.command([self.node, self.npm_cli, 'run', task], cwd=self.root / 'frontend')

    def stop(self):
        runtime_file = self.local / 'runtime.json'
        if runtime_file.exists():
            runtime = json.loads(runtime_file.read_text())
            self.python, self.node = Path(runtime['python']), Path(runtime['node'])
            print(self.service_command('stop').stdout, end='')
        else:
            print('Aucun service gere par ce lanceur.')
        if (self.local / 'postgres/PG_VERSION').exists():
            self.ensure_postgres()
            self.pg_command('pg_ctl', '-D', self.local / 'postgres', '-m', 'fast', '-w', 'stop', check=False)

    def doctor(self):
        print(f'Systeme: {platform.system()} / {platform.machine()}\nProjet: {self.root}')
        for name in ('uv', 'node', 'python3', 'python', 'pg_ctl', 'cc', 'make'):
            print(f'{name}: {shutil.which(name) or "absent du PATH"}')
        for port in (5432, 5433, 5434, 5173, 8000):
            print(f'Port {port}: {"libre" if port_available(port) else "occupe (ne sera pas arrete)"}')
        print('Configuration locale:', 'presente' if (self.local / 'project.env').exists() else 'a creer')
        print('Docker: non requis. Aucune installation ou modification effectuee par --doctor.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup-only', action='store_true', help='Installer et preparer sans lancer le site.')
    parser.add_argument('--data', choices=('sample', 'full', 'none'), default='sample', help='Extrait reel par defaut; full telecharge environ 3,5 Go.')
    parser.add_argument('--csv', help='Importer ce fichier CSV PDH dans la base vide du projet.')
    parser.add_argument('--repair', action='store_true', help='Reinstaller les dependances; conserver les donnees et les identifiants.')
    parser.add_argument('--check', action='store_true', help='Verifier les types et compiler le site.')
    parser.add_argument('--test', action='store_true', help='Lancer aussi les tests fonctionnels sur le jeu de reference.')
    parser.add_argument('--no-open', action='store_true', help='Ne pas ouvrir le navigateur.')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--stop', action='store_true', help='Arreter uniquement les services et la base dedies au projet.')
    group.add_argument('--doctor', action='store_true', help='Afficher le diagnostic sans installer ni modifier.')
    args = parser.parse_args(argv)
    launcher = Launcher()
    if args.doctor:
        launcher.doctor()
        return 0
    if sys.version_info < (3, 12):
        raise SetupError('Python 3.12 requis: utilisez run.cmd ou sh run.sh pour son installation automatique.')
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        raise SetupError('Utilisez un compte normal, sans sudo pour lancer le projet. sudo ne sera utilise que pour des outils systeme manquants.')
    with setup_lock(launcher.local):
        if args.stop:
            launcher.stop()
            return 0
        launcher.ensure_uv()
        launcher.ensure_node()
        launcher.ensure_python_packages(args.repair)
        launcher.ensure_frontend_packages(args.repair)
        launcher.ensure_postgres()
        launcher.ensure_database()
        launcher.ensure_data(args.data, args.csv)
        if args.check:
            launcher.checks()
        if not args.setup_only:
            frontend, backend = launcher.start_services(not args.no_open)
            if args.test:
                launcher.command([launcher.python, launcher.root / 'scripts/test_local.py',
                                  '--frontend-url', frontend, '--backend-url', backend])
        elif args.test:
            raise SetupError('--test requiert le demarrage des services; retirez --setup-only.')
    return 0


if __name__ == '__main__':
    # Windows redirected output can default to cp1252, while npm emits Unicode.
    # Configure the launcher itself, not only its child-process environment.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nInterrompu. Les donnees sont conservees; relancez la meme commande pour reprendre.', file=sys.stderr)
        raise SystemExit(130)
    except (SetupError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'\nERREUR: {exc}\nLes bases existantes ne sont pas reinitialisees. Relancez avec --doctor pour le diagnostic.', file=sys.stderr)
        raise SystemExit(1)
