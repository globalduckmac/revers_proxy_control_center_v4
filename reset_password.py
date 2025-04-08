from app import db, create_app
from models import User
from werkzeug.security import generate_password_hash

# Создаем контекст приложения
app = create_app()

# Выполняем операции в контексте приложения
with app.app_context():
    # Находим пользователя admin
    admin = User.query.filter_by(username='admin').first()
    
    if admin:
        # Сбрасываем пароль на 'admin'
        admin.password_hash = generate_password_hash('admin')
        db.session.commit()
        print(f"Пароль пользователя {admin.username} успешно сброшен на 'admin'")
    else:
        print("Пользователь 'admin' не найден в базе данных")