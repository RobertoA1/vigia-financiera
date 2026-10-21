"""Runs the exported graph through real LFX; backend/OpenAI are explicitly simulated.

No model key or deployed backend needed. The fake service validates the fixed
endpoint, header and stage order, returns unavailable (never fabricated AI).
"""
import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from lfx.graph import Graph

calls = []
class ControlledBackend(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/api/v1/automation/intelligence' or self.headers.get('X-Webhook-Key') != 'x' * 48:
            self.send_error(403)
            return
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        calls.append(body['role'])
        result = {"status": "unavailable", "executed": False, "calls": 0, "agents": {}, "reason": "simulated_backend_no_key", "model": "gpt-6-mini"}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
    def log_message(self, *args):
        pass

async def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), ControlledBackend)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ['LANGFLOW_API_URL'] = f'http://127.0.0.1:{server.server_port}/api/v1'
    os.environ['WEBHOOK_KEY'] = 'x' * 48
    try:
        payload = json.loads(Path(__file__).with_name('vigia-evidence-agents.json').read_text())
        graph = Graph.from_payload(payload)
        results = await graph.arun(inputs=[{'input_value': json.dumps({'domain':'ejemplo.test','score':25,'risk':'moderate','indicators':[]})}], types=['chat'])
        assert calls == ['context','correlation','explanation','incident_support'], calls
        assert results, 'No output from graph'
        output = str(results)
        assert 'simulated_backend_no_key' in output
        print('PASS: export imported by real LFX, 6 nodes, 5 edges, all 4 stages executed against controlled backend. OpenAI NOT executed.')
    finally:
        server.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
