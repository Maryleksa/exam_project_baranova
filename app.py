# -*- coding: cp1251 -*-
import os
import hashlib
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import login_required, current_user
import markdown
import bleach
from werkzeug.utils import secure_filename

# 1. Сначала импортируем менеджер аутентификации
from auth import login_manager

# 2. Затем строго инициализируем сам Flask-апп
app = Flask(__name__)
app.config['SECRET_KEY'] = '1234qwer'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///electronic_library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['PER_PAGE'] = 10

# 3. Связываем login_manager с созданным приложением app
login_manager.init_app(app)

# 4. Подключаем базу данных моделей
from models import db, Book, Genre, Cover, Review, User, Role, Collection, book_genre, book_collection
db.init_app(app)

# --- МАРШРУТЫ (ROUTES) ---
# (Весь остальной код с @app.route('/') и ниже оставляй без изменений)

# --- МАРШРУТЫ (ROUTES) ---

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    # Сортировка по ID по убыванию (как аналог даты добавления / последних релизов)
    pagination = Book.query.order_by(Book.year.desc(), Book.id.desc()).paginate(page=page, per_page=app.config['PER_PAGE'], error_out=False)
    books = pagination.items
    return render_template('index.html', books=books, pagination=pagination)

@app.route('/book/add', methods=['GET', 'POST'])
@login_required
def add_book():
    if current_user.role.name != 'administrator':
        flash("У вас недостаточно прав для выполнения данного действия.", "danger")
        return redirect(url_for('index'))
    
    genres = Genre.query.all()
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            description = request.form.get('description')
            year = request.form.get('year')
            publisher = request.form.get('publisher')
            author = request.form.get('author')
            pages = request.form.get('pages')
            genre_ids = request.form.getlist('genres')
            cover_file = request.files.get('cover')

            if not (title and description and year and publisher and author and pages and cover_file):
                flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")
                return render_template('book_form.html', genres=genres, action="add")

            # Создаем запись книги
            new_book = Book(title=title, description=description, year=int(year), publisher=publisher, author=author, pages=int(pages))
            for g_id in genre_ids:
                genre = Genre.query.get(g_id)
                if genre:
                    new_book.genres.append(genre)

            db.session.add(new_book)
            db.session.flush() # Получаем ID книги до коммита

            # Обработка обложки и MD5
            file_contents = cover_file.read()
            md5_hash = hashlib.md5(file_contents).hexdigest()
            cover_file.seek(0)

            existing_cover = Cover.query.filter_by(md5_hash=md5_hash).first()
            
            if existing_cover:
                # Если хэш совпал, используем существующий файл
                new_cover = Cover(filename=existing_cover.filename, mime_type=cover_file.content_type, md5_hash=md5_hash, book_id=new_book.id)
            else:
                # Иначе сохраняем новый файл, имя файла = MD5 хэш + расширение
                ext = os.path.splitext(secure_filename(cover_file.filename))[1]
                filename = f"{md5_hash}{ext}"
                
                if not os.path.exists(app.config['UPLOAD_FOLDER']):
                    os.makedirs(app.config['UPLOAD_FOLDER'])
                    
                cover_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                new_cover = Cover(filename=filename, mime_type=cover_file.content_type, md5_hash=md5_hash, book_id=new_book.id)

            db.session.add(new_cover)
            db.session.commit()
            
            flash("Книга успешно добавлена!", "success")
            return redirect(url_for('view_book', book_id=new_book.id))

        except Exception as e:
            db.session.rollback()
            flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")
    
    return render_template('book_form.html', genres=genres, action="add")

@app.route('/book/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    if current_user.role.name not in ['administrator', 'moderator']:
        flash("У вас недостаточно прав для выполнения данного действия.", "danger")
        return redirect(url_for('index'))
    
    book = Book.query.get_or_404(book_id)
    genres = Genre.query.all()
    
    if request.method == 'POST':
        try:
            book.title = request.form.get('title')
            book.description = request.form.get('description')
            book.year = int(request.form.get('year'))
            book.publisher = request.form.get('publisher')
            book.author = request.form.get('author')
            book.pages = int(request.form.get('pages'))
            
            genre_ids = request.form.getlist('genres')
            book.genres = []
            for g_id in genre_ids:
                genre = Genre.query.get(g_id)
                if genre:
                    book.genres.append(genre)
            
            db.session.commit()
            flash("Данные книги успешно обновлены.", "success")
            return redirect(url_for('view_book', book_id=book.id))
        except Exception:
            db.session.rollback()
            flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")

    return render_template('book_form.html', book=book, genres=genres, action="edit")

@app.route('/book/<int:book_id>/delete', methods=['POST'])
@login_required
def delete_book(book_id):
    if current_user.role.name != 'administrator':
        flash("У вас недостаточно прав для выполнения данного действия.", "danger")
        return redirect(url_for('index'))
    
    book = Book.query.get_or_404(book_id)
    try:
        # Удаление файла обложки, если на него больше никто не ссылается
        cover = Cover.query.filter_by(book_id=book.id).first()
        if cover:
            other_uses = Cover.query.filter_by(filename=cover.filename).count()
            if other_uses <= 1:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], cover.filename)
                if os.path.exists(file_path):
                    os.remove(file_path)

        db.session.delete(book)
        db.session.commit()
        flash(f"Книга «{book.title}» успешно удалена.", "success")
    except Exception:
        db.session.rollback()
        flash("Ошибка при удалении книги.", "danger")
        
    return redirect(url_for('index'))

@app.route('/book/<int:book_id>')
def view_book(book_id):
    book = Book.query.get_or_404(book_id)
    reviews = Review.query.filter_by(book_id=book.id).order_by(Review.created_at.desc()).all()
    
    # Расчет средней оценки
    avg_rating = 0
    if reviews:
        avg_rating = sum([r.rating for r in reviews]) / len(reviews)
    
    user_review = None
    user_collections = []
    if current_user.is_authenticated:
        user_review = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()
        if current_user.role.name == 'user':
            user_collections = Collection.query.filter_by(user_id=current_user.id).all()

    return render_template('book_view.html', book=book, reviews=reviews, avg_rating=round(avg_rating, 2), user_review=user_review, user_collections=user_collections)

@app.route('/book/<int:book_id>/review', methods=['GET', 'POST'])
@login_required
def add_review(book_id):
    book = Book.query.get_or_404(book_id)
    
    existing_review = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()
    if existing_review:
        flash("Вы уже оставили рецензию на эту книгу.", "warning")
        return redirect(url_for('view_book', book_id=book.id))
        
    if request.method == 'POST':
        try:
            rating = int(request.form.get('rating'))
            text = request.form.get('text')
            
            if not text:
                flash("Текст рецензии не может быть пустым.", "danger")
                return render_template('review_form.html', book=book)
                
            new_review = Review(book_id=book.id, user_id=current_user.id, rating=rating, text=text)
            db.session.add(new_review)
            db.session.commit()
            flash("Рецензия успешно добавлена.", "success")
            return redirect(url_for('view_book', book_id=book.id))
        except Exception:
            db.session.rollback()
            flash("Ошибка при сохранении рецензии.", "danger")
            
    return render_template('review_form.html', book=book)

# --- ВАРИАНТ 2: МАРШРУТЫ ДЛЯ ПОДБОРОК ---

@app.route('/collections')
@login_required
def collections():
    if current_user.role.name != 'user':
        flash("У вас недостаточно прав для выполнения данного действия.", "danger")
        return redirect(url_for('index'))
    user_collections = Collection.query.filter_by(user_id=current_user.id).all()
    return render_template('collections.html', collections=user_collections)

@app.route('/collections/add', methods=['POST'])
@login_required
def add_collection():
    if current_user.role.name != 'user':
        flash("У вас недостаточно прав для выполнения данного действия.", "danger")
        return redirect(url_for('index'))
    
    name = request.form.get('name')
    if name:
        try:
            new_collection = Collection(name=name, user_id=current_user.id)
            db.session.add(new_collection)
            db.session.commit()
            flash("Подборка успешно создана!", "success")
        except Exception:
            db.session.rollback()
            flash("Ошибка при создании подборки.", "danger")
    return redirect(url_for('collections'))

@app.route('/collections/<int:collection_id>')
@login_required
def view_collection(collection_id):
    if current_user.role.name != 'user':
        flash("У вас недостаточно прав.", "danger")
        return redirect(url_for('index'))
    collection = Collection.query.get_or_404(collection_id)
    if collection.user_id != current_user.id:
        abort(403)
    return render_template('index.html', books=collection.books, collection_title=collection.name)

@app.route('/book/<int:book_id>/add_to_collection', methods=['POST'])
@login_required
def add_to_collection(book_id):
    if current_user.role.name != 'user':
        flash("У вас недостаточно прав.", "danger")
        return redirect(url_for('index'))
    
    book = Book.query.get_or_404(book_id)
    collection_id = request.form.get('collection_id')
    collection = Collection.query.get_or_404(collection_id)
    
    if collection.user_id != current_user.id:
        abort(403)
        
    if book not in collection.books:
        collection.books.append(book)
        db.session.commit()
        flash("Книга успешно добавлена в подборку.", "success")
    else:
        flash("Книга уже находится в этой подборке.", "warning")
        
    return redirect(url_for('view_book', book_id=book.id))

# --- АУТЕНТИФИКАЦИЯ ---

from flask_login import login_user, logout_user
from werkzeug.security import check_password_hash

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_data = request.form.get('login')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter_by(login=login_data).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            flash("Успешный вход в систему.", "success")
            return redirect(url_for('index'))
        
        flash("Невозможно аутентифицироваться с указанными логином и паролем", "danger")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Создаст таблицы, если их нет
    app.run(debug=True)