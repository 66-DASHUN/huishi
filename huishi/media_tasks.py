"""Durable submission identity, worker fencing and recovery bookkeeping."""
import hashlib
import json
import secrets
import time
from huishi.db import get_db, immediate_transaction, utc_now

SCHEMA = '''
CREATE TABLE IF NOT EXISTS media_reference_assets (
 id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, storage_key TEXT NOT NULL,
 metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media_request_keys (
 user_id INTEGER NOT NULL, request_key TEXT NOT NULL, payload_hash TEXT NOT NULL,
 task_id INTEGER NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(user_id, request_key)
);
CREATE TABLE IF NOT EXISTS media_task_leases (
 task_id INTEGER PRIMARY KEY, owner_token TEXT NOT NULL DEFAULT '',
 lease_expires_at INTEGER NOT NULL DEFAULT 0, fencing_token INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS media_task_settlements (
 task_id INTEGER PRIMARY KEY, record_id INTEGER NOT NULL, points INTEGER NOT NULL, settled_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS video_pricing_rules (
 id INTEGER PRIMARY KEY AUTOINCREMENT, model TEXT NOT NULL, resolution TEXT NOT NULL,
 billing_unit TEXT NOT NULL CHECK (billing_unit IN ('per_second','per_request')),
 duration_seconds INTEGER NOT NULL DEFAULT 0, points INTEGER NOT NULL CHECK(points > 0),
 enabled INTEGER NOT NULL DEFAULT 1,
 UNIQUE(model,resolution,billing_unit,duration_seconds)
);
'''


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def request_replay(user_id, key, payload):
    if not key or len(key) > 200:
        raise ValueError('请求标识不能为空或超过200字符')
    row = get_db().execute('SELECT payload_hash, task_id FROM media_request_keys WHERE user_id=? AND request_key=?', (user_id, key)).fetchone()
    if row is None:
        return None
    if row['payload_hash'] != payload_hash(payload):
        raise ValueError('同一请求标识不能用于不同的生成参数')
    return int(row['task_id'])


def remember_request(user_id, key, payload, task_id):
    get_db().execute('INSERT INTO media_request_keys(user_id,request_key,payload_hash,task_id,created_at) VALUES (?,?,?,?,?)',
                     (user_id, key, payload_hash(payload), task_id, utc_now()))


def claim_task(task_id):
    token = secrets.token_hex(16)
    now = int(time.time())
    with immediate_transaction():
        db = get_db()
        db.execute('INSERT INTO media_task_leases(task_id) VALUES (?) ON CONFLICT(task_id) DO NOTHING', (task_id,))
        changed = db.execute('UPDATE media_task_leases SET owner_token=?, lease_expires_at=?, fencing_token=fencing_token+1 WHERE task_id=? AND lease_expires_at<=?',
                             (token, now+180, task_id, now)).rowcount
    return token if changed == 1 else None


def assert_owner(task_id, token):
    changed=get_db().execute('UPDATE media_task_leases SET lease_expires_at=lease_expires_at WHERE task_id=? AND owner_token=? AND lease_expires_at>?',
                             (task_id,token,int(time.time()))).rowcount
    if changed != 1:
        raise RuntimeError('视频任务租约已失效')


def save_phase(task_id, token, metadata, phase, **extra):
    now = int(time.time())
    with immediate_transaction():
        db = get_db()
        changed = db.execute('UPDATE media_task_leases SET lease_expires_at=? WHERE task_id=? AND owner_token=? AND lease_expires_at>?',
                             (now+180, task_id, token, now)).rowcount
        if changed != 1:
            raise RuntimeError('视频任务租约已失效')
        metadata.update(phase=phase, **extra)
        db.execute("UPDATE generation_tasks SET metadata_json=?, updated_at=? WHERE id=? AND status IN ('queued','running')",
                   (json.dumps(metadata, ensure_ascii=False), utc_now(), task_id))


def release_task(task_id, token):
    get_db().execute('UPDATE media_task_leases SET lease_expires_at=0 WHERE task_id=? AND owner_token=?', (task_id, token))
    get_db().commit()


def recover_video_tasks(app):
    """Called by worker maintenance; leases make duplicate queue deliveries safe."""
    from huishi.generation_queue import enqueue_generation_task
    now = int(time.time())
    rows = get_db().execute("SELECT t.id,t.metadata_json FROM generation_tasks t LEFT JOIN media_task_leases l ON l.task_id=t.id WHERE t.media_type='video' AND t.status IN ('queued','running') AND (l.task_id IS NULL OR l.lease_expires_at<=?)", (now,)).fetchall()
    for row in rows:
        meta = json.loads(row['metadata_json'] or '{}')
        if meta.get('phase') == 'needs_reconciliation' or int(meta.get('next_poll_at') or 0) > now:
            continue
        enqueue_generation_task(app, int(row['id']))


# 待人工核对的视频任务：上游受理状态未知，因此**自动恢复被刻意暂停**
# （见 recover_video_tasks 里对 needs_reconciliation 的跳过），只能由管理员
# 确认原渠道后手动恢复。两处消费者必须共用这一段查询：
#   * 业务流水页的待核对表格
#   * 运行总览的健康探针（否则首页数字与列表会对不上）
_NEEDS_RECONCILIATION_SELECT = (
    "SELECT id,user_id,model,provider_id,provider_task_id,metadata_json,created_at "
    "FROM generation_tasks "
    "WHERE media_type='video' AND status IN ('queued','running') "
    "ORDER BY id DESC"
)


def _row_metadata(row) -> dict:
    """安全解析 metadata_json。

    容错是必要的：这一列由多个写入路径维护，一条写坏的行不应让整个
    业务流水页或运行总览探针一起挂掉。
    """
    try:
        metadata = json.loads(row['metadata_json'] or '{}')
    except (TypeError, ValueError):
        return {}
    return metadata if isinstance(metadata, dict) else {}


def needs_reconciliation_tasks():
    """列出需要管理员核对的视频任务（最近在前）。"""
    result = []
    for row in get_db().execute(_NEEDS_RECONCILIATION_SELECT).fetchall():
        metadata = _row_metadata(row)
        if metadata.get('phase') != 'needs_reconciliation':
            continue
        item = dict(row)
        item['metadata'] = metadata
        result.append(item)
    return result


def count_needs_reconciliation() -> int:
    """待核对任务数，供运行总览的健康探针使用。"""
    return sum(
        1
        for row in get_db().execute(_NEEDS_RECONCILIATION_SELECT).fetchall()
        if _row_metadata(row).get('phase') == 'needs_reconciliation'
    )


def resume_video_task(app, task_id):
    """Admin retry preserves task identity and never guesses an upstream ID."""
    from huishi.records import get_generation_task
    from huishi.generation_queue import enqueue_generation_task
    from huishi.media_capabilities import CHANNEL_PROTOCOLS
    token=claim_task(task_id)
    if not token:
        raise ValueError('任务正在处理，请稍后再试')
    try:
        task=get_generation_task(task_id)
        if not task or task.get('media_type')!='video' or task['status'] not in ('queued','running'):
            raise ValueError('仅能恢复未完成的视频任务')
        meta=task.get('metadata') or {}
        if meta.get('phase')!='needs_reconciliation':
            raise ValueError('任务未处于暂停核对状态，无需重复操作')
        if not task.get('provider_task_id') and (meta.get('api_format') not in CHANNEL_PROTOCOLS or not meta.get('idempotency_key') or not meta.get('normalized_request')):
            raise ValueError('缺少上游任务号或原始幂等请求，必须先人工核对；不会新建生成任务')
        phase='polling' if task.get('provider_task_id') else 'submitting'
        save_phase(task_id,token,meta,phase,recovery_attempts=0,next_poll_at=0,recovery_error='')
    finally:
        release_task(task_id,token)
    try:
        enqueue_generation_task(app,task_id)
    except Exception:
        app.logger.exception('manual video resume queued for maintenance task_id=%s',task_id)
