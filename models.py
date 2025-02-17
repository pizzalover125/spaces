from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from slugify import slugify

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    preview_code_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    github_token = db.Column(db.Text, nullable=True)
    slack_id = db.Column(db.String(50), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'    

class GitHubRepo(db.Model):
    __tablename__ = 'github_repo'
    
    id = db.Column(db.Integer, primary_key=True)
    repo_name = db.Column(db.String(100), nullable=False)
    repo_url = db.Column(db.String(200), nullable=False)
    is_private = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    site = db.relationship('Site', backref=db.backref('github_repo', uselist=False))

    def __repr__(self):
        return f'<GitHubRepo {self.repo_name}>'    

class Site(db.Model):
    __tablename__ = 'site'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    site_type = db.Column(db.String(20), nullable=False, default='web')
    html_content = db.Column(db.Text, nullable=False, default='<h1>Welcome to my site!</h1>')
    python_content = db.Column(db.Text, nullable=False, default='print("Hello, World!")')
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('sites', lazy=True))
    
    def __init__(self, *args, **kwargs):
        if 'slug' not in kwargs:
            kwargs['slug'] = slugify(kwargs.get('name', ''))
        super(Site, self).__init__(*args, **kwargs)
    
    def __repr__(self):
        return f'<Site {self.name}>'
