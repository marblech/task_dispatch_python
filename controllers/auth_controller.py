from flask import Blueprint, request, render_template, redirect, url_for, session, flash, jsonify
from db.dbconn import DBConn
from models.user import UserTable
from utils.password_helper import PasswordHelper
import os
from datetime import datetime

auth_bp = Blueprint('auth', __name__,
                    template_folder='../templates',
                    static_folder='../static',
                    static_url_path='/static')


def _upgrade_legacy_user_password(session_db, user, plain_password: str):
    hashed_pwd, salt = PasswordHelper.hash_password(plain_password)
    user.user_pwd = hashed_pwd
    user.salt = salt
    user.update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session_db.add(user)
    session_db.commit()


def init_default_user():
    """初始化默认管理员账号"""
    session_db = None
    try:
        db = DBConn()
        session_db = db.get_session()
        
        # 检查是否已有用户
        existing_user = session_db.query(UserTable).filter_by(username="admin").first()
        if existing_user:
            return
        
        # 创建默认管理员
        admin_data = PasswordHelper.create_default_admin()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        admin_user = UserTable(
            username=admin_data["username"],
            user_pwd=admin_data["user_pwd"],
            salt=admin_data["salt"],
            add_time=now,
            update_time=now
        )
        
        session_db.add(admin_user)
        session_db.commit()
        print(f"[auth] 默认管理员账号已创建: {admin_data['username']}")
    except Exception as e:
        print(f"[auth] 创建默认管理员账号失败: {e}")
    finally:
        if session_db is not None:
            session_db.close()


def check_user_exists():
    """检查是否已有用户（用于决定是否显示注册页面等）"""
    session_db = None
    try:
        db = DBConn()
        session_db = db.get_session()
        count = session_db.query(UserTable).count()
        return count > 0
    except Exception:
        return False
    finally:
        if session_db is not None:
            session_db.close()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'POST':
        # AJAX请求处理
        if request.is_json:
            data = request.get_json()
            username = data.get('username', '')
            password = data.get('password', '')
            
            result = authenticate_user(username, password)
            
            if result['success']:
                session['logged_in'] = True
                session['username'] = result['username']
                return jsonify({
                    'success': True,
                    'message': '登录成功',
                    'redirect': '/manager'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': result['message']
                })
        else:
            # 传统表单提交
            username = request.form.get('username', '')
            password = request.form.get('password', '')
            
            result = authenticate_user(username, password)
            
            if result['success']:
                session['logged_in'] = True
                session['username'] = result['username']
                flash('登录成功！', 'success')
                return redirect('/manager')
            else:
                flash(result['message'], 'error')
                return redirect('/login')
    
    # GET请求，显示登录页面
    return render_template('login.html')


def authenticate_user(username: str, password: str) -> dict:
    """
    验证用户账号和密码
    Returns:
        dict: {'success': bool, 'message': str, 'username': str}
    """
    session_db = None
    try:
        db = DBConn()
        session_db = db.get_session()
        
        user = session_db.query(UserTable).filter_by(username=username).first()
        
        if not user:
            return {'success': False, 'message': '用户名或密码错误', 'username': ''}
        
        # 验证密码
        if not PasswordHelper.verify_password(password, user.user_pwd, user.salt):
            return {'success': False, 'message': '用户名或密码错误', 'username': ''}

        if PasswordHelper.password_needs_upgrade(user.salt):
            try:
                _upgrade_legacy_user_password(session_db, user, password)
                print(f"[auth] 已升级旧密码格式: {user.username}")
            except Exception as exc:
                session_db.rollback()
                print(f"[auth] 升级旧密码格式失败: {exc}")
        
        return {'success': True, 'message': '登录成功', 'username': user.username}
    
    except Exception as e:
        print(f"[auth] 验证用户失败: {e}")
        return {'success': False, 'message': '系统错误，请稍后重试', 'username': ''}
    finally:
        if session_db is not None:
            session_db.close()


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """注销登录"""
    session.clear()
    if request.is_json:
        return jsonify({'success': True, 'message': '已退出登录'})
    flash('已退出登录', 'info')
    return redirect('/login')


@auth_bp.route('/api/auth/status', methods=['GET'])
def auth_status():
    """检查登录状态"""
    logged_in = session.get('logged_in', False)
    if logged_in:
        return jsonify({
            'logged_in': True,
            'username': session.get('username', '')
        })
    return jsonify({
        'logged_in': False
    })


@auth_bp.route('/manager')
def manager():
    """管理页面（重定向到manager.html）"""
    if not session.get('logged_in'):
        if request.is_json:
            return jsonify({'success': False, 'message': '未登录', 'redirect': '/login'})
        return redirect('/login')
    
    return render_template('manager.html')