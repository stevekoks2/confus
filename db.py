import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host="95.139.188.102",
        user="confus",
        password="QO?p#&(6>~-:",
        database="confus"
    )