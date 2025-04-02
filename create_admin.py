from app import app, db
from models import User
from datetime import datetime

def create_admin_user():
    with app.app_context():
        # Check if admin already exists
        admin = User.query.filter_by(username='admin').first()
        if admin:
            print("Admin user already exists.")
            return
        
        # Create new admin user
        admin = User(
            username='admin',
            email='admin@example.com',
            created_at=datetime.utcnow(),
            is_admin=True
        )
        admin.set_password('admin123')
        
        # Add to database
        db.session.add(admin)
        db.session.commit()
        print("Admin user created successfully.")

if __name__ == '__main__':
    create_admin_user()