"""Task reservation display and atomic video failure settlement.

Queued/running task costs already reserve balance in billing.py. Never debit
that reservation twice or credit it as a refund: only captured fees hit ledger.
"""
import json

from huishi.db import get_db, utc_now


def billing_summary(task):
    billing = dict((task.get('metadata') or {}).get('billing') or {})
    cost = int(task.get('cost') or 0)
    active = task.get('status') in ('queued', 'running')
    billing.setdefault('state', 'reserved' if active else 'charged' if task.get('status') == 'succeeded' else 'released')
    billing.setdefault('reserved_points', cost if active else 0)
    billing.setdefault('charged_points', cost if task.get('status') == 'succeeded' else 0)
    billing.setdefault('released_points', 0 if active or task.get('status') == 'succeeded' else cost)
    return billing


def settle_video_failure(task, metadata, provider, error, *, accepted):
    """Caller holds the worker lease and wraps this in its terminal transaction."""
    fresh = get_db().execute('SELECT status FROM generation_tasks WHERE id=?', (task['id'],)).fetchone()
    if not fresh or fresh['status'] not in ('queued', 'running'):
        return
    cost = int(task['cost'])
    billing = dict(state='released', reserved_points=0, charged_points=0, released_points=cost,
                   upstream_accepted=bool(accepted), settled_at=utc_now())
    # Failed generations are free to the user, including upstream review costs.
    # Preserve the upstream error on the task for operators; never debit it.
    metadata.update(phase='failed', billing=billing, upstream_status='failed', recovery_error='')
    get_db().execute('UPDATE generation_tasks SET metadata_json=? WHERE id=?',
                     (json.dumps(metadata, ensure_ascii=False), task['id']))


def billing_message(billing):
    state = billing['state']
    if state == 'reserved':
        return f"已冻结 {billing['reserved_points']} 点，成功后结算"
    if state == 'charged':
        return f"已结算 {billing['charged_points']} 点"
    return f"已解冻 {billing['released_points']} 点，未扣费"
