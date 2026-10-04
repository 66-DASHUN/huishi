"""JSON management endpoints, protected by existing session permissions and CSRF."""
from flask import Blueprint, g, jsonify, request
from huishi.auth import permission_required
from huishi.admin_permissions import has_permission
from huishi import model_management as management

bp=Blueprint('model_management',__name__,url_prefix='/admin/model-management')


@bp.before_request
def require_json_identity():
    if g.get('user') is None:
        return jsonify(ok=False,error='请先登录'),401
    permission='providers.view' if request.method=='GET' or request.path.endswith('/preview') else 'providers.update'
    if not has_permission(g.user['role'],permission):
        return jsonify(ok=False,error='无权限'),403
    if request.path.endswith('/calls') and not has_permission(g.user['role'],'records.view'):
        return jsonify(ok=False,error='无权限'),403


def payload():
    data=request.get_json(silent=True)
    if not isinstance(data,dict):
        raise ValueError('请发送 JSON 对象')
    return data


@bp.errorhandler(ValueError)
def invalid_request(error):
    return jsonify(ok=False,error=str(error)),409 if isinstance(error,management.RevisionConflict) else 400


@bp.get('/catalog')
@permission_required('providers.view')
def catalog():
    return jsonify(ok=True,**management.catalog())


@bp.post('/connections')
@permission_required('providers.update')
def connections():
    return jsonify(ok=True,connection=management.save_connection(payload()))


@bp.post('/discover')
@permission_required('providers.update')
def discover():
    return jsonify(ok=True,models=management.discover(payload()))


@bp.post('/import')
@permission_required('providers.update')
def import_models():
    return jsonify(ok=True,**management.import_models(payload()))


@bp.post('/models/save')
@permission_required('providers.update')
def models_save():
    data=payload()
    if 'prices' in data and not has_permission(g.user['role'],'billing.update'):
        return jsonify(ok=False,error='无定价修改权限'),403
    return jsonify(ok=True,model=management.save_model(data))


@bp.post('/preview')
@permission_required('providers.view')
def preview():
    return jsonify(ok=True,**management.preview(payload()))


@bp.get('/calls')
@permission_required('records.view')
def calls():
    return jsonify(ok=True,**management.calls(request.args))
