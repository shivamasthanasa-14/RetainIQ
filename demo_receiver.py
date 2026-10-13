import json
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PATH = Path(__file__).parent / 'data' / 'receiver.db'
PATH.parent.mkdir(exist_ok=True)
with sqlite3.connect(PATH) as db:
    db.execute('CREATE TABLE IF NOT EXISTS receipts (dispatch_id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if self.path != '/receive' or int(self.headers.get('Content-Length', '0')) > 100000:
                raise ValueError('Invalid request')
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            did = payload['dispatch_id']
            if type(did) is not int:
                raise ValueError('Invalid dispatch ID')
            with sqlite3.connect(PATH) as db:
                db.execute('INSERT OR IGNORE INTO receipts VALUES (?,?)', (did, json.dumps(payload)))
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'received': True, 'dispatch_id': did}).encode())
        except (ValueError, KeyError):
            self.send_error(400)

if __name__ == '__main__':
    print('Local demonstration receiver: http://127.0.0.1:8766/receive')
    HTTPServer(('127.0.0.1', 8766), Handler).serve_forever()
