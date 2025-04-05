import os
import glob
from app import app
from flask import render_template, request, redirect, url_for, session, jsonify
from db import get_db_connection
from datetime import datetime
import pytz
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError

# Установка часового пояса (например, Москва)
moscow_tz = pytz.timezone('Europe/Moscow')


@app.route('/')
def index():
    # Проверка сессии
    if 'user_id' in session:
        # Пользователь в сессии
        user_id = session['user_id']  # Айди по сессии
        avatar_path = f"static/avatar/{user_id}.*"  # Путь к аватаркам
        avatar_files = glob.glob(avatar_path)  # Возвращение аватарок
        if avatar_files:
            # Если есть аватарка, даём путь
            user_avatar = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}")
        else:
            # Если нет, ставим дефолтную
            user_avatar = url_for('static', filename='avatar/default_avatar.jpg')
    else:
        # Если пользователь не в сессии, возвращаем его на логин
        return redirect(url_for('login'))

    return render_template('index.html', user_avatar=user_avatar, user_id=user_id)

@app.route('/create_post', methods=['POST'])
def create_post():
    # Проверка наличия сессии
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Необходима авторизация'}), 401

    # Получаем данные из JSON
    data = request.get_json()
    caption = data.get('caption')
    author_id = session['user_id']

    # Подключение к базе данных
    connection = get_db_connection()
    cursor = connection.cursor()

    # Вставка данных поста в таблицу posts
    cursor.execute("""
        INSERT INTO posts (author_id, caption)
        VALUES (%s, %s)
    """, (author_id, caption))

    # Фиксация изменений и закрытие соединения
    connection.commit()
    cursor.close()
    connection.close()

    # Возвращаем JSON-ответ
    return jsonify({
        'success': True,
        'post': {
            'author_id': author_id,
            'author_name': session.get('username'),
            'author_avatar': url_for('static', filename=f"avatar/{author_id}.jpg"),
            'date': datetime.now().isoformat(),
            'caption': caption,
            'comments_count': 0,
            'likes_count': 0
        }
    })


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


@app.route('/get_new_posts', methods=['GET'])
def get_new_posts():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Получаем ID текущего пользователя (если он авторизован)
    user_id = session.get('user_id')

    # Запрос для получения постов
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
        ORDER BY posts.date DESC
    """)
    posts = cursor.fetchall()

    # Для каждого поста проверяем, лайкнул ли его текущий пользователь
    for post in posts:
        post_date = post['date']
        if isinstance(post_date, datetime):
            utc_date = pytz.utc.localize(post_date)
            local_date = utc_date.astimezone(moscow_tz)
            post['date'] = local_date.isoformat()

        # Проверка лайка
        if user_id:
            cursor.execute("""
                SELECT id FROM likes WHERE user_id = %s AND post_id = %s
            """, (user_id, post['id']))
            like = cursor.fetchone()
            post['is_liked'] = like is not None
        else:
            post['is_liked'] = False

        # Проверка аватарки
        avatar_path = f"static/avatar/{post['author_id']}.*"
        avatar_files = glob.glob(avatar_path)
        if avatar_files:
            post['author_avatar'] = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}")
        else:
            post['author_avatar'] = url_for('static', filename='avatar/default_avatar.jpg')

    cursor.close()
    connection.close()

    return jsonify(posts)

from flask import request, render_template

@app.route('/profile/<int:user_id>', methods=['GET'])
def profile(user_id):
    # Подключение к базе данных
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Запрос данных пользователя по ID
    cursor.execute("""
        SELECT 
            id, 
            username, 
            description, 
            avatar
        FROM 
            users 
        WHERE 
            id = %s
    """, (user_id,))
    user = cursor.fetchone()
    if 'user_id' in session:
            #пользователь в сессии
            user_id = session['user_id'] #айди по сессии
            avatar_path = f"static/avatar/{user_id}.*" #путь к аватаркам
            avatar_files = glob.glob(avatar_path) #возвращение аватарок
            if avatar_files:
                #если есть аватарка даём путь
                user_avatar = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}")
            else:
                #если нет, ставим дефолтную
                user_avatar = url_for('static', filename='avatar/default_avatar.jpg')
    if user:
        # Подсчет количества подписчиков
        cursor.execute("""
            SELECT 
                COUNT(*) AS followers_count
            FROM 
                followers 
            WHERE 
                user_id = %s
        """, (user_id,))
        followers_count = cursor.fetchone()['followers_count']
        user['followers_count'] = followers_count

        # Проверка наличия аватарки в папке /static/avatar/
        avatar_path = f"static/avatar/{user['id']}.*"
        avatar_files = glob.glob(avatar_path)
        if avatar_files:
            user['avatar'] = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}")
        else:
            user['avatar'] = url_for('static', filename='avatar/default_avatar.jpg')  # Дефолтная аватарка

        # Проверка наличия фонового изображения в папке /static/background/
        background_path = f"static/background/{user['id']}.*"
        background_files = glob.glob(background_path)
        if background_files:
            user['background'] = url_for('static', filename=f"background/{os.path.basename(background_files[0])}")
        else:
            user['background'] = url_for('static', filename='background/default_background.png')  # Дефолтное фоновое изображение

        # Закрытие соединения с базой данных
        cursor.close()
        connection.close()

        return render_template('profile.html', user=user, user_id=user_id, user_avatar=user_avatar)
    else:
        # Закрытие соединения с базой данных
        cursor.close()
        connection.close()
        return "Пользователь не найден", 404
    


@app.route('/like_post', methods=['POST'])
def like_post():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Необходима авторизация'}), 401

    data = request.get_json()
    print(f"Request data: {data}")  # Логируем данные запроса

    # Проверяем CSRF-токен
    csrf_token = data.get('csrf_token')
    if not csrf_token:
        return jsonify({'success': False, 'message': 'CSRF-токен отсутствует'}), 400

    try:
        validate_csrf(csrf_token)  # Проверяем CSRF-токен
    except ValidationError:
        return jsonify({'success': False, 'message': 'Неверный CSRF-токен'}), 400

    post_id = data.get('post_id')
    user_id = session['user_id']

    print(f"Received like request: user_id={user_id}, post_id={post_id}")  # Логируем данные

    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'message': 'Ошибка подключения к базе данных'}), 500

    cursor = connection.cursor()

    try:
        # Проверяем, не поставил ли пользователь уже лайк
        cursor.execute("""
            SELECT * FROM likes WHERE user_id = %s AND post_id = %s
        """, (user_id, post_id))
        existing_like = cursor.fetchone()
        print(f"Existing like: {existing_like}")  # Логируем результат проверки

        if existing_like:
            # Если лайк уже есть, удаляем его
            cursor.execute("""
                DELETE FROM likes WHERE user_id = %s AND post_id = %s
            """, (user_id, post_id))
            action = 'unlike'
            print("Like removed")  # Логируем удаление лайка
        else:
            # Если лайка нет, добавляем его
            cursor.execute("""
                INSERT INTO likes (user_id, post_id) VALUES (%s, %s)
            """, (user_id, post_id))
            action = 'like'
            print("Like added")  # Логируем добавление лайка

        # Обновляем количество лайков в таблице posts
        cursor.execute("""
            UPDATE posts SET likes_count = (
                SELECT COUNT(*) FROM likes WHERE post_id = %s
            ) WHERE id = %s
        """, (post_id, post_id))
        print("Likes count updated")  # Логируем обновление количества лайков

        connection.commit()
    except Exception as e:
        print(f"Database error: {e}")  # Логируем ошибку
        connection.rollback()
        return jsonify({'success': False, 'message': 'Ошибка базы данных'}), 500
    finally:
        cursor.close()
        connection.close()

    return jsonify({'success': True, 'action': action})



@app.route('/editor')
def editor():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Получаем данные текущего пользователя
    cursor.execute("""
        SELECT id, username, description, avatar 
        FROM users 
        WHERE id = %s
    """, (user_id,))
    user = cursor.fetchone()
    
    if user:
        # Проверяем аватар
        avatar_path = f"static/avatar/{user_id}.*"
        avatar_files = glob.glob(avatar_path)
        if avatar_files:
            user['avatar'] = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}")
        else:
            user['avatar'] = url_for('static', filename='avatar/default_avatar.jpg')
        
        # Проверяем фон
        background_path = f"static/background/{user_id}.*"
        background_files = glob.glob(background_path)
        if background_files:
            user['background'] = url_for('static', filename=f"background/{os.path.basename(background_files[0])}")
        else:
            user['background'] = url_for('static', filename='background/default_background.png')
    
    cursor.close()
    connection.close()
    
    return render_template('editor.html', user=user)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    username = request.form.get('username')
    description = request.form.get('description')
    avatar = request.files.get('avatar')
    background = request.files.get('background')
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Обновляем основные данные
        cursor.execute("""
            UPDATE users 
            SET username = %s, description = %s 
            WHERE id = %s
        """, (username, description, user_id))
        
        # Сохраняем аватар, если он был загружен
        if avatar and avatar.filename:
            avatar_ext = os.path.splitext(avatar.filename)[1]
            avatar_path = f"static/avatar/{user_id}{avatar_ext}"
            
            # Удаляем старые аватары
            old_avatars = glob.glob(f"static/avatar/{user_id}.*")
            for old_avatar in old_avatars:
                os.remove(old_avatar)
            
            avatar.save(avatar_path)
        
        # Сохраняем фон, если он был загружен
        if background and background.filename:
            background_ext = os.path.splitext(background.filename)[1]
            background_path = f"static/background/{user_id}{background_ext}"
            
            # Удаляем старые фоны
            old_backgrounds = glob.glob(f"static/background/{user_id}.*")
            for old_background in old_backgrounds:
                os.remove(old_background)
            
            background.save(background_path)
        
        connection.commit()
        return redirect(url_for('profile', user_id=user_id))
    except Exception as e:
        connection.rollback()
        return str(e), 500
    finally:
        cursor.close()
        connection.close()