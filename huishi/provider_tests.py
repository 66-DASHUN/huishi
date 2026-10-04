"""Model-specific generation checks, bound to the tested credential version."""
import json
from huishi.db import get_db, utc_now
from huishi.media_tasks import payload_hash
from huishi.providers import get_provider
from huishi.secrets import redact_sensitive_text


def record_video_test_result(task, *, generation, storage, error=''):
    meta=task.get('metadata') or {}
    if not meta.get('test_scope'):
        return
    provider=get_provider(int(task['provider_id']))
    if not provider:
        return
    entry=next((e for e in provider.get('models',[]) if e['id']==task['model']),None)
    if not entry:
        return
    from huishi.model_lifecycle import test_fingerprint
    if meta.get('binding_fingerprint') and meta['binding_fingerprint']!=test_fingerprint(provider,task['model']):
        return
    protocol=entry.get('api_format') or provider['api_format']
    if meta.get('upstream_model') and meta['upstream_model'] != (entry.get('upstream_id') or entry['id']):
        return
    current_version=payload_hash({**{k:provider.get(k) for k in ('api_key','base_url')},'api_format':protocol})
    if current_version != meta.get('credential_version'):
        return
    entries=provider.get('models') or []
    for entry in entries:
        if entry['id'] != task['model']:
            continue
        checks=dict(entry.get('verification') or {})
        checks.update(generation=generation,storage=storage,checked_at=utc_now(),task_id=task['id'],stale=False,
                      error=redact_sensitive_text(error,provider.get('api_key')))
        entry['verification']=checks
    # Compare-and-swap prevents overwriting a simultaneous model editor update.
    original=provider.get('models_json') or '[]'
    get_db().execute('UPDATE api_providers SET models_json=? WHERE id=? AND models_json=?',
                     (json.dumps(entries,ensure_ascii=False),provider['id'],original))
    from huishi.provider_catalog import invalidate_catalog
    invalidate_catalog()
