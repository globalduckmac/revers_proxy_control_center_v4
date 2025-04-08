from app import db, create_app
from models import User

# Создаем контекст приложения
app = create_app()

# Выполняем операции в контексте приложения
with app.app_context():
    # Проверяем, существует ли пользователь admin
    admin = User.query.filter_by(username='admin').first()
    
    if admin:
        print(f"Пользователь {admin.username} уже существует, обновляем пароль")
        admin.set_password('admin')
    else:
        # Создаем учетную запись администратора
        admin = User(
            username='admin',
            email='admin@example.com',
            is_admin=True
        )
        admin.set_password('admin')
        db.session.add(admin)
        print("Создан новый пользователь 'admin'")
    
    # Сохраняем изменения
    db.session.commit()
    print(f"Пароль пользователя 'admin': 'admin'")
    print(f"Email пользователя 'admin': '{admin.email}'")
    print("Используйте эти данные для входа в систему")