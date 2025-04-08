from app import app, db
import sqlalchemy as sa
from sqlalchemy import text

# Run this script to add the glances_enabled column to the external_server table
# and update the status column name from last_status to status

with app.app_context():
    # Check if the column already exists
    conn = db.engine.connect()
    
    # Get the column information
    inspector = sa.inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('external_server')]

    # Add missing columns
    try:
        if 'glances_enabled' not in columns:
            print("Adding glances_enabled column to external_server table...")
            conn.execute(text("ALTER TABLE external_server ADD COLUMN glances_enabled BOOLEAN DEFAULT TRUE"))
            conn.commit()
            print("Added glances_enabled column.")
        else:
            print("glances_enabled column already exists.")

        # Check if we need to rename last_status to status
        if 'last_status' in columns and 'status' not in columns:
            print("Renaming last_status column to status...")
            conn.execute(text("ALTER TABLE external_server RENAME COLUMN last_status TO status"))
            conn.commit()
            print("Renamed last_status column to status.")
        elif 'status' not in columns:
            print("Adding status column...")
            conn.execute(text("ALTER TABLE external_server ADD COLUMN status VARCHAR(20) DEFAULT 'unknown'"))
            conn.commit()
            print("Added status column.")
        else:
            print("status column already exists.")

        print("Database structure updated successfully!")
    except Exception as e:
        print(f"Error updating database: {str(e)}")
    finally:
        conn.close()