from flask import Flask, request, render_template, redirect, url_for
from config import Configuratrion
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.secret_key = 'JAZZ_MALE'
app.config.from_object(Configuratrion)
csrf = CSRFProtect(app)