from app import app, db
from models import ExternalServer, ExternalServerMetric

with app.app_context():
    db.create_all()
    print("Tables created successfully!")
