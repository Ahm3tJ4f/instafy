import logging
from logging.handlers import RotatingFileHandler
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired, TwoFactorRequired
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import sys
from dotenv import load_dotenv
import time
import random
from datetime import datetime
import pytz

def setup_logging():
    logger = logging.getLogger('instafy')
    logger.setLevel(logging.DEBUG)

    file_handler = RotatingFileHandler('instafy.log', maxBytes=1024 * 1024, backupCount=5)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

logger = setup_logging()

def get_current_song(spotify_object):
    logger.debug("Attempting to fetch current song from Spotify")
    try:
        current_song = spotify_object.current_user_playing_track()
        if current_song is not None and current_song['item'] is not None:
            song_title = current_song['item']['name']
            artist_name = current_song['item']['artists'][0]['name']
            duration_ms = current_song['item']['duration_ms']
            progress_ms = current_song['progress_ms']
            logger.info(f"Current song: {artist_name} - {song_title}")
            logger.debug(f"Song duration: {duration_ms}ms, Current progress: {progress_ms}ms")
            return song_title, artist_name, duration_ms, progress_ms
        else:
            logger.info("No song currently playing")
            return None, None, None, None
    except Exception as e:
        logger.error(f"Error getting current song: {str(e)}", exc_info=True)
        return None, None, None, None

def update_instagram_note(client, status):
    logger.info(f"Attempting to update Instagram note to: {status}")
    try:
        client.create_note(status, 0)
        logger.info("Instagram note updated successfully")
    except LoginRequired:
        logger.warning("Login required. Attempting to re-login.")
        try:
            login_instagram(client)
            client.create_note(status, 0)
            logger.info("Instagram note updated successfully after re-login")
        except Exception as login_error:
            logger.error(f"Re-login failed: {str(login_error)}", exc_info=True)
    except Exception as e:
        logger.error(f"Error updating Instagram note: {str(e)}", exc_info=True)

def login_instagram(client):
    logger.info(f"Attempting to log in to Instagram as {account_username}")
    try:
        client.login(account_username, account_password)
        logger.info("Instagram login successful")
    except (ChallengeRequired, TwoFactorRequired) as e:
        logger.error(f"Instagram login requires additional verification: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Instagram login failed: {str(e)}", exc_info=True)
        raise

def calculate_next_poll_time(duration_ms, progress_ms):
    logger.debug(f"Calculating next poll time. Duration: {duration_ms}ms, Progress: {progress_ms}ms")
    if duration_ms is None or progress_ms is None:
        default_time = 15 * 60
        logger.info(f"Using default poll time of {default_time} seconds")
        return default_time
    
    remaining_ms = duration_ms - progress_ms
    half_remaining_ms = remaining_ms / 2
    next_poll = max(half_remaining_ms / 1000, 30)
    logger.info(f"Next poll time calculated: {next_poll:.2f} seconds")
    return next_poll

def get_azerbaijan_time(timestamp):
    azerbaijan_tz = pytz.timezone('Asia/Baku')
    return datetime.fromtimestamp(timestamp, azerbaijan_tz).strftime('%Y-%m-%d %H:%M:%S %Z')

def main():
    logger.info("Starting Spotify to Instagram Note Updater")

    logger.debug("Loading environment variables")
    load_dotenv()
    spotify_client_id = os.getenv('SPOTIPY_CLIENT_ID')
    spotify_client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')
    spotify_redirect_uri = os.getenv('SPOTIPY_REDIRECT_URI')
    spotify_username = os.getenv('SPOTIFY_USERNAME')
    global account_username, account_password
    account_username = os.getenv('ACCOUNT_USERNAME')
    account_password = os.getenv('ACCOUNT_PASSWORD')

    if not spotify_username:
        logger.error('SPOTIFY_USERNAME not set in environment variables')
        sys.exit(1)

    logger.info(f"Spotify username: {spotify_username}")

    logger.info("Setting up Spotify authentication")
    scope = 'user-read-currently-playing'
    try:
        spotify_object = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=spotify_client_id,
                                                                   client_secret=spotify_client_secret,
                                                                   redirect_uri=spotify_redirect_uri,
                                                                   scope=scope,
                                                                   username=spotify_username))
        logger.info("Spotify authentication successful")
    except Exception as e:
        logger.error(f"Spotify authentication failed: {str(e)}", exc_info=True)
        sys.exit(1)

    logger.info("Setting up Instagram client")
    cl = Client()
    try:
        login_instagram(cl)
    except Exception as e:
        logger.error(f"Initial Instagram login failed: {str(e)}", exc_info=True)
        sys.exit(1)

    prev_song_title = None
    prev_artist_name = None
    next_poll_time = time.time()

    logger.info("Entering main loop")
    while True:
        try:
            current_time = time.time()
            if current_time < next_poll_time:
                time.sleep(1)
                continue

            logger.debug("Fetching current song information")
            song_title, artist_name, duration_ms, progress_ms = get_current_song(spotify_object)

            if song_title and artist_name:
                if song_title != prev_song_title or artist_name != prev_artist_name:
                    status = f"Listening to: {song_title} - {artist_name}"
                    logger.info(f"New song detected: {status}")
                    update_instagram_note(cl, status)
                    prev_song_title = song_title
                    prev_artist_name = artist_name
                else:
                    logger.debug("Song hasn't changed since last check")
                
                next_poll_interval = calculate_next_poll_time(duration_ms, progress_ms)
                logger.debug(f"Next poll in {next_poll_interval:.2f} seconds")
            else:
                next_poll_interval = random.randint(10 * 60, 20 * 60) 
                logger.info(f"No song playing. Next poll in {next_poll_interval // 60} minutes")
            
            next_poll_time = time.time() + next_poll_interval
            azerbaijan_time = get_azerbaijan_time(next_poll_time)
            logger.info(f"Next poll scheduled for: {azerbaijan_time} (Azerbaijan Time)")

        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}", exc_info=True)
            next_poll_time = time.time() + 60
            azerbaijan_time = get_azerbaijan_time(next_poll_time)
            logger.info(f"Retrying in 60 seconds due to error. Next attempt at: {azerbaijan_time} (Azerbaijan Time)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Program interrupted by user. Exiting.")
    except Exception as e:
        logger.critical(f"Unexpected error occurred: {str(e)}", exc_info=True)
    finally:
        logger.info("Program terminated")