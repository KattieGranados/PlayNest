from flask import Flask, render_template, request, redirect, url_for, session
# bcrypt is a hashing library used to securely hash passwords
# instead of storing passwords directly in the database, we store a hash of the password so that if the database is compromised,
# attackers wont have access to the actual user passwords
# make sure virtual environment is activated, then run pip install Flask-Bcrypt to install bcrypt
from flask_bcrypt import Bcrypt
from models import db, User, Forum, Thread, Comment

# run pip install python-dotenv to install
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# DB connection
app.config['SQLALCHEMY_DATABASE_URI'] = \
    f'postgresql://{os.getenv("DB_USER")}:{os.getenv("DB_PASS")}@{os.getenv("DB_HOST")}:{os.getenv("DB_PORT")}/{os.getenv("DB_NAME")}'
db.init_app(app) # initializing database with the flask app

bcrypt = Bcrypt(app)

@app.get('/')
def index():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            session['username'] = username
            return redirect(url_for('home'))
        else: 
            return "Invalid credentials"

    # If it's a GET request, render the login form
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm-password']
        
        # validation for password confirmation
        if password != confirm_password:
            return "Passwords do not match."
        
        # checking if username already exists in database
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return "Username already in use. Please choose a different one."
        
        # checking if email already exists in database
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            return "Email already in use. Please use a different one."
        
        # hash password before storing it
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # creating a new user and inserting it into the database
        new_user = User(username=username, email=email, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        # redirecting to log in page after sign up
        return redirect(url_for('login'))
    
# render the sign up form if GET request
    return render_template('signup.html')

@app.get('/home')
def home():
    return render_template('home.html')

@app.get('/logout')
def logout():
    # clear username from session
    session.pop('username', None)
    return redirect(url_for('index'))

@app.get('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.get('/settings')
def settings():
    return render_template('settings.html')

@app.get('/forum')
def forum():
    forums = Forum.query.all()
    return render_template('forum.html', forums=forums)

@app.route('/forum/<forum_slug>', methods=['GET', 'POST'])
def forum_threads(forum_slug):
    forum = Forum.query.filter_by(slug=forum_slug).first()
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        user_id = User.query.filter_by(username=session['username']).first().id
        
        new_thread = Thread(title=title, content=content, forum_id=forum.id, user_id=user_id)
        db.session.add(new_thread)
        db.session.commit()
        
    threads = Thread.query.filter_by(forum_id=forum.id).all()
    for thread in threads:
        thread.detail_url = url_for('thread_detail', forum_slug=forum.slug, thread_id=thread.id)

    return render_template('forum_threads.html', forum=forum, threads=threads)

@app.route('/forum/<forum_slug>/<int:thread_id>', methods=['GET', 'POST'])
def thread_detail(forum_slug, thread_id):
    forum = Forum.query.filter_by(slug=forum_slug).first()
    thread = Thread.query.get(thread_id)
    
    if request.method == 'POST':
        content = request.form['content']
        user_id = User.query.filter_by(username=session['username']).first().id
        
        new_comment = Comment(content=content, user_id=user_id, thread_id=thread.id)
        db.session.add(new_comment)
        db.session.commit()
        
    return render_template('thread_detail.html', forum=forum, thread=thread)

if __name__ == '__main__':
    app.run(debug=True)

