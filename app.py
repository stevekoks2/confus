from flask import Flask, request, render_template, redirect, url_for
from config import Configuratrion
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'JAZZ_MALE'
app.config.from_object(Configuratrion)
