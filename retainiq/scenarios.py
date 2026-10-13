import hashlib
import json
import random
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from .store import Store, now
from .constants import OWNERS

REFERENCE = date(2026, 9, 30)
SCENARIOS = {'Routine Operations':'routine', 'Growing Support Backlog':'backlog', 'Complex Customer Issues':'complex'}
CUSTOMERS = ['Northstar Labs','Juniper Logistics','Beacon Analytics','Atlas Supply','Cedar Studio','Harbor Systems','Lumen Works','Mosaic Studio']

# Baseline categories are fixture metadata, not represented as model inference.
CASES = [
('User invitations','Account Access','Invite an editor','I am a workspace Admin. How do I invite our new operations colleague so she can edit workflows but cannot manage billing?'),
('User invitations','Account Access','Read-only teammate','Our analyst only needs to inspect workflows and run history. Which role should I pick when inviting him? I am the workspace Owner.'),
('Password reset','Account Access','Password link expired','Hi support, the password reset link from yesterday has expired. This is a password-based account, not SSO. What should I do?'),
('Password reset','Account Access','Forgot my password','I forgot my RelayOps password. Where do I request a reset, and what should I check if the email does not arrive?'),
('SSO access','Account Access','Company login loop','The company SSO login sends me back to the identity page after my team changed. I cannot access the workspace. Who needs to investigate?'),
('Invoice downloads','Billing','Invoice for accounting','I am the workspace Owner. Where can I download the latest invoice for our accountant?'),
('Invoice downloads','Billing','Need a bill copy','Our finance team needs a copy of last monthâ€™s subscription invoice. I have Owner access. Can I get it from the workspace?'),
('Payment details','Billing','Replace payment card','We have a new company payment card. As the workspace Owner, where can I update payment details?'),
('Contract review','Billing','Annual subscription refund','We paid annually but are closing a department. Can someone review whether the unused months can be refunded under our agreement?'),
('Contract review','Billing','Custom renewal terms','Please give us a binding discount and different renewal payment terms. Our contract needs review before we can approve renewal.'),
('Workflow publishing','Workflow Configuration','Test before publish','I saved a workflow with a trigger and two actions. Does saving make it run automatically, or should I test and publish it first?'),
('Workflow publishing','Workflow Configuration','Pause during maintenance','We need to stop new workflow runs during maintenance without deleting the workflow. How should we pause it, and what happens to existing runs?'),
('Field mapping','Workflow Configuration','Missing input field','The action requires a customer reference but it is missing from the mapping picker. Our trigger sample is old. How can we refresh the sample and remap it?'),
('Field mapping','Workflow Configuration','Conditional branches','We want one branch for larger orders and another for everything else. How do we configure and test conditions, including empty values?'),
('Slack permissions','Integrations','Private Slack channel','Our Slack action works in a public channel but fails in a private ops channel. Does the RelayOps app need to be invited to the private channel?'),
('Slack permissions','Integrations','Slack access expired','Slack authentication expired after an admin account change. How do we reconnect the authorized workspace and test the action?'),
('Salesforce authorization','Integrations','Salesforce test session','One sample Salesforce test returned INVALID_SESSION_ID. Production is unaffected. What is the supported reconnect procedure?'),
('Production integration incident','Integrations','Salesforce production outage','URGENT: every production Salesforce sync is failing, orders have stopped and records may be missing. We need engineering to investigate before anyone replays the queue.'),
('Production integration incident','Integrations','Order sync down','Since 09:00, all Salesforce order syncs have failed. This blocks fulfilment for a major customer. We cannot tell which records reached Salesforce. Please escalate.'),
('Webhook investigation','Integrations','Duplicate order events','An order appears twice following a webhook timeout. We do not know whether delivery succeeded. Please investigate before replaying production events.'),
('Onboarding session','Onboarding','Plan first workflow','We have just created a workspace. Can support arrange an onboarding session to plan the first workflow? What details should we provide?'),
('Onboarding session','Onboarding','New team onboarding','Our operations team is new to RelayOps. We would like an onboarding session and help defining the first use case. How can we arrange this?'),
('Unclear request','Other','It stopped again','It is broken again this morning. I do not know which workflow or integration failed, and I have no error message. Can someone help work out what information is needed?'),
('Security incident','Account Access','Unfamiliar workspace member','An unfamiliar person appears in our members list. We suspect unauthorized access and need a specialist to review this with the workspace Owner.'),
('Unsupported feature','Product Guidance','Handwritten contracts','Can RelayOps read handwritten scanned contracts, translate them into Japanese and sign them automatically? I cannot find documentation for this.'),
('Run investigation','Product Errors','Missing production records','Following a failed production run several customer records appear to be missing. Please involve a person to investigate. We have not retried or deleted anything.'),
]

def fingerprint(ticket):
    return hashlib.sha256((ticket['subject'].strip()+'\n'+ticket['message'].strip()).encode()).hexdigest()

def generate_scenario(key):
    rng = random.Random({'routine':1201,'backlog':2202,'complex':3203}[key])
    weekly = {'routine':[11,14,10,12,9,13,15,16], 'backlog':[4,7,9,11,13,16,18,22], 'complex':[9,13,14,10,15,11,12,16]}[key]
    choices = {'routine':list(range(0,4))+[5,6,7,10,11,12,13,20,21,8,16,22],
               'backlog':[0,1,2,3,5,6,10,10,12,12,14,15,16,17,18,19,20,22,24],
               'complex':[4,8,9,14,16,17,17,18,18,19,19,22,22,23,24,25]}[key]
    tickets = []
    start = REFERENCE - timedelta(days=55)
    for week, count in enumerate(weekly):
        days = [rng.randint(0,6) for _ in range(count)]
        for day in sorted(days):
            received = datetime.combine(start+timedelta(days=week*7+day), datetime.min.time(), timezone.utc)+timedelta(hours=rng.randint(8,17),minutes=rng.randint(0,59))
            index = rng.choice(choices)
            group, category, subject, message = CASES[index]
            probability = .88 if key == 'routine' else (.82-week*.09 if key == 'backlog' else .28)
            resolution = received + timedelta(days=rng.randint(1,6),hours=rng.randint(0,4))
            resolved = rng.random() < probability and resolution.date() <= REFERENCE
            status = 'Resolved' if resolved else rng.choices(['Open','In Progress','Escalated'], [5,4,1] if key!='complex' else [3,3,4])[0]
            if status=='Escalated' and index not in {4,8,9,17,18,19,22,23,24,25}:
                status='Open'  # Routine documented fixtures need no invented escalation.
            due = received.date()+timedelta(days=rng.choice([3,5,7]))
            owner = 'Support Lead' if status=='Escalated' else rng.choice(OWNERS[:2])
            tickets.append({'ticket_id':f'{key.upper()}-{len(tickets)+1:03}', 'customer':rng.choice(CUSTOMERS), 'received_at':received.isoformat(timespec='seconds'),
                'subject':subject,'message':message, 'category':category, 'baseline_group':group, 'case_index':index,
                'processing_status':'Pending AI', 'owner':owner, 'status':status, 'due_date':due.isoformat(),
                'resolved_at':resolution.isoformat(timespec='seconds') if resolved else None,
                'follow_up':'' if resolved else ('Review incident context and agree next update' if status=='Escalated' else 'Check customer context and prepare a response'),
                'resolution_notes':'Customer confirmed resolution in the simulated operating history.' if resolved else ''})
    return {'name':next(n for n,k in SCENARIOS.items() if k==key),'key':key,'reference_date':REFERENCE.isoformat(),'seed_version':3,'tickets':tickets}

def ensure_scenarios(root):
    directory = Path(root)/'data'/'scenarios'
    directory.mkdir(parents=True,exist_ok=True)
    for key in SCENARIOS.values():
        path = directory/(key+'.json')
        if not path.exists():
            path.write_text(json.dumps(generate_scenario(key),indent=2),encoding='utf-8')

def seed_store(store, scenario):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT value FROM metadata WHERE key='seeded'").fetchone():
            return
        for t in scenario['tickets']:
            fields = ['ticket_id','customer','received_at','subject','message','category','processing_status','owner','status','follow_up','due_date','resolution_notes','resolved_at']
            db.execute('INSERT INTO tickets('+','.join(fields)+',updated_at) VALUES ('+','.join('?' for _ in range(len(fields)+1))+')',
                       (*[t[k] for k in fields],t['received_at']))
            store.event(db,t['ticket_id'],'Scenario intake','Support Lead',{'case_index':t['case_index'],'fixture_category':t['category'],'fixture_metadata_is_not_AI':True,'seed_escalation_before':t.get('seed_escalation_before')})
            store.lifecycle_event(db,t['ticket_id'],'Open',t['due_date'],t['received_at'])
            if t['status']=='Resolved':
                store.lifecycle_event(db,t['ticket_id'],'Resolved',t['due_date'],t['resolved_at'])
            elif t['status']!='Open':
                store.lifecycle_event(db,t['ticket_id'],t['status'],t['due_date'],t['received_at'])
        for k,v in [('reference_date',scenario['reference_date']),('scenario',scenario['key']),('seeded','1')]:
            db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',(k,v))

class Workspaces:
    def __init__(self, root, session='local'):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',session):
            raise ValueError('Invalid workspace identifier')
        self.root, self.session = Path(root), session
        ensure_scenarios(root)

    def open(self, key, custom=False):
        if key not in SCENARIOS.values():
            raise ValueError('Unknown scenario')
        directory = self.root/'data'/'workspaces'/self.session
        directory.mkdir(parents=True,exist_ok=True)
        target=directory/(key+('_custom' if custom else '')+'.db')
        legacy=self.root/'data'/'retainiq.db'
        if custom and key=='routine' and self.session=='local' and not target.exists() and legacy.exists():
            with sqlite3.connect(legacy) as src,sqlite3.connect(target) as dst: src.backup(dst)
        store = Store(target)
        if not store.metadata('seeded'):
            if custom:
                store.set_metadata('seeded','1')
                store.set_metadata('scenario',key)
            else:
                seed_store(store,json.loads((self.root/'data'/'scenarios'/(key+'.json')).read_text(encoding='utf-8')))
        if not custom:
            from .seed_corrections import repair_seed_escalations
            repair_seed_escalations(store,self.root)
        return store

    def reset(self, key):
        store = self.open(key)
        snapshots = self.root/'data'/'reset_snapshots'/self.session
        snapshots.mkdir(parents=True,exist_ok=True)
        path = snapshots/(key+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
        with store.connect() as src, sqlite3.connect(path) as dst:
            src.backup(dst)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for table in ['dispatches','history','drafts','lifecycle','response_templates','tickets','metadata']:
                db.execute('DELETE FROM '+table)
        seed_store(store,json.loads((self.root/'data'/'scenarios'/(key+'.json')).read_text(encoding='utf-8')))
        return path
