-- users table: 
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    registration_token VARCHAR(255)
);

-- forum table:
CREATE TABLE forum (
    id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    slug VARCHAR(50) UNIQUE NOT NULL
);

-- thread table:
CREATE TABLE thread (
    id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    forum_id INTEGER REFERENCES forum(id) NOT NULL,
    user_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- comment table:
-- if you previously made the comment table, drop it and recreate one with this query.
-- i made some changes to it.
CREATE TABLE Comment (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    thread_id INTEGER REFERENCES thread(id) NOT NULL,
    parent_comment_id INTEGER REFERENCES comment(id),
    created_at TIMESTAMP DEFAULT current_timestamp NOT NULL,
    FOREIGN KEY (parent_comment_id) REFERENCES comment(id) ON DELETE CASCADE,
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_thread FOREIGN KEY (thread_id) REFERENCES thread(id),
    CONSTRAINT fk_parent_comment FOREIGN KEY (parent_comment_id) REFERENCES comment(id)
);

-- games table:
CREATE TABLE games (
    game_id SERIAL NOT NULL,
    title VARCHAR(255) NOT NULL,
    game_cover_url VARCHAR(255),
    short_description VARCHAR(255),
    long_description TEXT,
    release_date VARCHAR(255) NOT NULL,
    game_url VARCHAR(255) NOT NULL,
    author_id INT NOT NULL,
    PRIMARY KEY (game_id),
    FOREIGN KEY (author_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE CASCADE
);

-- reviews table:
CREATE TABLE reviews (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255),
    content TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    game_identifier VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    is_recommendation BOOLEAN NOT NULL DEFAULT TRUE,
    rating INTEGER DEFAULT NULL
);

-- profiles table:
CREATE TABLE profiles (
    id SERIAL PRIMARY KEY,
    about_me TEXT,
    profile_picture VARCHAR(255),
    user_id INTEGER REFERENCES users(id) UNIQUE NOT NULL
);

-- likes table:
CREATE TABLE likes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    comment_id INTEGER REFERENCES comment(id) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);