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
import json  # Добавьте этот импорт
from werkzeug.utils import secure_filename

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



# Настройки загрузки файлов
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/create_post', methods=['POST'])
def create_post():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Необходима авторизация'}), 401

    try:
        caption = request.form.get('caption', '')
        author_id = session['user_id']
        media_files = request.files.getlist('media')
        media_data = []

        # Обработка медиафайлов
        UPLOAD_FOLDER = 'static/uploads'
        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)

        for file in media_files:
            if file and '.' in file.filename:
                ext = file.filename.rsplit('.', 1)[1].lower()
                if ext in ALLOWED_EXTENSIONS:
                    filename = secure_filename(f"{author_id}_{int(datetime.now().timestamp())}.{ext}")
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    file.save(filepath)
                    
                    file_type = f"image/{ext}" if ext in {'png', 'jpg', 'jpeg', 'gif'} else f"video/{ext}"
                    media_data.append({
                        'url': url_for('static', filename=f'uploads/{filename}'),
                        'type': file_type
                    })

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)  # Убедитесь, что используете правильный курсор

        # Вставка нового поста
        cursor.execute("""
            INSERT INTO posts (author_id, caption, media)
            VALUES (%s, %s, %s)
        """, (
            author_id, 
            caption, 
            json.dumps(media_data) if media_data else None
        ))
        
        post_id = cursor.lastrowid
        
        # Получаем данные о посте
        cursor.execute("""
            SELECT date, likes_count, comments_count 
            FROM posts 
            WHERE id = %s
        """, (post_id,))
        post_data = cursor.fetchone()
        
        connection.commit()

        return jsonify({
            'success': True,
            'post': {
                'id': post_id,
                'author_id': author_id,
                'author_name': session.get('username'),
                'author_avatar': url_for('static', filename=f"avatar/{author_id}.jpg"),
                'date': post_data['date'].isoformat(),  # Теперь можно обращаться по ключу
                'caption': caption,
                'media': media_data,
                'comments_count': post_data['comments_count'],
                'likes_count': post_data['likes_count']
            }
        })

    except Exception as e:
        print(f"Error creating post: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'connection' in locals(): connection.close()

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


from datetime import datetime, timedelta  # Добавьте этот импорт в начало файла

@app.route('/get_new_posts')
def get_new_posts():
    try:
        # Проверка авторизации
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Требуется авторизация'}), 401

        # Получаем параметр фильтра
        filter_type = request.args.get('filter', 'all')
        user_id = session['user_id']
        time_filter = datetime.now() - timedelta(hours=12)
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'success': False, 'message': 'Ошибка подключения к БД'}), 500

        cursor = connection.cursor(dictionary=True)

        # Основной запрос с учетом медиа-контента
        base_query = """
            SELECT 
                p.id, p.author_id, p.date, p.caption,
                p.likes_count, p.comments_count, p.media,
                u.username AS author_name,
                u.avatar AS author_avatar,
                EXISTS(
                    SELECT 1 FROM likes l 
                    WHERE l.post_id = p.id AND l.user_id = %s
                ) AS is_liked
            FROM posts p
            JOIN users u ON p.author_id = u.id
        """

        # Добавляем условия фильтрации
        if filter_type == 'popular':
            query = base_query + """
                WHERE p.date >= %s
                ORDER BY p.likes_count DESC, p.date DESC
                LIMIT 50
            """
            params = (user_id, time_filter)
        elif filter_type == 'discussed':
            query = base_query + """
                WHERE p.date >= %s
                ORDER BY p.comments_count DESC, p.date DESC
                LIMIT 50
            """
            params = (user_id, time_filter)
        else:  # 'all' и 'recent'
            query = base_query + """
                ORDER BY p.date DESC
                LIMIT 50
            """
            params = (user_id,)

        cursor.execute(query, params)
        posts = cursor.fetchall()

        # Обработка результатов
        processed_posts = []
        for post in posts:
            # Обработка медиа-контента
            try:
                post['media'] = json.loads(post['media']) if post['media'] else []
            except (TypeError, json.JSONDecodeError):
                post['media'] = []

            # Форматирование даты
            if isinstance(post['date'], datetime):
                utc_date = pytz.utc.localize(post['date'])
                local_date = utc_date.astimezone(moscow_tz)
                post['date'] = local_date.isoformat()

            # Проверка аватарки автора
            avatar_path = f"static/avatar/{post['author_id']}.*"
            avatar_files = glob.glob(avatar_path)
            post['author_avatar'] = (
                url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}")
                if avatar_files 
                else url_for('static', filename='avatar/default_avatar.jpg')
            )

            processed_posts.append(post)

        return jsonify(processed_posts)

    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({'success': False, 'message': f'Ошибка базы данных: {str(e)}'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()

from flask import request, render_template

@app.route('/profile/<int:user_id>', methods=['GET'])
def profile(user_id):
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
    
    # Проверка аватарки текущего пользователя (из сессии)
    user_avatar = None
    if 'user_id' in session:
        session_user_id = session['user_id']
        avatar_path = f"static/avatar/{session_user_id}.*"
        avatar_files = glob.glob(avatar_path)
        if avatar_files:
            user_avatar = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}")
        else:
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

        # Проверка аватарки
        avatar_path = f"static/avatar/{user['id']}.*"
        avatar_files = glob.glob(avatar_path)
        if avatar_files:
            user['avatar'] = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}")
        else:
            user['avatar'] = url_for('static', filename='avatar/default_avatar.jpg')

        # Проверка фона
        background_path = f"static/background/{user['id']}.*"
        background_files = glob.glob(background_path)
        if background_files:
            user['background'] = url_for('static', filename=f"background/{os.path.basename(background_files[0])}")
        else:
            user['background'] = url_for('static', filename='background/default_background.png')

        # Проверка, является ли профиль профилем текущего пользователя
        is_own_profile = False
        if 'user_id' in session and session['user_id'] == user['id']:
            is_own_profile = True

        cursor.close()
        connection.close()

        return render_template(
            'profile.html', 
            user=user, 
            user_id=user_id, 
            user_avatar=user_avatar,
            is_own_profile=is_own_profile
        )
    else:
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
    description = request.form.get('description')
    avatar = request.files.get('avatar')
    background = request.files.get('background')
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Обновляем основные данные
        cursor.execute("""
            UPDATE users 
            SET description = %s 
            WHERE id = %s
        """, (description, user_id))
        
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

@app.route('/post/<int:post_id>')
def post_details(post_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Получаем данные текущего пользователя для шапки
    user_id = session['user_id']
    avatar_path = f"static/avatar/{user_id}.*"
    avatar_files = glob.glob(avatar_path)
    user_avatar = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}") if avatar_files else url_for('static', filename='avatar/default_avatar.jpg')

    return render_template('post_details.html', 
                         post_id=post_id,
                         user_avatar=user_avatar,
                         user_id=user_id)

@app.route('/get_post_comments/<int:post_id>')
def get_post_comments(post_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Получаем сам пост
    cursor.execute("""
        SELECT 
            posts.*, 
            users.username AS author_name,
            users.avatar AS author_avatar
        FROM posts
        JOIN users ON posts.author_id = users.id
        WHERE posts.id = %s
    """, (post_id,))
    post = cursor.fetchone()

    # Получаем комментарии
    cursor.execute("""
        SELECT 
            comments.*, 
            users.username AS author_name,
            users.avatar AS author_avatar
        FROM comments
        JOIN users ON comments.user_id = users.id
        WHERE comments.post_id = %s
        ORDER BY comments.date ASC
    """, (post_id,))
    comments = cursor.fetchall()

    # Форматируем данные
    if post:
        # Обработка аватарки автора поста
        avatar_path = f"static/avatar/{post['author_id']}.*"
        avatar_files = glob.glob(avatar_path)
        post['author_avatar'] = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}") if avatar_files else url_for('static', filename='avatar/default_avatar.jpg')

        # Форматирование даты
        if isinstance(post['date'], datetime):
            utc_date = pytz.utc.localize(post['date'])
            local_date = utc_date.astimezone(moscow_tz)
            post['date'] = local_date.strftime('%d.%m.%Y %H:%M')

    for comment in comments:
        # Обработка аватарок комментаторов
        avatar_path = f"static/avatar/{comment['user_id']}.*"
        avatar_files = glob.glob(avatar_path)
        comment['author_avatar'] = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}") if avatar_files else url_for('static', filename='avatar/default_avatar.jpg')

        # Форматирование даты
        if isinstance(comment['date'], datetime):
            utc_date = pytz.utc.localize(comment['date'])
            local_date = utc_date.astimezone(moscow_tz)
            comment['date'] = local_date.strftime('%d.%m.%Y %H:%M')

    cursor.close()
    connection.close()

    return jsonify({
        'post': post,
        'comments': comments
    })

@app.route('/add_comment', methods=['POST'])
def add_comment():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Необходима авторизация'}), 401

    data = request.get_json()
    post_id = data.get('post_id')
    text = data.get('text')
    user_id = session['user_id']

    if not text or not post_id:
        return jsonify({'success': False, 'message': 'Неверные данные'}), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Добавляем комментарий
        cursor.execute("""
            INSERT INTO comments (post_id, user_id, text)
            VALUES (%s, %s, %s)
        """, (post_id, user_id, text))

        # Обновляем счетчик комментариев в посте
        cursor.execute("""
            UPDATE posts SET comments_count = comments_count + 1
            WHERE id = %s
        """, (post_id,))

        # Получаем данные нового комментария
        cursor.execute("""
            SELECT 
                comments.*,
                users.username AS author_name,
                users.avatar AS author_avatar
            FROM comments
            JOIN users ON comments.user_id = users.id
            WHERE comments.id = LAST_INSERT_ID()
        """)
        new_comment = cursor.fetchone()

        # Форматируем данные
        avatar_path = f"static/avatar/{new_comment['user_id']}.*"
        avatar_files = glob.glob(avatar_path)
        new_comment['author_avatar'] = url_for('static', filename=f"avatar/{os.path.basename(avatar_files[0])}") if avatar_files else url_for('static', filename='avatar/default_avatar.jpg')

        if isinstance(new_comment['date'], datetime):
            utc_date = pytz.utc.localize(new_comment['date'])
            local_date = utc_date.astimezone(moscow_tz)
            new_comment['date'] = local_date.strftime('%d.%m.%Y %H:%M')

        connection.commit()

        return jsonify({
            'success': True,
            'comment': new_comment
        })

    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        connection.close()
