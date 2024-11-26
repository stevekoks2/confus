import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host="95.139.232.191",
        user="larisa",
        password="password",
        database="confusdb"
    )