CATEGORIES = ['Account Access', 'Billing', 'Workflow Configuration', 'Integrations', 'Product Errors', 'Onboarding', 'Product Guidance', 'Other']
OWNERS = ['Agent X', 'Agent Y', 'Support Lead']
LEGACY_OWNERS = {'Maya Chen — Support': 'Agent X', 'Leo Martin — Technical Support': 'Agent Y', 'Samira Patel — Billing': 'Agent X', 'Alex Reed — Engineering': 'Support Lead'}
ROUTING = {c: OWNERS[0] for c in CATEGORIES}
ROUTING.update({'Billing': OWNERS[0], 'Integrations': OWNERS[1], 'Product Errors': OWNERS[1]})
STATUSES = ['Open', 'In Progress', 'Escalated', 'Resolved']
TRANSITIONS = {'Open': {'In Progress', 'Escalated', 'Resolved'}, 'In Progress': {'Open', 'Escalated', 'Resolved'}, 'Escalated': {'Open', 'In Progress', 'Resolved'}, 'Resolved': {'Open'}}
