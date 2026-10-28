"""Build with the platform's existing proxy and CA; never print credentials."""
import os
import socket
import subprocess
from urllib.parse import urlsplit

args = ['docker', 'build', '--network', 'host']
for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY'):
    if os.environ.get(name):
        args += ['--build-arg', name]
hosts = {urlsplit(os.environ[name]).hostname for name in ('HTTP_PROXY', 'HTTPS_PROXY') if os.environ.get(name)}
for host in sorted(hosts):
    args += ['--add-host', f'{host}:{socket.gethostbyname(host)}']
if os.environ.get('SSL_CERT_FILE'):
    args += ['--secret', 'id=cloud_ca,src=' + os.environ['SSL_CERT_FILE']]
args += ['-t', 'branch-to-head-office-management-platform-web', '.']
subprocess.run(args, check=True, env={**os.environ, 'DOCKER_CONFIG': '/tmp/shiplens-docker'})
