# -*- coding: utf-8 -*-
from flask_login import LoginManager
from models import User

login_manager = LoginManager()

# Настройки перенаправления при попытке зайти на защищенную страницу
login_manager.login_view = 'login'
login_manager.login_message = "Для выполнения данного действия необходимо пройти процедуру аутентификации."
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    """Обязательный метод для Flask-Login, загружающий пользователя из БД по его ID"""
    return User.query.get(int(user_id))