from app import app
from flask import render_template
from db import get_db_connection

@app.route('/')
def index():
    # Подключение к базе данных
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Запрос данных из таблицы posts
    cursor.execute("SELECT id, user_id, content, username, created_at FROM posts")
    posts = cursor.fetchall()

    # Закрытие соединения с базой данных
    cursor.close()
    connection.close()

    # Передача данных в шаблон
    return render_template('index.html', posts=posts)


@app.route('/reg')
def reg():
    return render_template('reg.html')
