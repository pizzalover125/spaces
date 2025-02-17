import os
from flask import Flask, render_template, redirect, flash, request, jsonify, url_for, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from datetime import datetime
from dotenv import load_dotenv
from models import db, User, Site
from slugify import slugify
from github_routes import github_bp
from slack_routes import slack_bp

load_dotenv()


def get_database_url():
    """Get database URL from environment variables"""
    return os.getenv('DATABASE_URL')


app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev')
app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 3600,
    'pool_pre_ping': True
}

app.config['PREFERRED_URL_SCHEME'] = 'https'

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

app.register_blueprint(github_bp)
app.register_blueprint(slack_bp)


def check_db_connection():
    try:
        with app.app_context():
            db.engine.connect()
        return True
    except Exception as e:
        app.logger.error(f"Database connection failed: {str(e)}")
        return False


@app.before_request
def check_database():
    if request.endpoint in ['static', 'error_page']:
        return None
    try:
        if not check_db_connection():
            return render_template(
                'error.html',
                error_message=
                "Database connection is currently unavailable. We're working on it!"
            ), 503
    except Exception as e:
        app.logger.error(f"Database check failed: {str(e)}")
        return render_template(
            'error.html',
            error_message=
            "Database connection is currently unavailable. We're working on it!"
        ), 503


@app.route('/error')
def error_page():
    return render_template(
        'error.html',
        error_message=
        "Database connection is currently unavailable. We're working on it!"
    ), 503


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception as e:
        app.logger.error(f"Failed to load user: {str(e)}")
        return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if current_user.is_authenticated:
        return redirect(url_for('welcome'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('welcome'))

        flash('Invalid email or password', 'error')

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle user registration"""
    if current_user.is_authenticated:
        return redirect(url_for('welcome'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        preview_code = request.form.get('preview_code')

        if preview_code != 'iloveboba':
            flash('Invalid preview code', 'error')
            return render_template('signup.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('signup.html')

        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'error')
            return render_template('signup.html')

        user = User(username=username, email=email, preview_code_verified=True)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash('Successfully registered! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/welcome')
@login_required
def welcome():
    """Welcome page after successful login"""
    sites = Site.query.filter_by(user_id=current_user.id).order_by(
        Site.updated_at.desc()).all()
    return render_template('welcome.html', sites=sites)


@app.route('/edit/<int:site_id>')
@login_required
def edit_site(site_id):
    """Edit a site"""
    try:
        site = Site.query.get_or_404(site_id)
        if site.user_id != current_user.id:
            app.logger.warning(
                f'User {current_user.id} attempted to access site {site_id} owned by {site.user_id}'
            )
            abort(403)
        app.logger.info(f'User {current_user.id} editing site {site_id}')
        if site.site_type == 'python':
            return render_template('python_editor.html', site=site)
        return render_template('site_editor.html', site=site)
    except Exception as e:
        app.logger.error(f'Error in edit_site: {str(e)}')
        abort(500)


@app.route('/api/sites/<int:site_id>/run', methods=['POST'])
@login_required
def run_python(site_id):
    """Run Python code"""
    try:
        site = Site.query.get_or_404(site_id)
        if site.user_id != current_user.id:
            abort(403)

        data = request.get_json()
        code = data.get('code', '')

        import sys
        from io import StringIO
        old_stdout = sys.stdout
        redirected_output = StringIO()
        sys.stdout = redirected_output

        try:
            exec(code, {})
            output = redirected_output.getvalue()
            return jsonify({'output': output})
        except Exception as e:
            return jsonify({'output': str(e), 'error': True}), 400
        finally:
            sys.stdout = old_stdout

    except Exception as e:
        return jsonify({'message': str(e)}), 500


@app.route('/s/<string:slug>')
def view_site(slug):
    """View a public site"""
    site = Site.query.filter_by(slug=slug).first_or_404()
    if not site.is_public and (not current_user.is_authenticated
                               or site.user_id != current_user.id):
        abort(403)
    return site.html_content


@app.route('/api/sites', methods=['POST'])
@login_required
def create_site():
    """Create a new site"""
    try:
        site_count = Site.query.filter_by(user_id=current_user.id).count()
        if site_count >= 3:
            app.logger.warning(
                f'User {current_user.id} attempted to exceed site limit')
            return jsonify({
                'message':
                'You have reached the maximum limit of 3 sites per account'
            }), 403

        data = request.get_json()
        if not data:
            app.logger.error('No JSON data received')
            return jsonify({'message': 'Invalid request data'}), 400

        name = data.get('name')
        if not name:
            app.logger.warning('Site name not provided')
            return jsonify({'message': 'Name is required'}), 400

        app.logger.info(
            f'Creating new site "{name}" for user {current_user.id}')
        site = Site(name=name, user_id=current_user.id)
        db.session.add(site)
        db.session.commit()

        app.logger.info(f'Successfully created site {site.id}')
        return jsonify({
            'message': 'Site created successfully',
            'site_id': site.id
        })
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error creating site: {str(e)}')
        return jsonify({'message': 'Failed to create site'}), 500


@app.route('/api/sites/<int:site_id>', methods=['PUT'])
@app.route('/api/sites/<int:site_id>/python', methods=['PUT'])
@login_required
def update_site(site_id):
    """Update a site's content"""
    site = Site.query.get_or_404(site_id)
    if site.user_id != current_user.id:
        abort(403)

    data = request.get_json()
    html_content = data.get('html_content')
    python_content = data.get('python_content')

    if html_content is None and python_content is None:
        return jsonify({'message': 'Content is required'}), 400

    if html_content is not None:
        site.html_content = html_content
    if python_content is not None:
        site.python_content = python_content

    site.updated_at = datetime.utcnow()

    try:
        db.session.commit()
        return jsonify({'message': 'Site updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Failed to update site'}), 500


@app.route('/api/sites/<int:site_id>/rename', methods=['PUT'])
@login_required
def rename_site(site_id):
    """Rename a site"""
    site = Site.query.get_or_404(site_id)
    if site.user_id != current_user.id:
        abort(403)

    data = request.get_json()
    new_name = data.get('name')

    if not new_name:
        return jsonify({'message': 'New name is required'}), 400

    try:
        new_slug = slugify(new_name)
        existing_site = Site.query.filter(Site.slug == new_slug, Site.id
                                          != site_id).first()
        if existing_site:
            return jsonify({'message':
                            'A site with this name already exists'}), 400

        site.name = new_name
        site.slug = new_slug
        site.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'message': 'Site renamed successfully'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error renaming site: {str(e)}')
        return jsonify({'message': 'Failed to rename site'}), 500


@app.route('/api/sites/python', methods=['POST'])
@login_required
def create_python_site():
    """Create a new Python script site"""
    try:
        site_count = Site.query.filter_by(user_id=current_user.id).count()
        if site_count >= 3:
            return jsonify({
                'message':
                'You have reached the maximum limit of 3 sites per account'
            }), 403

        data = request.get_json()
        if not data:
            return jsonify({'message': 'Invalid request data'}), 400

        name = data.get('name')
        if not name:
            return jsonify({'message': 'Name is required'}), 400

        site = Site(name=name,
                    user_id=current_user.id,
                    html_content='print("Hello, World!")',
                    site_type='python')
        db.session.add(site)
        db.session.commit()

        return jsonify({
            'message': 'Python script created successfully',
            'site_id': site.id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Failed to create Python script'}), 500


@app.route('/python/<int:site_id>')
@login_required
def python_editor(site_id):
    """Python script editor"""
    site = Site.query.get_or_404(site_id)
    if site.user_id != current_user.id:
        abort(403)
    return render_template('python_editor.html', site=site)


@app.route('/api/sites/<int:site_id>', methods=['DELETE'])
@login_required
def delete_site(site_id):
    """Delete a site"""
    site = Site.query.get_or_404(site_id)
    if site.user_id != current_user.id:
        abort(403)

    try:
        db.session.delete(site)
        db.session.commit()
        return jsonify({'message': 'Site deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Failed to delete site'}), 500


@app.route('/documentation')
def documentation():
    """Documentation page"""
    return render_template('documentation.html')


@app.route('/logout')
@login_required
def logout():
    """Logout the current user"""
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Handle user settings updates"""
    if request.method == 'POST':
        user = current_user
        action = request.form.get('action')

        if action == 'update_profile':
            username = request.form.get('username')
            email = request.form.get('email')

            if username != user.username and User.query.filter_by(
                    username=username).first():
                return jsonify({
                    'status': 'error',
                    'message': 'Username already taken'
                })
            if email != user.email and User.query.filter_by(
                    email=email).first():
                return jsonify({
                    'status': 'error',
                    'message': 'Email already registered'
                })

            user.username = username
            user.email = email
            db.session.commit()
            return jsonify({
                'status': 'success',
                'message': 'Profile updated successfully'
            })

        elif action == 'change_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')

            if not user.check_password(current_password):
                return jsonify({
                    'status': 'error',
                    'message': 'Current password is incorrect'
                })

            user.set_password(new_password)
            db.session.commit()
            return jsonify({
                'status': 'success',
                'message': 'Password changed successfully'
            })

    return render_template('settings.html')


def initialize_database():
    try:
        with app.app_context():
            db.create_all()
        return True
    except Exception as e:
        app.logger.warning(f"Database initialization skipped: {str(e)}")
        return False


if __name__ == '__main__':
    try:
        initialize_database()
    except:
        app.logger.warning("Running without database support")
    app.run(host='0.0.0.0', port=3000)
