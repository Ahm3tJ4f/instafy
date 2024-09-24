import logging
from logging.handlers import RotatingFileHandler
from instagrapi import Client
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import sys
from dotenv import load_dotenv
import time

# Set up logging
def setup_logging():
    logger = logging.getLogger('spotify_instagram_updater')
    logger.setLevel(logging.DEBUG)

    file_handler = RotatingFileHandler('spotify_instagram_updater.log', maxBytes=1024 * 1024, backupCount=5)
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
    try:
        logger.debug("Fetching current song from Spotify")
        current_song = spotify_object.current_user_playing_track()
        if current_song is not None and current_song['item'] is not None:
            song_title = current_song['item']['name']
            artist_name = current_song['item']['artists'][0]['name']
            duration_ms = current_song['item']['duration_ms']
            progress_ms = current_song['progress_ms']
            logger.info(f"Current song: {artist_name} - {song_title}")
            return song_title, artist_name, duration_ms, progress_ms
        else:
            logger.info("No song currently playing")
            return None, None, None, None
    except Exception as e:
        logger.error(f"Error getting current song: {e}", exc_info=True)
        return None, None, None, None

def update_instagram_status(client, status):
    try:
        logger.info(f"Updating Instagram status to: {status}")
        client.create_note(status, 0)
        logger.info("Instagram status updated successfully")
    except Exception as e:
        logger.error(f"Error updating Instagram status: {e}", exc_info=True)

def generate_cookie(username, password):
    cl = Client()
    cl.login(username, password)
    cl.dump_settings(f"{username}.json")
    logger.info(f"Generated cookie for {username}")

def calculate_next_poll_time(duration_ms, progress_ms):
    if duration_ms is None or progress_ms is None:
        return 15 * 60  # 15 minutes in seconds
    
    remaining_ms = duration_ms - progress_ms
    half_remaining_ms = remaining_ms / 2
    return max(half_remaining_ms / 1000, 10)  # Convert to seconds, minimum 10 seconds

def main():
    logger.info("Starting Spotify to Instagram Status Updater")

    # Get environment variables
    logger.debug("Loading environment variables")
    load_dotenv()
    spotify_client_id = os.getenv('SPOTIPY_CLIENT_ID')
    spotify_client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')
    spotify_redirect_uri = os.getenv('SPOTIPY_REDIRECT_URI')
    spotify_username = os.getenv('SPOTIFY_USERNAME')
    account_username = os.getenv('ACCOUNT_USERNAME')
    account_password = os.getenv('ACCOUNT_PASSWORD')

    if not spotify_username:
        logger.error('SPOTIFY_USERNAME not set in environment variables')
        sys.exit(1)
    
    logger.info(f"Using Spotify username: {spotify_username}")

    # Set up Spotify authentication
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
        logger.error(f"Spotify authentication failed: {e}", exc_info=True)
        sys.exit(1)

    # Set up Instagram client
    logger.info("Setting up Instagram client")
    cl = Client()
    if os.path.exists(f"{account_username}.json"):
        logger.info("Using existing cookies")
        cl.load_settings(f"{account_username}.json")
    else:
        logger.info("Generating new cookies")
        generate_cookie(account_username, account_password)
    
    try:
        cl.login(account_username, account_password)
        logger.info("Instagram login successful")
    except Exception as e:
        logger.error(f"Instagram login failed: {e}", exc_info=True)
        sys.exit(1)

    prev_song_title = None
    prev_artist_name = None
    next_poll_time = time.time()

    logger.info("Entering main loop")
    while True:
        current_time = time.time()
        if current_time < next_poll_time:
            time.sleep(1)
            continue

        song_title, artist_name, duration_ms, progress_ms = get_current_song(spotify_object)

        if song_title and artist_name:
            if song_title != prev_song_title or artist_name != prev_artist_name:
                status = f"Listening to: {song_title}-{artist_name}"
                logger.info(f"New song detected: {status}")
                update_instagram_status(cl, status)
                prev_song_title = song_title
                prev_artist_name = artist_name
            
            next_poll_interval = calculate_next_poll_time(duration_ms, progress_ms)
            logger.debug(f"Next poll in {next_poll_interval:.2f} seconds")
        else:
            next_poll_interval = 15 * 60  # 15 minutes
            logger.info("No song playing. Next poll in 15 minutes")
        
        next_poll_time = time.time() + next_poll_interval

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Program interrupted by user. Exiting.")
    except Exception as e:
        logger.critical(f"Unexpected error occurred: {e}", exc_info=True)
    finally:
        logger.info("Program terminated")