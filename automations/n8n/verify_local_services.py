"""Verify n8n A → real local API/PostgreSQL → Mailpit, never Internet SMTP.

Requires n8n2.44.4, root .env and local running services. Creates an isolated
n8n database, one webhook marker/callback in application PostgreSQL and one
Mailpit message for pruebas@ejemplo.invalid. It never changes root .env.
"""
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import create_engine, text


def main():
    root = Path(__file__).resolve().parents[2]
    folder = Path(__file__).resolve().parent
    config = dotenv_values(root/'.env')
    key = config.get('WEBHOOK_SHARED_KEY', '')
    if len(key) < 32: raise SystemExit('Missing local integration key')
    api = os.environ.get('LOCAL_API_BASE', 'http://127.0.0.1:8000/api/v1')
    mailpit = os.environ.get('LOCAL_MAILPIT_BASE', 'http://127.0.0.1:8025')
    database = os.environ.get('LOCAL_DATABASE_URL', 'postgresql+psycopg://vigia@127.0.0.1:55432/vigia')
    if any(urlparse(url).hostname not in ('127.0.0.1','localhost','::1') for url in (api,mailpit,database)):
        raise SystemExit('This test only accepts local services')
    executable = shutil.which(os.environ.get('N8N_BIN','n8n'))
    if not executable: raise SystemExit('Set N8N_BIN to n8n2.44.4')
    assert subprocess.check_output([executable,'--version'],text=True).strip() == '2.44.4'
    engine = create_engine(database)
    with engine.connect() as connection:
        row = connection.execute(text("SELECT id,domain,risk FROM evaluations WHERE risk='high' ORDER BY created_at DESC LIMIT 1")).mappings().first()
    if not row: raise SystemExit('A high-risk academic evaluation is required')
    event_id = 'local-n8n-'+str(uuid4())
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0)); port=probe.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    process=None
    with tempfile.TemporaryDirectory(prefix='vigia-n8n-live-') as work:
        env=dict(os.environ)
        for name in ('OPENAI_API_KEY','VIRUSTOTAL_API_KEY','SMTP_USERNAME','SMTP_PASSWORD','DATABASE_URL'):
            env.pop(name,None)
        env.update(N8N_USER_FOLDER=work,N8N_ENCRYPTION_KEY=secrets.token_hex(32),N8N_HOST='127.0.0.1',
                   N8N_LISTEN_ADDRESS='127.0.0.1',N8N_PORT=str(port),N8N_PROTOCOL='http',N8N_SECURE_COOKIE='false',
                   N8N_LOG_LEVEL='error',N8N_DIAGNOSTICS_ENABLED='false',N8N_VERSION_NOTIFICATIONS_ENABLED='false',
                   N8N_BLOCK_ENV_ACCESS_IN_NODE='false',N8N_USE_WORKFLOW_PUBLICATION_SERVICE='false',
                   N8N_LICENSE_AUTO_RENEW_ENABLED='false',GENERIC_TIMEZONE='America/Lima',
                   INTERNAL_API_URL=api,N8N_INTERNAL_URL=base,WEBHOOK_KEY=key,EMAIL_NOTIFICATIONS_ENABLED='true',
                   SMTP_HOST='127.0.0.1',SMTP_PORT='1025',SMTP_SSL='false',SMTP_STARTTLS='false',
                   SMTP_FROM='Vigía QA <noreply@vigia.local>',ALERT_RECIPIENT='pruebas@ejemplo.invalid',
                   APP_URL='http://127.0.0.1:8080',N8N_WEBHOOK_URL=base+'/',
                   PATH=str(Path(executable).parent)+os.pathsep+env.get('PATH',''))
        logfile=Path(work)/'runtime.log'
        with logfile.open('w+') as log:
            def run(command):
                result=subprocess.run(command,env=env,cwd=work,stdout=log,stderr=log,timeout=120)
                if result.returncode: raise RuntimeError('n8n command failed\n'+logfile.read_text()[-4000:])
            try:
                run(['node',str(folder/'bootstrap.cjs')])
                workflow_id=json.loads((folder/'A-alertas.json').read_text())['id']
                run([executable,'publish:workflow','--id='+workflow_id])
                process=subprocess.Popen([executable,'start'],env=env,cwd=work,stdout=log,stderr=log)
                payload={'event_id':event_id,'type':'risk.alert','data':{'evaluation_id':row['id'],'domain':row['domain'],'risk':'high','notification_allowed':True}}
                def post(authenticated):
                    headers={'Content-Type':'application/json'}
                    if authenticated: headers['X-Webhook-Key']=key
                    request=Request(base+'/webhook/vigia-alerts',json.dumps(payload).encode(),headers,method='POST')
                    try:
                        with urlopen(request,timeout=5) as response:return response.status
                    except HTTPError as error:return error.code
                for _ in range(180):
                    if process.poll() is not None: raise RuntimeError('n8n stopped\n'+logfile.read_text()[-4000:])
                    try:
                        status=post(False)
                        if status in (401,403):break
                    except (URLError,TimeoutError):pass
                    time.sleep(.5)
                else:raise RuntimeError('Webhook readiness timeout\n'+logfile.read_text()[-4000:])
                assert post(True)==200
                message_id=None
                for _ in range(120):
                    with urlopen(mailpit+'/api/v1/messages?limit=100',timeout=5) as response:messages=json.load(response)['messages']
                    for message in messages:
                        if any(recipient['Address']=='pruebas@ejemplo.invalid' for recipient in message['To']):
                            with urlopen(mailpit+'/api/v1/message/'+message['ID'],timeout=5) as response:full=json.load(response)
                            if event_id in full.get('Text',''):
                                message_id=message['ID']
                    with engine.connect() as connection:
                        callback=connection.execute(text("SELECT result FROM webhook_events WHERE event_id=:event AND kind='notification:email'"),{'event':event_id}).scalar()
                    if message_id and callback:break
                    time.sleep(.25)
                else:raise RuntimeError('Mailpit/callback timeout\n'+logfile.read_text()[-4000:])
                assert (json.loads(callback) if isinstance(callback,str) else callback)['status']=='accepted'
                print(json.dumps({'n8n':'2.44.4 real','backend':'FastAPI real local','persistence':'PostgreSQL real local','smtp':'Mailpit real local 127.0.0.1:1025','recipient':'pruebas@ejemplo.invalid','mailpit_message_id':message_id,'event_id':event_id,'callback':'accepted persisted','internet_email_sent':0,'local_messages_delivered':1},ensure_ascii=False,indent=2))
            finally:
                if process and process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:process.wait(timeout=15)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                engine.dispose()

if __name__=='__main__':main()
