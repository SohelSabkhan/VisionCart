from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import bcrypt

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    carts = db.relationship('Cart', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

class Cart(db.Model):
    __tablename__ = 'carts'

    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.String(36), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    items = db.Column(db.JSON, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
