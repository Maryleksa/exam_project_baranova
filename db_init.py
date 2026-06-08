from app import app
from models import db, Role, User, Genre
from werkzeug.security import generate_password_hash

with app.app_context():
    print("=== Старт инициализации базы данных SQLite ===")
    
    # 1. Создаем саму базу данных и все таблицы по моделям
    db.create_all()
    print("1. Таблицы базы данных успешно созданы.")

    # 2. Заполняем роли (Администратор, Модератор, Пользователь)
    if not Role.query.first():
        admin_role = Role(id=1, name='administrator', description='Администратор')
        moderator_role = Role(id=2, name='moderator', description='Модератор')
        user_role = Role(id=3, name='user', description='Пользователь')
        
        db.session.add_all([admin_role, moderator_role, user_role])
        print("2. Роли успешно добавлены.")
    else:
        print("2. Роли уже существуют в базе.")

    # 3. Заполняем базовые жанры
    if not Genre.query.first():
        genres_list = [
            Genre(id=1, name='Фантастика'),
            Genre(id=2, name='Роман'),
            Genre(id=3, name='Детектив'),
            Genre(id=4, name='Фэнтези'),
            Genre(id=5, name='Научная литература'),
            Genre(id=6, name='Классика')
        ]
        db.session.add_all(genres_list)
        print("3. Базовые жанры литературы успешно добавлены.")
    else:
        print("3. Жанры уже существуют в базе.")

    # 4. Создаем учетные записи для тестирования
    if not User.query.filter_by(login='admin').first():
        # Генерируем безопасный хэш пароля "password123"
        hashed_password = generate_password_hash("password123")
        
        # Админ
        admin_user = User(
            login='admin', 
            password_hash=hashed_password, 
            last_name='Баранова', 
            first_name='Мария', 
            middle_name='Алексеевна', 
            role_id=1
        )
        # Модератор
        mod_user = User(
            login='moderator', 
            password_hash=hashed_password, 
            last_name='Петров', 
            first_name='Петр', 
            middle_name='Петрович', 
            role_id=2
        )
        # Обычный пользователь
        regular_user = User(
            login='user', 
            password_hash=hashed_password, 
            last_name='Иванов', 
            first_name='Иван', 
            middle_name=None, 
            role_id=3
        )
        
        db.session.add_all([admin_user, mod_user, regular_user])
        print("4. Тестовые пользователи успешно созданы!")
        print("   -> Логин: admin      | Пароль: password123 (Роль: Администратор)")
        print("   -> Логин: moderator  | Пароль: password123 (Роль: Модератор)")
        print("   -> Логин: user       | Пароль: password123 (Роль: Пользователь)")
    else:
        print("4. Тестовые пользователи уже есть в базе.")

    # Сохраняем все изменения в файл базы данных
    db.session.commit()
    print("=== База данных полностью готова к работе! ===")