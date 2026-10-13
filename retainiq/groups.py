"""Group model-understood issues by handling, never only by broad category."""
from collections import defaultdict

def group_key(ticket):
    handling = 'Individual review' if ticket.get('attention_reason') or ticket['processing_status'] == 'Needs Review' or ticket['status'] == 'Escalated' else 'Standard documentation'
    return (ticket.get('issue_group') or ticket['category']) + ' | ' + handling

def issue_groups(tickets):
    buckets = defaultdict(list)
    for ticket in tickets:
        if ticket['processing_status'] not in {'Pending AI','AI Failed'}:
            buckets[group_key(ticket)].append(ticket)
    result = []
    for key, rows in buckets.items():
        unresolved = [t for t in rows if t['status'] != 'Resolved']
        result.append({'key':key,'Issue Group':key.split(' | ')[0], 'Number of Requests':len(rows),
                       'Common Problem':'Customer requests about '+key.split(' | ')[0].lower(),
                       'Suggested Handling':key.split(' | ')[1], 'Unresolved':len(unresolved), 'tickets':rows})
    return sorted(result, key=lambda g: (-g['Number of Requests'],g['key']))


def problem_description(problem, tickets):
    # Plain-language descriptions of the existing reviewed issue labels.
    descriptions = {
        'Invoice downloads':'Customers need help locating and downloading invoices for accounting and financial reporting.',
        'User invitations':'Customers need help inviting teammates and choosing roles with the right workflow and billing permissions.',
        'Password reset':'Customers need help resetting passwords, replacing expired links, or finding reset emails.',
        'Payment details':'Customers with Owner access need help updating the workspace payment card.',
        'SSO access':'Customers cannot access their workspace because company SSO sign-in loops or fails after a team change.',
        'Contract review':'Customers want their subscription agreement reviewed for refunds, discounts, or changes to renewal terms.',
        'Workflow publishing':'Customers need to understand how testing and publishing activate a saved workflow.',
        'Pause workflows':'Customers want to pause new workflow runs during maintenance without deleting their workflow.',
        'Field mapping':'Customers need help refreshing trigger samples and mapping required input fields.',
        'Conditional branches':'Customers need help configuring and testing workflow branches, including empty input values.',
        'Slack permissions':'Customers need help checking RelayOps access to private Slack channels.',
        'Slack authorization':'Customers need to reconnect Slack after authentication expires or an administrator account changes.',
        'Salesforce authorization':'Customers need help reconnecting Salesforce after a test session reports an authorization error.',
        'Production integration incident':'Customers report failed production Salesforce syncs that block orders and may leave records missing.',
        'Webhook investigation':'Customers report duplicate events after webhook timeouts and need delivery checked before replaying them.',
        'Onboarding session':'Customers want an onboarding session to plan their first workflow and define their use case.',
        'Unclear request':'Customers report a failure but need help identifying the affected workflow, error, and timing.',
        'Security incident':'Customers report unfamiliar workspace members and suspected unauthorized access.',
        'Unsupported feature':'Customers ask about handwritten contract processing, translation, and signing that are not covered by RelayOps documentation.',
        'Run investigation':'Customers report missing records after failed production runs and need investigation before retrying.',
    }
    return descriptions.get(problem) or next((t['summary'] for t in tickets if t.get('summary')), 'Customers need help with '+problem.lower()+'.')
