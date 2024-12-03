import os
import glob
from app import app
from flask import render_template, request, redirect, url_for, session
from db import get_db_connection
from datetime import datetime
import pytz
from werkzeug.security import generate_password_hash, check_password_hash

# Установка часового пояса (например, Москва)
moscow_tz = pytz.timezone('Europe/Moscow')

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # Подключение к базе данных
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Запрос данных из таблицы posts
    cursor.execute("""
        SELECT 
            posts.id, 
            posts.author_id, 
            posts.date, 
            posts.caption, 
            posts.attachment, 
            posts.likes_count, 
            posts.comments_count, 
            users.username AS author_name, 
            users.avatar AS author_avatar
        FROM 
            posts 
        JOIN 
            users 
        ON 
            posts.author_id = users.id
    """)
    posts = cursor.fetchall()

    # Закрытие соединения с базой данных
    cursor.close()
    connection.close()

    posts.sort(key=lambda x: x['date'], reverse=True)
    # Преобразование времени из UTC в нужный часовой пояс
    for post in posts:
        post_date = post['date']
        if isinstance(post_date, datetime):
            # Предполагаем, что время в базе данных хранится в UTC
            utc_date = pytz.utc.localize(post_date)
            local_date = utc_date.astimezone(moscow_tz)
            post['date'] = local_date


    # Проверка наличия аватарки в папке /static/avatar/
        avatar_path = f"static/avatar/{post['author_id']}.*"
        avatar_files = glob.glob(avatar_path)
        if avatar_files:
            post['author_avatar'] = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}")
        else:
            post['author_avatar'] = url_for('static', filename='avatar/default_avatar.jpg')  # Дефолтная аватарка
        # Сортировка постов по дате в обратном порядке
            # Получение аватарки текущего пользователя
    user_avatar = url_for('static', filename='avatar/default_avatar.jpg')  # Дефолтная аватарка
    if 'user_id' in session:
        user_id = session['user_id']
        avatar_path = f"static/avatar/{user_id}.*"
        avatar_files = glob.glob(avatar_path)
        if avatar_files:
            user_avatar = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}")

    # Передача данных в шаблон
    return render_template('index.html', posts=posts, user_avatar=user_avatar)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Получаем данные из формы
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Хешируем пароль
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Подключение к базе данных
        connection = get_db_connection()
        cursor = connection.cursor()

        # Вставка данных пользователя в таблицу users
        cursor.execute("""
            INSERT INTO users (username, email, password)
            VALUES (%s, %s, %s)
        """, (username, email, hashed_password))

        # Фиксация изменений и закрытие соединения
        connection.commit()
        cursor.close()
        connection.close()

        # Перенаправление на страницу входа
        return redirect(url_for('login'))
    

    # Если метод GET, просто отображаем форму
    return render_template('reg.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Получаем данные из формы
        username = request.form['username']
        password = request.form['password']

        # Подключение к базе данных
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Проверка наличия пользователя в базе данных
        cursor.execute("""
            SELECT * FROM users WHERE username = %s
        """, (username,))
        user = cursor.fetchone()

        # Закрытие соединения с базой данных
        cursor.close()
        connection.close()

        # Проверка пароля
        if user and check_password_hash(user['password'], password):
            # Устанавливаем сессию
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            # Если данные неверны, возвращаем сообщение об ошибке
            return "Неверный логин или пароль"

    # Если метод GET, просто отображаем форму
    return render_template('login.html')