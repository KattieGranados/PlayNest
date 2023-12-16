from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort, send_from_directory
from werkzeug.utils import secure_filename
import zipfile
import shutil
# bcrypt is a hashing library used to securely hash passwords
# instead of storing passwords directly in the database, we store a hash of the password so that if the database is compromised,
# attackers wont have access to the actual user passwords
# make sure virtual environment is activated, then run pip install Flask-Bcrypt to install bcrypt
from flask_bcrypt import Bcrypt
from sqlalchemy import desc
from models import db, User, Forum, Thread, Comment, Review, Game, Profile, Like
# pip install requests
import requests

# pip install Flask-WTF
from flask_wtf import FlaskForm
from wtforms import TextAreaField, SelectField, SubmitField, validators, ValidationError
from wtforms.validators import DataRequired

# beautifulsoup4: python package for parsing HTML
# I had an issue where the game descriptions from the API were displaying html elements in the text,
# like <p> and <br> were showing. So I used this package to remove that.
# pip install beautifulsoup4
from bs4 import BeautifulSoup

# run pip install python-dotenv to install
from dotenv import load_dotenv
import os

from os import listdir
from os.path import isfile, join

load_dotenv()

app = Flask(__name__)

app.secret_key = 'your_secret_key'

# DB connection
database_url = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
db.init_app(app) # initializing database with the flask app

bcrypt = Bcrypt(app)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Allowed cover image extensions
ALLOWED_COVER_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
# Allowed game file extensions
ALLOWED_GAME_EXTENSIONS = {'zip'}

# This stuff is for Godot 4 support, but we're not doing that anymore,
# so just ignore it
#
#@app.after_request
#def add_cors_headers(response):
#   response.headers['Cross-Origin-Embedder-Policy'] = 'credentialless'
#   response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
#
#   return response

def get_game_details_from_rawg_api(game_id):
    API_KEY = os.getenv('API_KEY')
    base_url = f'https://api.rawg.io/api/games/{game_id}'
    
    params = {
        'key': API_KEY,
    }
    
    try:
        response = requests.get(base_url, params=params)
        
        if response.status_code == 200:
            game_data = response.json()
            
            if 'description' in game_data:
                game_data['description'] = strip_html_tags(game_data['description'])

            return game_data
        else:
            print(f"Error: Unable to fetch game details from RAWG API. Status code: {response.status_code}")
            return None
    except requests.RequestException as e:
        print(f"Error: {e}")
        return None

@app.get('/')
def home():
    # retrieve most recent threads from all forums and recent reviews posted
    recent_threads = Thread.query.order_by(desc(Thread.created_at)).limit(4).all()
    recent_reviews = Review.query.order_by(desc(Review.created_at)).limit(4).all()
    recent_games = Game.query.order_by(desc(Game.release_date)).limit(4).all()

    for thread in recent_threads:
        thread.detail_url = url_for('thread_detail', forum_slug=thread.forum.slug, thread_id=thread.id)

    for review in recent_reviews:
        review.detail_url = url_for('game_details', game_id=review.game_identifier)

    for game in recent_games:
        game.detail_url = url_for('game_detail', game_id=game.game_id)

    return render_template('home.html', recent_threads=recent_threads, recent_reviews=recent_reviews, recent_games=recent_games, get_game_details_from_rawg_api=get_game_details_from_rawg_api)

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

@app.get('/logout')
def logout():
    # clear username from session
    session.pop('username', None)
    return redirect(url_for('home'))

def find_index_html(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # Get a list of all files in the ZIP archive
        file_list = zip_ref.namelist()
        
        # Search for index.html in all files
        for file in file_list:
            if file.lower().endswith('index.html'):
                return file
        
        return None

def allowed_game_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_GAME_EXTENSIONS

def allowed_cover_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_COVER_EXTENSIONS

@app.route('/dashboard', methods=['GET','POST'])
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    else:
        user = User.query.filter_by(username=session['username']).first()

    if request.method == 'POST':
        title = request.form['title']

        # Cover image file handler
        if 'cover-image' not in request.files:
            return redirect(request.url)
        
        cover_file = request.files['cover-image']

        if cover_file and allowed_cover_file(cover_file.filename):
            cover_filename = secure_filename(cover_file.filename)
            cover_path = os.path.join(app.config['UPLOAD_FOLDER'], cover_filename)
            cover_file.save(cover_path)

            # Generate a path for the uploaded image
            cover_url = url_for('static', filename=f'uploads/{cover_filename}')
            print(f'{cover_url}')
        
        else:
            cover_url='/static/images/playnest_logo.png'

        short_description = request.form['short-description']
        long_description = request.form['long-description']

        # Game file handler
        if 'game-file' not in request.files:
            return redirect(request.url)
        
        game_file = request.files['game-file']

        if game_file.filename == '':
            return redirect(request.url)

        if game_file and allowed_game_file(game_file.filename):
            filename = secure_filename(game_file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            game_file.save(file_path)

            # Extract the uploaded ZIP file
            zip_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename.split('.')[0])
            print(f'{path}')
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(path)

            # Search for index.html in the extracted files
            index_html_path = find_index_html(zip_path)
            if index_html_path:
                game_url = url_for('static', filename=f'uploads/{filename.split(".")[0]}/{index_html_path}')
                print(f'{game_url}')
                os.remove(zip_path)
            else:
                # If index.html is not found, make the file downloadable and delete the extracted folder
                game_url = zip_path
                if os.path.exists(path):
                    shutil.rmtree(path)
                path = filename
                print(f'{path}')
        else:
            return 'Invalid game file format'
        
        author_id = User.query.filter_by(username=session['username']).first().id

        new_game = Game(title=title, cover_url=cover_url, filepath=path, short_description=short_description, long_description=long_description, game_url=game_url, author_id=author_id)
        db.session.add(new_game)
        db.session.commit()
        return render_template('dashboard.html', games=Game.query.filter_by(author_id=user.id).all())
    
    return render_template('dashboard.html', games=Game.query.filter_by(author_id=user.id).all())

@app.post('/dashboard/delete/<int:game_id>')
def delete_user_game(game_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    else:
        user = User.query.filter_by(username=session['username']).first()

    game = Game.query.get(game_id)

    if game.cover_url == '/static/images/playnest_logo.png':
        if game.game_url.lower().endswith('index.html'):
            game_folder = game.filepath
            print(f'{game_folder}')
            shutil.rmtree(game_folder)
        
        else:
            game_file = game.game_url
            print(f'{game_file}')
            os.remove(game_file)

    else:
        if game.game_url.lower().endswith('index.html'):
            game_folder = game.filepath
            print(f'{game_folder}')
            shutil.rmtree(game_folder)

            cover_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(game.cover_url))
            print(f'{cover_path}')
            os.remove(cover_path)

        else:
            game_file = game.game_url
            print(f'{game_file}')
            os.remove(game_file)

            cover_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(game.cover_url))
            print(f'{cover_path}')
            os.remove(cover_path)

    db.session.delete(game)
    db.session.commit()

    return redirect(url_for('dashboard', games=Game.query.filter_by(author_id=user.id).all()))

@app.get('/game/<int:game_id>')
def play_game(game_id):
    game = Game.query.get(game_id)
    return render_template('game.html', game=game)

@app.get('/game/download/<name>')
def download_game(name):
    return send_from_directory(app.config['UPLOAD_FOLDER'], name)

@app.route('/settings')
def settings():
    if 'username' not in session: 
        return redirect(url_for('login'))
    # retrieve user ID of current session user
    user = User.query.filter_by(username=session['username']).first()
    user_email = User.query.filter_by(username=session['username']).first().email
    num_games = Game.query.filter_by(author_id=user.id).count()
    
    if request.method == 'POST':
        pass
    return render_template('settings.html', user_email=user_email, num_games=num_games)

@app.route('/change-username', methods=['GET', 'POST'])
def change_username():
    if request.method == 'POST':
        user = User.query.filter_by(username=session['username']).first()
        new_username = request.form['username']
        user.username = new_username
        db.session.commit()

        session['username'] = new_username
    return redirect(url_for('settings'))

@app.route('/change-email', methods=['GET', 'POST'])
def change_email():
    if request.method == 'POST':
        user = User.query.filter_by(username=session['username']).first()
        old_email = request.form['oldemail']
        new_email = request.form['newemail']
        if user.email != old_email:
            return "Current email does not match."
        user.email = new_email
        db.session.commit()
    return redirect(url_for('settings'))

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if request.method == "POST":
        old_password = request.form['old-password']
        new_password = request.form['new-password']
        re_new_password = request.form['renew-password']
        user = User.query.filter_by(username=session['username']).first()
        if bcrypt.check_password_hash(user.password_hash, old_password):
            if new_password != re_new_password:
                return "Passwords do not match."
            # hash password before storing it
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            user.password_hash = hashed_password
            db.session.commit()
        else:
            return "Current password incorrect."
    return redirect(url_for('settings'))

@app.route('/delete-account', methods=['GET', 'POST'])
def delete_account():
    if request.method == "POST":
        password_verification = request.form['delete-account-pw']
        user = User.query.filter_by(username=session['username']).first()
        if bcrypt.check_password_hash(user.password_hash, password_verification):
            if user.profile:
                db.session.delete(user.profile)

            Review.query.filter_by(user_id=user.id).delete()
            Thread.query.filter_by(user_id=user.id).delete()
            Like.query.filter(Like.comment_id.in_(db.session.query(Comment.id).filter_by(user_id=user.id))).delete()
            Comment.query.filter_by(user_id=user.id).delete()

            db.session.delete(user)
            db.session.commit()
            # clear username from session
            session.pop('username', None)
    else:
        return "Password incorrect."
    return redirect(url_for('home'))

@app.route('/delete-games', methods=['GET', 'POST'])
def delete_games():
    if request.method == "POST":
        password_verification = request.form['delete-games-pw']
        user = User.query.filter_by(username=session['username']).first()
        if bcrypt.check_password_hash(user.password_hash, password_verification):
            db.session.query(Game).filter_by(author_id=user.id).delete()
            db.session.commit()
        else:
            return "Password incorrect."
    return redirect(url_for('settings'))

@app.get('/forum')
def forum():
    forums = Forum.query.all()
    return render_template('forum.html', forums=forums)

@app.route('/forum/<forum_slug>', methods=['GET', 'POST'])
def forum_threads(forum_slug):
    # retrieve forum using provided slug from URL 
    forum = Forum.query.filter_by(slug=forum_slug).first()
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        # retrieve user ID of current session user
        user_id = User.query.filter_by(username=session['username']).first().id
        
        # creating a new thread to add to database
        new_thread = Thread(title=title, content=content, forum_id=forum.id, user_id=user_id)
        db.session.add(new_thread)
        db.session.commit()
    
    # attach URLs to each thread for thread details viewing
    threads = Thread.query.filter_by(forum_id=forum.id).all()
    for thread in threads:
        thread.detail_url = url_for('thread_detail', forum_slug=forum.slug, thread_id=thread.id)

    return render_template('forum_threads.html', forum=forum, threads=threads, background_image=forum.image_filename)

@app.route('/forum/<forum_slug>/<int:thread_id>', methods=['GET', 'POST'])
def thread_detail(forum_slug, thread_id):
    forum = Forum.query.filter_by(slug=forum_slug).first()
    thread = Thread.query.get(thread_id)
    
    if request.method == 'POST':
        # extract comment info from submitted form data
        content = request.form['content']
        user_id = User.query.filter_by(username=session['username']).first().id
        
        parent_comment_id = request.form.get('parent_comment_id')
        
        # creating a new comment to add to database
        if parent_comment_id:
            new_comment = Comment(content=content, user_id=user_id, thread_id=thread.id, parent_comment_id=parent_comment_id)
        else:
            new_comment = Comment(content=content, user_id=user_id, thread_id=thread.id)
        db.session.add(new_comment)
        db.session.commit()

    if 'username' in session:
        user_id = User.query.filter_by(username=session['username']).first().id
        liked_comments = [like.comment_id for like in Like.query.filter_by(user_id=user_id).all()]
    else:
        liked_comments = []

    return render_template('thread_detail.html', forum_slug=forum_slug, forum=forum, thread=thread, liked_comments=liked_comments, background_image=forum.image_filename)

def post_reply_helper(content, user_id, parent_comment_id, thread_id=None, review_id=None, game_id=None, forum_slug=None):
    if thread_id is not None:
        new_comment = Comment(content=content, user_id=user_id, thread_id=thread_id, parent_comment_id=parent_comment_id)
        redirect_route = 'thread_detail'
        redirect_args = {'forum_slug': forum_slug, 'thread_id': thread_id}
    elif review_id is not None:
        new_comment = Comment(content=content, user_id=user_id, review_id=review_id, parent_comment_id=parent_comment_id)
        redirect_route = 'review_detail'
        redirect_args = {'review_id': review_id}
    elif game_id is not None:
        new_comment = Comment(content=content, user_id=user_id, game_id=game_id, parent_comment_id=parent_comment_id)
        redirect_route = 'game_detail'
        redirect_args = {'game_id': game_id}
    else:
        # Handle invalid parameters
        return abort(404)

    db.session.add(new_comment)
    db.session.commit()
    
    return redirect(url_for(redirect_route, **redirect_args))

@app.route('/forum/<forum_slug>/<int:thread_id>/post_reply', methods=['POST'])
def post_reply(forum_slug, thread_id):
    if request.method == 'POST':
        content = request.form.get('content')
        parent_comment_id = request.form.get('parent_comment_id')
        
        user = User.query.filter_by(username=session['username']).first()

        if user:
            user_id = user.id
            return post_reply_helper(content, user_id, parent_comment_id, thread_id=thread_id, forum_slug=forum_slug)
    
    return abort(404)

@app.route('/review_detail/<int:review_id>/post_reply', methods=['POST'])
def post_review_reply(review_id):
    if request.method == 'POST':
        content = request.form.get('content')
        parent_comment_id = request.form.get('parent_comment_id')
        
        user = User.query.filter_by(username=session['username']).first()

        if user:
            user_id = user.id
            return post_reply_helper(content, user_id, parent_comment_id, review_id=review_id)
    
    return abort(404)

@app.route('/game_detail/<int:game_id>/post_reply', methods=['POST'])
def post_game_reply(game_id):
    if request.method == 'POST':
        content = request.form.get('content')
        parent_comment_id = request.form.get('parent_comment_id')
        
        user = User.query.filter_by(username=session['username']).first()

        if user:
            user_id = user.id
            return post_reply_helper(content, user_id, parent_comment_id, game_id=game_id)
    
    return abort(404)

def delete_comment_helper(comment_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    comment = Comment.query.get(comment_id)
    
    # check if logged in user is the owner of the comment
    if comment.user.username == session['username']:
        # delete child comments first
        for child_comment in comment.child_comments:
            db.session.delete(child_comment)

        db.session.delete(comment)
        db.session.commit()

@app.route('/forum/<forum_slug>/<int:thread_id>/delete_comment/<int:comment_id>', methods=['POST'])
def delete_comment(forum_slug, thread_id, comment_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    delete_comment_helper(comment_id)

    return redirect(url_for('thread_detail', forum_slug=forum_slug, thread_id=thread_id))

@app.route('/review_detail/<int:review_id>/delete_comment/<int:comment_id>', methods=['POST'])
def delete_review_comment(review_id, comment_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    delete_comment_helper(comment_id)

    return redirect(url_for('review_detail', review_id=review_id))

@app.route('/game_detail/<int:game_id>/delete_comment/<int:comment_id>', methods=['POST'])
def delete_game_comment(game_id, comment_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    delete_comment_helper(comment_id)

    return redirect(url_for('game_detail', game_id=game_id))

def edit_comment_helper(comment_id, session_username, new_content, new_rating):
    comment = Comment.query.get(comment_id)
    if comment:
        # check if logged in user is owner of the comment
        if comment.user.username == session_username:
            # update the comment content in the database
            comment.content = new_content
            comment.rating = new_rating
            db.session.commit()
            return True
        else:
            abort(403)
    else:
        abort(404)

@app.route('/forum/<forum_slug>/<int:thread_id>/edit_comment/<int:comment_id>', methods=['POST'])
def edit_comment(forum_slug, thread_id, comment_id):
    if 'username' not in session: 
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_content = request.form.get('edit_content')
        if edit_comment_helper(comment_id, session['username'], new_content, new_rating=None):
            return redirect(url_for('thread_detail', forum_slug=forum_slug, thread_id=thread_id))

    abort(400) 

@app.route('/review_detail/<int:review_id>/edit_comment/<int:comment_id>', methods=['POST'])
def edit_review_comment(review_id, comment_id):
    if 'username' not in session: 
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_content = request.form.get('edit_content')
        if edit_comment_helper(comment_id, session['username'], new_content, new_rating=None):
            return redirect(url_for('review_detail', review_id=review_id))

    abort(400)

@app.route('/game_detail/<int:game_id>/edit_comment/<int:comment_id>', methods=['POST'])
def edit_game_comment(game_id, comment_id):
    if 'username' not in session: 
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_rating = request.form.get('edit_rating')
        new_content = request.form.get('edit_content')
        if edit_comment_helper(comment_id, session['username'], new_content, new_rating):
            return redirect(url_for('game_detail', game_id=game_id))

    abort(400)

@app.route('/forum/<forum_slug>/<int:thread_id>/edit_thread', methods=['POST'])
def edit_thread(forum_slug, thread_id):
    if 'username' not in session: 
        return redirect(url_for('login'))
    
    thread = Thread.query.get(thread_id)
    
    # check if logged in user is the owner of the reply
    if thread.user.username == session['username']:
        if request.method == 'POST':
            new_title = request.form.get('edit_title')
            new_content = request.form.get('edit_content')
            
            # update the reply content in the database
            thread.title = new_title
            thread.content = new_content
            db.session.commit()

    return redirect(url_for('thread_detail', forum_slug=forum_slug, thread_id=thread_id))

@app.route('/forum/<forum_slug>/<int:thread_id>/delete_thread', methods=['POST'])
def delete_thread(forum_slug, thread_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    thread = Thread.query.get(thread_id)
    
    # check if logged in user is the owner of the thread
    if thread.user.username == session['username']:
        for comment in thread.comments:
            for like in comment.likes:
                db.session.delete(like)
            db.session.delete(comment)
    
        db.session.delete(thread)
        db.session.commit()

    return redirect(url_for('forum_threads', forum_slug=forum_slug))

def get_games_from_rawg_api():
    API_KEY = os.getenv('API_KEY')
    base_url = 'https://api.rawg.io/api/games'
    
    # defining parameters for API request
    params = {
        'key': API_KEY,
        'ordering': '-metacritic',
        'page_size': 12,  # number of games per 'page'
        'language': 'english',
    }
    
    try:
        # make a GET request to RAWG API
        response = requests.get(base_url, params=params)
        
        # checking if request was successful
        if response.status_code == 200:
            # parse the JSON data from the response
            games_data = response.json()
            
            # extract results containing game information
            games = games_data.get('results', [])
            
            return games
        else:
            # print error message is request wasn't successful
            print(f"Error: Unable to fetch games from RAWG API. Status code: {response.status_code}")
            return None
        
    except requests.RequestException as e:
        # print error message if there is an exception during the request
        print(f"Error: {e}")
        return None

@app.get('/game_reviews')
def game_reviews():
    games = get_games_from_rawg_api()
    api_key = os.getenv("API_KEY")
    
    if games is not None and games:
        return render_template('game_reviews.html', games=games, api_key=api_key)
    else:
        # return template without passing the game variable
        return render_template('game_reviews.html')

@app.route('/game_details/<int:game_id>', methods=['GET', 'POST'])
def game_details(game_id):
    sort_by = request.args.get('sort', 'default')

    game = get_game_details_from_rawg_api(game_id)

    if sort_by == 'highest_rating':
        reviews = Review.query.filter_by(game_identifier=str(game_id)).order_by(Review.rating.desc()).all()
    elif sort_by == 'lowest_rating':
        reviews = Review.query.filter_by(game_identifier=str(game_id)).order_by(Review.rating).all()
    else:
        reviews = Review.query.filter_by(game_identifier=str(game_id)).order_by(desc(Review.created_at)).all()

    if game:
        average_rating, review_count = calculate_average_rating(reviews)
        return render_template('game_details.html', game=game, reviews=reviews, sort_by=sort_by, average_rating=average_rating, review_count=review_count)
    else:
        return render_template('game_details.html', sort_by=sort_by)

def calculate_average_rating(reviews):
    total_ratings = 0
    count = 0
    for review in reviews:
        if review.rating is not None: 
            total_ratings += review.rating
            count += 1
    average_rating = total_ratings / count if count > 0 else 0
    return average_rating, count

def strip_html_tags(html):
    # using BeautifulSoup to parse the HTML and then get text
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text()

@app.route('/post_review', methods=['POST'])
def post_review():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        user_id = User.query.filter_by(username=session['username']).first().id
        game_id = request.form.get('game_id')
        is_recommendation = bool(int(request.form.get('recommendation', 1)))
        rating = int(request.form.get('rating'))
        
        # associate the review with the corresponding game using game_id
        new_review = Review(
            title=title, 
            content=content, 
            user_id=user_id, 
            game_identifier=game_id,
            is_recommendation=is_recommendation,
            rating=rating
        )
        
        db.session.add(new_review)
        db.session.commit()
        
        # redirect to game details page
        return redirect(url_for('game_details', game_id=game_id))
    
    return redirect(url_for('home'))

def delete_review_helper(review_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    review = Review.query.get(review_id)

    # check if logged in user is owner of the review
    if review.user.username == session['username']:
        db.session.delete(review)
        db.session.commit()

@app.route('/delete_review/<int:review_id>', methods=['POST'])
def delete_review(review_id):
    delete_review_helper(review_id)

    return jsonify({'success': True})

@app.route('/delete_single_review/<int:review_id>', methods=['POST'])
def delete_single_review(review_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    review = Review.query.get(review_id)
    delete_review_helper(review_id)
    game_id = review.game_identifier
    return redirect(url_for('game_details', game_id=game_id))

@app.route('/edit_review/<int:review_id>', methods=['POST'])
def edit_review(review_id):
    if 'username' not in session: 
        return redirect(url_for('login'))
    
    review = Review.query.get(review_id)
    
    # check if logged in user is the owner of the review
    if review.user.username == session['username']:
        if request.method == 'POST':
            new_content = request.form.get('edit_content')
            
            # update the review content in the database
            review.content = new_content
            db.session.commit()

    game_id = review.game_identifier
    return redirect(url_for('game_details', game_id=game_id))

@app.route('/edit_single_review/<int:review_id>', methods=['POST'])
def edit_single_review(review_id):
    if 'username' not in session: 
        return redirect(url_for('login'))
    
    review = Review.query.get(review_id)
    
    # check if logged in user is the owner of the review
    if review.user.username == session['username']:
        if request.method == 'POST':
            new_title = request.form.get('edit_title')
            new_recommendation = int(request.form.get('edit_recommendation', review.is_recommendation))
            new_rating = int(request.form.get('edit_rating', review.rating))
            new_content = request.form.get('edit_content')
            
            # update the review content in the database
            review.title = new_title
            review.is_recommendation = new_recommendation
            review.rating = new_rating
            review.content = new_content
            db.session.commit()

    return redirect(url_for('review_detail', review_id=review.id))

@app.route('/game_detail/<int:game_id>', methods=['GET', 'POST'])
def game_detail(game_id):
    game = Game.query.get(game_id)

    if request.method == 'POST':
        content = request.form['content']
        user_id = User.query.filter_by(username=session['username']).first().id
        parent_comment_id = request.form.get('parent_comment_id')

        rating = int(request.form['rating']) if request.form['rating'] else None

        if parent_comment_id:
            new_comment = Comment(content=content, user_id=user_id, game_id=game.game_id, parent_comment_id=parent_comment_id, rating=rating)
        else:
            new_comment = Comment(content=content, user_id=user_id,  game_id=game.game_id, rating=rating)

        db.session.add(new_comment)
        db.session.commit()

        return redirect(url_for('game_detail',  game_id=game.game_id))

    comments = game.comments
    if 'username' in session:
        user_id = User.query.filter_by(username=session['username']).first().id
        liked_comments = [like.comment_id for like in Like.query.filter_by(user_id=user_id).all()]
    else:
        liked_comments = []

    return render_template('game.html', game=game, comments=comments, liked_comments=liked_comments)

@app.route('/review_detail/<int:review_id>', methods=['GET', 'POST'])
def review_detail(review_id):
    review = Review.query.get(review_id)
    game = get_game_details_from_rawg_api(review.game_identifier)

    if request.method == 'POST':
        content = request.form['content']
        user_id = User.query.filter_by(username=session['username']).first().id
        parent_comment_id = request.form.get('parent_comment_id')

        if parent_comment_id:
            new_comment = Comment(content=content, user_id=user_id, review_id=review.id, parent_comment_id=parent_comment_id)
        else:
            new_comment = Comment(content=content, user_id=user_id, review_id=review.id)

        db.session.add(new_comment)
        db.session.commit()

        return redirect(url_for('review_detail', review_id=review_id))

    comments = review.comments
    if 'username' in session:
        user_id = User.query.filter_by(username=session['username']).first().id
        liked_comments = [like.comment_id for like in Like.query.filter_by(user_id=user_id).all()]
    else:
        liked_comments = []

    return render_template('review_detail.html', review=review, game=game, comments=comments, liked_comments=liked_comments)

class ProfileEditForm(FlaskForm):
    about_me = TextAreaField('About Me')
    profile_picture = SelectField('Profile Picture',  validators=[validators.DataRequired()])
    submit = SubmitField('Save Changes')

    def __init__(self, *args, **kwargs):
        super(ProfileEditForm, self).__init__(*args, **kwargs)

        # this dynamically populates choices for the profile pic dropdown
        picture_options_path = join('static', 'images', 'picture_options')
        image_files = [f for f in listdir(picture_options_path) if isfile(join(picture_options_path, f))]
        self.profile_picture.choices = [(filename, join(picture_options_path, filename)) for filename in image_files]

        if not self.profile_picture.data:
            self.profile_picture.data = 'images/default.jpeg'

@app.route('/profile/edit', methods=['GET', 'POST'])
def edit_profile():
    if 'username' not in session: 
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    profile = user.profile
    
    form = ProfileEditForm(request.form, obj=profile)

    if request.method == 'POST' and form.validate():
        action = request.form.get('action')

        if action == 'save_description':
            # update only the about me desc
            form.profile_picture.data = profile.profile_picture  # retain the current picture
            form.populate_obj(profile)
        elif action == 'save_picture':
            # update only the profile picture
            form.about_me.data = profile.about_me  # retain the current description
            form.populate_obj(profile)
        else:
            # update both description and picture
            form.populate_obj(profile)

        db.session.commit()
        return redirect(url_for('view_profile', user_id=user.id))

    return render_template('profile_edit.html', form=form, user=user)

@app.route('/view_profile/<int:user_id>', methods=['GET'])
def view_profile(user_id):
    user = User.query.get(user_id)

    # retrieve reviews and threads posted by user
    user_reviews = Review.query.filter_by(user_id=user.id).all()
    user_threads = Thread.query.filter_by(user_id=user.id).all()
    user_games = Game.query.filter_by(author_id=user.id).all()

    # attach URLs to reviews and threads for details viewing
    for review in user_reviews:
        review.detail_url = url_for('game_details', game_id=review.game_identifier)

    for thread in user_threads:
        thread.detail_url = url_for('thread_detail', forum_slug=thread.forum.slug, thread_id=thread.id)

    for game in user_games:
        game.detail_url = url_for('game_detail', game_id=game.game_id)

    return render_template('profile_view.html', user=user, user_reviews=user_reviews, user_threads=user_threads, user_games=user_games, get_game_details_from_rawg_api=get_game_details_from_rawg_api)

@app.route('/view_own_profile', methods=['GET'])
def view_own_profile():
    if 'username' in session:
        user = User.query.filter_by(username=session['username']).first()

        # retrieve reviews and threads posted by the user
        user_reviews = Review.query.filter_by(user_id=user.id).all()
        user_threads = Thread.query.filter_by(user_id=user.id).all()
        user_games = Game.query.filter_by(author_id=user.id).all()

        # attach URLs to reviews, threads and games for details viewing
        for review in user_reviews:
            review.detail_url = url_for('game_details', game_id=review.game_identifier)

        for thread in user_threads:
            thread.detail_url = url_for('thread_detail', forum_slug=thread.forum.slug, thread_id=thread.id)

        for game in user_games:
            game.detail_url = url_for('game_detail', game_id=game.game_id)

        return render_template('profile_view.html', user=user, user_reviews=user_reviews, user_threads=user_threads, user_games=user_games, get_game_details_from_rawg_api=get_game_details_from_rawg_api)
    else:
        # if the user is not logged in
        return redirect(url_for('login'))

@app.route('/like_comment/<int:comment_id>', methods=['POST'])
def like_comment(comment_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    user_id = User.query.filter_by(username=session['username']).first().id
    comment = Comment.query.get(comment_id)
    
    # check if the user has already liked the comment
    existing_like = Like.query.filter_by(user_id=user_id, comment_id=comment_id).first()

    if existing_like:
        # user has already liked the comment so unlike
        db.session.delete(existing_like)
        db.session.commit()
    else:
        # user has not liked the comment so like
        like = Like(user_id=user_id, comment_id=comment_id)
        db.session.add(like)
        db.session.commit()

    return jsonify({'success': True})

@app.route('/users')
def display_users():
    users = User.query.order_by(User.username).all()
    return render_template('all_users.html', users=users)

@app.route('/user_games')
def user_games():
    games = Game.query.order_by(desc(Game.release_date)).all()
    for game in games:
        game.detail_url = url_for('game_detail', game_id=game.game_id)

    return render_template('user_games.html', games=games)

@app.route('/edit_game_desc/<int:game_id>', methods=['GET', 'POST'])
def edit_game_desc(game_id):
    if 'username' not in session: 
        return redirect(url_for('login'))

    game = Game.query.get(game_id)

    # check if logged in user is the owner of the game
    if game.author.username == session['username']:
        if request.method == 'POST':
            new_long_description = request.form.get('edit_long_description')
            new_game_title = request.form.get('edit_title')

            # update the game long description in the database
            game.long_description = new_long_description
            game.title = new_game_title
            db.session.commit()

    return render_template('game.html', game=game)
