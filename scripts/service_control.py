"""Start/stop only processes verified to belong to this project checkout."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time

import psutil


def config_values(path):
    return dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines()
                if line and not line.startswith('#') and '=' in line)


def belongs_to_project(process, root, kind):
    try:
        cwd = Path(process.cwd()).resolve()
        command = process.cmdline()
        if kind == 'backend':
            return cwd == root / 'backend' and 'uvicorn' in command and 'main:app' in command
        return cwd == root / 'frontend' and any('vite' in part.replace('\\', '/').split('/') for part in command)
    except (psutil.Error, OSError):
        return False


def token(process, port):
    return {'pid': process.pid, 'created': process.create_time(), 'port': port}


def known_process(record, root, kind):
    try:
        process = psutil.Process(int(record['pid']))
        if abs(process.create_time() - float(record['created'])) > 0.01:
            return None  # PID was reused by a different process.
        return process if belongs_to_project(process, root, kind) else None
    except (KeyError, ValueError, psutil.Error):
        return None


def terminate_owned(process, root, kind):
    if not belongs_to_project(process, root, kind):
        raise RuntimeError('Refusing to stop an unrelated process.')
    children = process.children(recursive=True)
    for child in reversed(children):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    try:
        process.terminate()
    except psutil.NoSuchProcess:
        pass
    _, alive = psutil.wait_procs([process, *children], timeout=10)
    for child in alive:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass


def free_port(start, end):
    for port in range(start, end + 1):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                pass
    raise RuntimeError(f'No available port between {start} and {end}; no existing service was stopped.')


def find_existing(root, kind, state, preferred, allocate=True):
    process = known_process(state.get(kind, {}), root, kind)
    if process:
        return process, int(state[kind]['port'])
    # Adopt services from the old project-specific Windows script, but verify identity.
    pid_file = root / '.local' / f'{kind}.pid'
    if pid_file.exists():
        try:
            parent = psutil.Process(int(pid_file.read_text().strip()))
            candidates = [parent, *parent.children(recursive=True)]
            for candidate in reversed(candidates):
                if belongs_to_project(candidate, root, kind):
                    for connection in candidate.net_connections(kind='tcp'):
                        if connection.status == psutil.CONN_LISTEN and connection.laddr.ip == '127.0.0.1':
                            return candidate, connection.laddr.port
        except (ValueError, psutil.Error):
            pass
    return None, free_port(preferred, preferred + 29) if allocate else preferred


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'stop'))
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--python', required=True)
    parser.add_argument('--node', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    local = root / '.local'
    state_file = local / 'services.json'
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    if args.action == 'stop':
        for kind in ('backend', 'frontend'):
            if not known_process(state.get(kind, {}), root, kind):
                process, port = find_existing(root, kind, state, 8000 if kind == 'backend' else 5173, allocate=False)
                if process:
                    state[kind] = token(process, port)
        for kind, record in state.items():
            process = known_process(record, root, kind)
            if process:
                terminate_owned(process, root, kind)
                print(f'{kind}: arrete')
        state_file.write_text('{}', encoding='utf-8')
        return
    path = local / 'project.env'
    config = config_values(path)
    backend, backend_port = find_existing(root, 'backend', state, 8000)
    frontend, frontend_port = find_existing(root, 'frontend', state, 5173)
    if backend:
        try:
            inherited = backend.environ()
            if any(inherited.get(key) != config.get(key) for key in
                   ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'ANALYSIS_CACHE_DIR', 'PROPOS_CACHE_DIR', 'SAINT_LIVE_CACHE_DIR')):
                terminate_owned(backend, root, 'backend')
                backend = None
        except psutil.AccessDenied:
            raise RuntimeError('Cannot verify the project backend environment; stop it manually before restarting.')
    old_backend = config.get('PYTHON_API_URL')
    backend_url = f'http://127.0.0.1:{backend_port}'
    if frontend and old_backend and old_backend != backend_url:
        terminate_owned(frontend, root, 'frontend')
        frontend = None
    config.update({'PYTHON_API_URL': backend_url, 'PY_ANALYSIS_API_URL': backend_url,
                   'VITE_PYTHON_API_URL': backend_url,
                   'PFAS_FRONTEND_URL': f'http://127.0.0.1:{frontend_port}'})
    path.write_text(''.join(f'{key}={value}\n' for key, value in config.items()), encoding='utf-8')
    environment = os.environ.copy()
    environment.update(config)
    environment.update({'PFAS_PROJECT_ROOT': str(root), 'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1', 'MPLBACKEND': 'Agg'})
    specifications = {
        'backend': (backend, backend_port, root / 'backend', [args.python, '-X', 'utf8', '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(backend_port)]),
        'frontend': (frontend, frontend_port, root / 'frontend', [args.node, str(root / 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', str(frontend_port), '--strictPort']),
    }
    for kind, (existing, port, cwd, command) in specifications.items():
        if existing:
            state[kind] = token(existing, port)
            print(f'{kind}: processus du projet reutilise sur le port {port}')
        else:
            options = {'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
            with (local / f'{kind}.log').open('ab') as output, (local / f'{kind}-error.log').open('ab') as errors:
                child = subprocess.Popen(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                         stdout=output, stderr=errors, **options)
            state[kind] = token(psutil.Process(child.pid), port)
            print(f'{kind}: demarre sur le port {port}')
        temporary = state_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, indent=2), encoding='utf-8')
        temporary.replace(state_file)


if __name__ == '__main__':
    main()
