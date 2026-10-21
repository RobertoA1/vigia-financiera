"""Run the genuine exported graph against the local real API with AI disabled.

Read WEBHOOK_SHARED_KEY from root .env without logging it. Refuse enabled AI or
nonlocal API hosts. This test never changes .env and never submits an unsafe URL.
"""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values
from lfx.graph import Graph

async def main():
    root = Path(__file__).resolve().parents[2]
    config = dotenv_values(root / '.env')
    if config.get('AI_ENABLED', 'false').lower() != 'false':
        raise SystemExit('This verification requires AI_ENABLED=false')
    key = config.get('WEBHOOK_SHARED_KEY', '')
    if len(key) < 32: raise SystemExit('Missing integration key in local .env')
    base = os.environ.get('LOCAL_API_BASE', 'http://127.0.0.1:8000/api/v1')
    if urlparse(base).hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise SystemExit('Local API hosts only')
    os.environ['LANGFLOW_API_URL'] = base
    os.environ['WEBHOOK_KEY'] = key
    payload = json.loads(Path(__file__).with_name('vigia-evidence-agents.json').read_text())
    graph = Graph.from_payload(payload)
    results = await graph.arun(inputs=[{'input_value': json.dumps({'domain':'ejemplo.invalid','score':25,'risk':'moderate','indicators':[]})}], types=['chat'])
    final = None
    for result in results:
        for output in result.outputs:
            for value in (output.results or {}).values():
                if hasattr(value, 'text'):
                    parsed = json.loads(value.text)
                    if len(parsed.get('stages', {})) == 4:
                        final = parsed
    assert final and list(final['stages']) == ['context','correlation','explanation','incident_support']
    assert all(stage['executed'] is False and stage['reason'] == 'disabled' for stage in final['stages'].values()), 'API must run with AI disabled'
    print(json.dumps({'engine':'lfx==0.2.2','backend':'real local FastAPI','authenticated_stages':4,'all_stages':'unavailable/disabled','openai_executed':False}, indent=2))

if __name__ == '__main__': asyncio.run(main())
