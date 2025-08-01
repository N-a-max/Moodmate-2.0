import os
import certifi
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from test_nlp import detect_emotion
import time

load_dotenv()

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(64)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///moodmate.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = 'http://127.0.0.1:5000/callback'
SCOPE = 'user-read-recently-played user-top-read'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(120), unique=True, nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    access_token = db.Column(db.String(300), nullable=True)
    refresh_token = db.Column(db.String(300), nullable=True)
    token_expires_at = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f'<User {self.display_name}>'

def get_spotify_oauth():
    return SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SCOPE,
        cache_path=None
    )

def get_token():
    token_info = session.get("token_info", None)
    if not token_info:
        return None

    now = int(time.time())
    is_expired = token_info['expires_at'] - now < 60
    if is_expired:
        sp_oauth = get_spotify_oauth()
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        session["token_info"] = token_info
    
    return token_info

@app.route('/login')
def login():
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url() # Corrected this line
    return redirect(auth_url)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/callback')
def callback():
    sp_oauth = get_spotify_oauth()
    session.clear()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session["token_info"] = token_info

    sp = spotipy.Spotify(auth=token_info['access_token'])
    user_info = sp.current_user()
    spotify_id = user_info['id']
    display_name = user_info['display_name']

    user = User.query.filter_by(spotify_id=spotify_id).first()
    if not user:
        user = User(spotify_id=spotify_id, display_name=display_name)
        db.session.add(user)
    
    user.access_token = token_info['access_token']
    user.refresh_token = token_info['refresh_token']
    user.token_expires_at = token_info['expires_at']
    db.session.commit()
    
    session['spotify_id'] = user.spotify_id
    return redirect(url_for('index'))

@app.route("/")
def index():
    current_user = None
    if 'spotify_id' in session:
        user = User.query.filter_by(spotify_id=session['spotify_id']).first()
        if user:
            current_user = {'display_name': user.display_name}
    return render_template("index.html", current_user=current_user)

@app.route("/predict", methods=['POST'])
def predict_emotion_and_get_quote():
    input_data = request.get_json()
    text = input_data.get('text', '')
    if not text:
        return jsonify({"error": "No text provided"}), 400
    emotion = detect_emotion(text)
    quote = generate_gemini_quote(emotion, text)
    response_data = {
        'input_text': text,
        'detected_emotion': emotion,
        'recommended_quote': quote
    }
    return jsonify(response_data)

@app.route("/recommend", methods=['POST'])
def recommend_music():
    token_info = get_token()
    if not token_info:
        return jsonify({"error": "User not logged in"}), 401

    data = request.get_json()
    emotion = data.get('emotion')
    if not emotion:
        return jsonify({"error": "Emotion not provided"}), 400

    sp = spotipy.Spotify(auth=token_info['access_token'])
    
    # Try to get user's top artists
    top_artists_res = sp.current_user_top_artists(limit=5, time_range='short_term')
    seed_artists = [artist['id'] for artist in top_artists_res['items']]
    
    # If no artists in short term, try medium term
    if not seed_artists:
        top_artists_res = sp.current_user_top_artists(limit=5, time_range='medium_term')
        seed_artists = [artist['id'] for artist in top_artists_res['items']]

    # If still no artists, use a fallback list
    if not seed_artists: 
        seed_artists = ['4gzpq5DPGxSnKTe4SA8HAU', '4tZwfgrHOc3mvqYlEYSvVi', '1dfeR4HaWDbWqFHLkxsg1d'] # Coldplay, Daft Punk, Queen
    
    emotion_params = {
        'joy': {'target_valence': 0.8, 'target_energy': 0.8},
        'sadness': {'target_valence': 0.2, 'target_energy': 0.3},
        'anger': {'target_valence': 0.4, 'target_energy': 0.9},
        'fear': {'target_valence': 0.3, 'target_energy': 0.4},
        'love': {'target_valence': 0.7, 'target_energy': 0.6},
        'surprise': {'target_valence': 0.7, 'target_energy': 0.7},
    }
    
    rec_params = emotion_params.get(emotion, {'target_valence': 0.5, 'target_energy': 0.5})

    try:
        recommendations = sp.recommendations(seed_artists=seed_artists[:5], limit=10, **rec_params)
    except spotipy.exceptions.SpotifyException:
        # If no recommendations can be made, return an empty list
        return jsonify([])

    tracks = []
    for track in recommendations['tracks']:
        if track: # Ensure track is not None
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'url': track['external_urls']['spotify'],
                'album_art': track['album']['images'][0]['url']
            })
        
    return jsonify(tracks)

def generate_gemini_quote(emotion, original_text):
    try:
        prompt = (
            f"A user is feeling '{emotion}' and wrote this: '{original_text}'. "
            f"Generate a short, comforting, and original quote for them that is under 25 words. "
            f"Do not include quotation marks in your response."
        )
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API request failed: {e}")
        return "The best way to predict the future is to create it. - Abraham Lincoln"

if __name__ == "__main__":
    app.run(debug=True)