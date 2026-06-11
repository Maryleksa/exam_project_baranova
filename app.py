# -*- coding: utf-8 -*-
import os
import hashlib
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user, login_user, logout_user
import markdown
import bleach
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash

from auth import login_manager
from models import db, Book, Genre, Cover, Review, User, Role, Collection

app = Flask(__name__)
app.config['SECRET_KEY'] = '1234qwer'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///electronic_library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['PER_PAGE'] = 10

# Инициализируем ЕДИНЫЙ экземпляр login_manager
login_manager.init_app(app)
db.init_app(app)

# Кастомный фильтр Markdown
@app.template_filter('markdown')
def markdown_filter(text):
    if text:
        clean_html = bleach.clean(markdown.markdown(text), tags=['p', 'ul', 'ol', 'li', 'strong', 'em', 'h1', 'h2', 'h3', 'br'])
        return clean_html
    return ''

def check_rights(action):
    if not current_user.is_authenticated:
        return False
    if action == 'delete':
        return current_user.role.name == 'administrator'
    if action in ['add', 'edit']:
        return current_user.role.name in ['administrator', 'moderator']
    return True

# --- РОУТЫ СИСТЕМЫ ---

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    pagination = Book.query.order_by(Book.year.desc()).paginate(page=page, per_page=app.config['PER_PAGE'], error_out=False)
    books = pagination.items
    
    # Если запрашивается конкретная подборка
    collection_id = request.args.get('collection_id', type=int)
    collection_title = None
    if collection_id:
        col = Collection.query.get_or_404(collection_id)
        books = col.books
        pagination = None
        collection_title = col.name

    return render_template('index.html', books=books, pagination=pagination, collection_title=collection_title)

@app.route('/books/add', methods=['GET', 'POST'])
@login_required
def add_book():
    if not check_rights('add'):
        flash("У вас недостаточно прав для выполнения данного действия.", "danger")
        return redirect(url_for('index'))
        
    genres = Genre.query.all()
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            description = bleach.clean(request.form.get('description'))
            year = int(request.form.get('year'))
            publisher = request.form.get('publisher')
            author = request.form.get('author')
            pages = int(request.form.get('pages'))
            genre_ids = request.form.getlist('genres')

            new_book = Book(title=title, description=description, year=year, publisher=publisher, author=author, pages=pages)
            for g_id in genre_ids:
                g = Genre.query.get(int(g_id))
                if g: new_book.genres.append(g)

            db.session.add(new_book)
            db.session.flush()

            # Работа с обложкой
            file = request.files.get('cover')
            if file:
                file_bytes = file.read()
                md5_hash = hashlib.md5(file_bytes).hexdigest()
                file.seek(0)

                existing_cover = Cover.query.filter_by(md5_hash=md5_hash).first()
                if existing_cover:
                    filename = existing_cover.filename
                    mime_type = existing_cover.mime_type
                else:
                    filename = secure_filename(file.filename)
                    mime_type = file.mimetype
                    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

                new_cover = Cover(filename=filename, mime_type=mime_type, md5_hash=md5_hash, book_id=new_book.id)
                db.session.add(new_cover)

            db.session.commit()
            flash("Книга успешно добавлена.", "success")
            return redirect(url_for('view_book', book_id=new_book.id))
        except Exception as e:
            db.session.rollback()
            flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")
            
    return render_template('book_form.html', action='add', genres=genres, book=None)

@app.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    if not check_rights('edit'):
        flash("У вас недостаточно прав для выполнения данного действия.", "danger")
        return redirect(url_for('index'))
        
    book = Book.query.get_or_404(book_id)
    genres = Genre.query.all()
    
    if request.method == 'POST':
        try:
            book.title = request.form.get('title')
            book.description = bleach.clean(request.form.get('description'))
            book.year = int(request.form.get('year'))
            book.publisher = request.form.get('publisher')
            book.author = request.form.get('author')
            book.pages = int(request.form.get('pages'))
            
            genre_ids = request.form.getlist('genres')
            book.genres = []
            for g_id in genre_ids:
                g = Genre.query.get(int(g_id))
                if g: book.genres.append(g)

            db.session.commit()
            flash("Данные книги успешно обновлены.", "success")
            return redirect(url_for('view_book', book_id=book.id))
        except Exception as e:
            db.session.rollback()
            flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")

    return render_template('book_form.html', action='edit', genres=genres, book=book)

@app.route('/books/<int:book_id>', methods=['GET'])
def view_book(book_id):
    book = Book.query.get_or_404(book_id)
    reviews = Review.query.filter_by(book_id=book.id).all()
    
    user_review = None
    if current_user.is_authenticated:
        user_review = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()

    collections = []
    if current_user.is_authenticated and current_user.role.name == 'user':
        collections = Collection.query.filter_by(user_id=current_user.id).all()

    return render_template('book_view.html', book=book, reviews=reviews, user_review=user_review, collections=collections)

@app.route('/books/<int:book_id>/delete', methods=['POST'])
@login_required
def delete_book(book_id):
    if not check_rights('delete'):
        flash("У вас недостаточно прав для выполнения данного действия.", "danger")
        return redirect(url_for('index'))
        
    book = Book.query.get_or_404(book_id)
    try:
        if book.covers:
            for cover in book.covers:
                # Проверяем, используется ли этот файл другими книгами перед удалением с диска
                other_uses = Cover.query.filter(Cover.filename == cover.filename, Cover.book_id != book.id).count()
                if other_uses == 0:
                    path = os.path.join(app.config['UPLOAD_FOLDER'], cover.filename)
                    if os.path.exists(path):
                        os.remove(path)
        
        db.session.delete(book)
        db.session.commit()
        flash("Книга успешно удалена.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Ошибка при удалении книги.", "danger")
        
    return redirect(url_for('index'))



# --- УПРАВЛЕНИЕ ПОДБОРКАМИ (ВАРИАНТ 2) ---

@app.route('/collections')
@login_required
def collections():
    # Ваша логика получения подборок
    user_collections = Collection.query.filter_by(user_id=current_user.id).all()
    return render_template('collections.html', collections=user_collections)

@app.route('/collections/create', methods=['POST'])
@login_required
def create_collection():
    name = request.form.get('name')
    if name:
        new_collection = Collection(name=name, user_id=current_user.id)
        db.session.add(new_collection)
        db.session.commit()
        flash("Подборка успешно создана!", "success")
    else:
        flash("Название подборки не может быть пустым.", "danger")
    return redirect(url_for('collections'))

@app.route('/books/<int:book_id>/add_to_collection', methods=['POST'])
@login_required
def add_to_collection(book_id): # Аргумент collection_id здесь не нужен, берем из формы
    collection_id = request.form.get('collection_id')
    if not collection_id:
        flash("Подборка не выбрана", "danger")
        return redirect(url_for('view_book', book_id=book_id))
        
    collection = Collection.query.get_or_404(collection_id)
    book = Book.query.get_or_404(book_id)
    
    if collection.user_id != current_user.id:
        abort(403)
        
    if book not in collection.books:
        collection.books.append(book)
        db.session.commit()
        flash("Книга успешно добавлена в подборку.", "success")
    else:
        flash("Книга уже находится в этой подборке.", "warning")
        
    return redirect(url_for('view_book', book_id=book_id))

# --- РАБОТА С ПОДБОРКАМИ ---

@app.route('/collections/<int:collection_id>')
def view_collection(collection_id):
    # Получаем подборку по ID
    from models import Collection, Book
    collection = Collection.query.get_or_404(collection_id)
    
    # Книги в подборке доступны через связь collection.books (убедитесь, что она есть в модели)
    return render_template('collection_view.html', collection=collection)

@app.route('/collections/delete/<int:collection_id>', methods=['POST'])
@login_required
def delete_collection(collection_id):
    collection = Collection.query.get_or_404(collection_id)
    if collection.user_id != current_user.id:
        abort(403)
    db.session.delete(collection)
    db.session.commit()
    flash("Подборка удалена.", "success")
    return redirect(url_for('collections'))

# --- РАБОТА С РЕЦЕНЗИЯМИ ---
@app.route('/books/<int:book_id>/add_review', methods=['GET', 'POST'])
@login_required
def add_review(book_id):
    book = Book.query.get_or_404(book_id)
    
    # Проверка, не оставлял ли пользователь уже отзыв
    existing_review = Review.query.filter_by(book_id=book_id, user_id=current_user.id).first()
    if existing_review:
        flash("Вы уже оставили рецензию на эту книгу.", "warning")
        return redirect(url_for('view_book', book_id=book_id))

    if request.method == 'POST':
        rating = request.form.get('rating')
        text = request.form.get('text')
        
        # Базовая валидация
        if not rating or not text:
            flash("Пожалуйста, заполните все поля.", "danger")
            return redirect(url_for('add_review', book_id=book_id))
        
        new_review = Review(
            book_id=book_id, 
            user_id=current_user.id, 
            rating=int(rating), 
            text=text
        )
        
        try:
            db.session.add(new_review)
            db.session.commit()
            flash("Рецензия успешно добавлена!", "success")
            return redirect(url_for('view_book', book_id=book_id))
        except Exception as e:
            db.session.rollback()
            flash("Произошла ошибка при сохранении рецензии.", "danger")
            
    return render_template('review_form.html', book=book)

# --- АУТЕНТИФИКАЦИЯ ---

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
    flash("Вы вышли из системы.", "success")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)