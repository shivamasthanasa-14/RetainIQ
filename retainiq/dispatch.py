"""Explicit local-only dispatch and idempotent demonstration receiver."""
import json
import requests
from urllib.parse import urlparse
from .store import now

def dispatch(store, dispatch_id, url='http://127.0.0.1:8766/receive'):
    parsed = urlparse(url)
    if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('Demonstration dispatch must use a local HTTP receiver')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM dispatches WHERE id=?', (dispatch_id,)).fetchone()
        if not row:
            raise ValueError('Dispatch not found')
        if row['status'] == 'Delivered':
            return 'Already delivered'
        ticket = db.execute('SELECT status,owner FROM tickets WHERE ticket_id=?', (row['ticket_id'],)).fetchone()
        if ticket['status'] != 'Escalated':
            raise ValueError('Only currently escalated tickets may be dispatched')
        payload = json.loads(row['payload'])
        payload['owner'] = ticket['owner']
        payload['dispatch_id'] = dispatch_id
        try:
            response = requests.post(url, json=payload, timeout=15)
            response.raise_for_status()
            ack = response.json()
            if ack.get('dispatch_id') != dispatch_id or ack.get('received') is not True:
                raise ValueError('Receiver did not acknowledge this dispatch')
            status, error = 'Delivered', ''
        except (requests.RequestException, ValueError) as exc:
            status, error = 'Failed', str(exc)[:500]
        db.execute('UPDATE dispatches SET status=?,attempts=attempts+1,last_error=?,owner=?,payload=?,updated_at=? WHERE id=?',
                   (status, error, ticket['owner'], json.dumps(payload), now(), dispatch_id))
        store.event(db, row['ticket_id'], 'Local dispatch ' + status.lower(), 'Local dispatcher', {'dispatch_id': dispatch_id, 'error': error})
    return status
