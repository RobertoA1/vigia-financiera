"""Run four real n8n workflows against a controlled HTTP service; no real emails.

Requires the pinned n8n CLI (N8N_BIN, default n8n) and node on PATH. Uses an
isolated temporary n8n database, credentials and random local ports. PostgreSQL,
OpenAI, VirusTotal and SMTP are NOT exercised by this integration smoke test.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    folder = Path(__file__).resolve().parent
    executable = shutil.which(os.environ.get('N8N_BIN', 'n8n'))
    if not executable:
        raise SystemExit('Install n8n==2.44.4 and set N8N_BIN to its executable')
    version = subprocess.check_output([executable, '--version'], text=True).strip()
    if version != '2.44.4':
        raise SystemExit(f'Expected n8n 2.44.4, got {version}')
    key = secrets.token_urlsafe(40)
    state = {'events': {}, 'callbacks': [], 'summaries': 0, 'authenticated': 0}
    lock = threading.Lock()

    class ControlledBackend(BaseHTTPRequestHandler):
        def handle_request(self, post):
            if self.headers.get('X-Webhook-Key') != key:
                self.send_error(401)
                return
            with lock:
                state['authenticated'] += 1
                payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}') if post else {}
                if self.path == '/api/v1/webhooks/events' and post:
                    event_id = payload['event_id']
                    duplicate = event_id in state['events']
                    state['events'][event_id] = payload
                    result = {'accepted': True, 'duplicate': duplicate}
                elif self.path == '/api/v1/webhooks/notifications' and post:
                    state['callbacks'].append(payload)
                    result = {'accepted': True, 'duplicate': False}
                elif self.path == '/api/v1/automation/summary' and not post:
                    state['summaries'] += 1
                    result = {'evaluations': 1, 'suspicious': 1, 'open_incidents': 1}
                else:
                    self.send_error(404)
                    return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        def do_GET(self): self.handle_request(False)
        def do_POST(self): self.handle_request(True)
        def log_message(self, *args): pass

    backend = ThreadingHTTPServer(('127.0.0.1', 0), ControlledBackend)
    threading.Thread(target=backend.serve_forever, daemon=True).start()
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        n8n_port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{n8n_port}'
    process = None
    with tempfile.TemporaryDirectory(prefix='vigia-n8n-verify-') as work:
        env = dict(os.environ)
        env.update(N8N_USER_FOLDER=work, N8N_ENCRYPTION_KEY=secrets.token_hex(32),
                   N8N_HOST='127.0.0.1', N8N_LISTEN_ADDRESS='127.0.0.1', N8N_PORT=str(n8n_port),
                   N8N_PROTOCOL='http', N8N_SECURE_COOKIE='false', N8N_LOG_LEVEL='info',
                   N8N_DIAGNOSTICS_ENABLED='false', N8N_VERSION_NOTIFICATIONS_ENABLED='false',
                   N8N_BLOCK_ENV_ACCESS_IN_NODE='false', N8N_USE_WORKFLOW_PUBLICATION_SERVICE='false',
                   N8N_LICENSE_AUTO_RENEW_ENABLED='false', GENERIC_TIMEZONE='America/Lima',
                   INTERNAL_API_URL=f'http://127.0.0.1:{backend.server_port}/api/v1',
                   N8N_INTERNAL_URL=base, WEBHOOK_KEY=key, EMAIL_NOTIFICATIONS_ENABLED='false',
                   SMTP_HOST='127.0.0.1', SMTP_PORT='9', SMTP_FROM='test@vigia.local',
                   ALERT_RECIPIENT='nobody@vigia.local', APP_URL='http://127.0.0.1',
                   REPORT_SCHEDULE_CRON='*/2 * * * * *', N8N_WEBHOOK_URL=base+'/',
                   PATH=str(Path(executable).parent)+os.pathsep+env.get('PATH', ''))
        # Keep any caller's real project credentials out of the isolated process.
        for name in ('OPENAI_API_KEY', 'VIRUSTOTAL_API_KEY', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'DATABASE_URL'):
            env.pop(name, None)
        log_path = Path(work) / 'runtime.log'
        with log_path.open('w+') as log:
            def run(args):
                result = subprocess.run(args, env=env, cwd=work, stdout=log, stderr=log, timeout=120)
                if result.returncode:
                    log.flush()
                    raise RuntimeError('n8n command failed: '+str(args[1:])+ '\n'+log_path.read_text()[-6000:])
            try:
                run(['node', str(folder/'bootstrap.cjs')])
                for file in sorted(folder.glob('*.json')):
                    workflow_id = json.loads(file.read_text())['id']
                    run([executable, 'publish:workflow', '--id='+workflow_id])
                import sqlite3
                with sqlite3.connect(str(Path(work)/'.n8n/database.sqlite')) as check_db:
                    records = check_db.execute('SELECT id,active,activeVersionId FROM workflow_entity').fetchall()
                    assert len(records) == 4 and all(item[1] and item[2] for item in records), str(records)+'\n'+log_path.read_text()[-5000:]
                process = subprocess.Popen([executable, 'start'], env=env, cwd=work, stdout=log, stderr=log)
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError('n8n exited on startup\n'+log_path.read_text()[-6000:])
                    try:
                        with urlopen(base+'/healthz', timeout=1) as response:
                            if response.status == 200: break
                    except (HTTPError, URLError, TimeoutError): pass
                    time.sleep(.5)
                else: raise RuntimeError('n8n startup timeout')
                # HTTP server readiness precedes webhook publication readiness.
                time.sleep(3)
                def post(path, payload, authenticated=True):
                    headers={'Content-Type':'application/json'}
                    if authenticated: headers['X-Webhook-Key']=key
                    request=Request(base+path, json.dumps(payload).encode(), headers, method='POST')
                    try:
                        with urlopen(request, timeout=10) as result: return result.status
                    except HTTPError as error: return error.code
                external={'event_id':'controlled-external', 'type':'risk.alert', 'data':{'evaluation_id':'controlled-evaluation','risk':'high','notification_allowed':False}}
                for _ in range(120):
                    unauthorized_status = post('/webhook/vigia-external',external,False)
                    if unauthorized_status != 404: break
                    time.sleep(.5)
                assert unauthorized_status in (401,403), f'Expected auth rejection, HTTP {unauthorized_status}\n'+log_path.read_text()[-5000:]
                assert post('/webhook/vigia-external',external) == 200
                critical={'event_id':'controlled-critical','type':'risk.alert','data':{'evaluation_id':'controlled-evaluation','risk':'critical','notification_allowed':False}}
                assert post('/webhook/vigia-alerts',critical) == 200
                for _ in range(100):
                    with lock:
                        types = [event['type'] for event in state['events'].values()]
                        complete = ('incident.escalate' in types and 'report.request' in types and len(state['callbacks']) >= 2 and state['summaries'] >= 1)
                    if complete: break
                    time.sleep(.2)
                else: raise RuntimeError('Expected stages did not complete\n'+log_path.read_text()[-6000:]+'\n'+str(state))
                with lock: before=len(state['callbacks'])
                assert post('/webhook/vigia-alerts',critical) == 200
                time.sleep(2)
                with lock:
                    assert len(state['callbacks']) == before, 'Duplicate event delivered twice'
                    assert all(item['detail']=='Correo desactivado o sin consentimiento.' for item in state['callbacks'])
                    summary={'n8n_version':version,'workflows_imported':4,'workflows_published':4,'authenticated_requests':state['authenticated'],'notification_callbacks':len(state['callbacks']),'scheduled_summaries':state['summaries'],'checks':['webhook rejects missing key','A alerts','A triggers B critical escalation','C actual cron triggers report','D authenticated ingress','duplicate event skips notification'],'backend':'controlled simulated HTTP','openai_executed':False,'emails_sent':0}
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            finally:
                if process and process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try: process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill();process.wait()
                backend.shutdown()

if __name__ == '__main__':
    main()
