from datetime import date, datetime, timedelta

def as_date(value):
    return date.fromisoformat(value[:10]) if value else None

def report(store, period='Last 7 Days', reference=None):
    ref = reference or store.reference_date()
    records = [t for t in store.tickets() if as_date(t['received_at']) <= ref]
    events = store.query('SELECT * FROM lifecycle ORDER BY effective_at,id')
    timelines = {}
    resolutions = []
    last = {}
    for event in events:
        tid = event['ticket_id']
        timelines.setdefault(tid,[]).append(event)
        if event['status']=='Resolved' and last.get(tid)!='Resolved':
            resolutions.append((tid,as_date(event['effective_at'])))
        last[tid]=event['status']
    for t in records:
        if t['ticket_id'] not in timelines and t['resolved_at']:
            resolutions.append((t['ticket_id'],as_date(t['resolved_at'])))

    def snapshot(cutoff):
        open_count = overdue = 0
        statuses = {'Open':0,'In Progress':0,'Escalated':0,'Resolved':0}
        for t in records:
            if as_date(t['received_at'])>cutoff: continue
            states = [e for e in timelines.get(t['ticket_id'],[]) if as_date(e['effective_at'])<=cutoff]
            if states:
                status,due = states[-1]['status'],states[-1]['due_date']
            else:
                status = 'Resolved' if t['resolved_at'] and as_date(t['resolved_at'])<=cutoff else 'Open'
                due = t['due_date']
            statuses[status]+=1
            if status!='Resolved':
                open_count+=1
                overdue+=bool(due) and as_date(due)<cutoff
        return open_count,overdue,statuses

    alltime = period=='All Time'
    days = 7 if period=='Last 7 Days' else 30
    start = min((as_date(t['received_at']) for t in records),default=ref) if alltime else ref-timedelta(days=days-1)
    previous_end = start-timedelta(days=1)
    previous_start = previous_end-timedelta(days=days-1)
    received = sum(start<=as_date(t['received_at'])<=ref for t in records)
    resolved = len({tid for tid,day in resolutions if start<=day<=ref})
    open_count,overdue,distribution = snapshot(ref)
    comparisons = None
    if not alltime:
        prior_open,prior_overdue,_ = snapshot(previous_end)
        comparisons = {'Requests Received':received-sum(previous_start<=as_date(t['received_at'])<=previous_end for t in records),
                       'Requests Resolved':resolved-len({tid for tid,day in resolutions if previous_start<=day<=previous_end}),
                       'Open Requests':open_count-prior_open,'Overdue Requests':overdue-prior_overdue}
    weekly=[]
    week_start = start-timedelta(days=start.weekday())
    while week_start<=ref:
        end=min(week_start+timedelta(days=6),ref)
        lo=max(week_start,start)
        opened,_,_=snapshot(end)
        weekly.append({'Week':week_start.isoformat(),'Incoming':sum(lo<=as_date(t['received_at'])<=end for t in records),
                       'Resolved':len({tid for tid,day in resolutions if lo<=day<=end}),'Open Requests':opened})
        week_start+=timedelta(days=7)
    categories={}
    for t in records:
        if start<=as_date(t['received_at'])<=ref:
            categories[t['category']]=categories.get(t['category'],0)+1
    return {'reference':ref.isoformat(),'start':start.isoformat(),'metrics':{'Requests Received':received,'Requests Resolved':resolved,'Open Requests':open_count,'Overdue Requests':overdue},
            'comparisons':comparisons,'weeks':weekly,'categories':categories,'distribution':distribution}
