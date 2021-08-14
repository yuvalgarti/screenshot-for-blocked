import tweepy
import os
import logging

from services.firebase_service import FirebaseService
from screenshot_for_blocked import ScreenshotForBlocked


if __name__ == '__main__':
    auth = tweepy.OAuthHandler(os.environ['SCREENSHOT_CONSUMER_KEY'], os.environ['SCREENSHOT_CONSUMER_VALUE'])
    auth.set_access_token(os.environ['SCREENSHOT_ACCESS_TOKEN_KEY'], os.environ['SCREENSHOT_ACCESS_TOKEN_VALUE'])

    firebase_config = {
        'apiKey': os.environ['FIREBASE_API_KEY'],
        'authDomain': os.environ['FIREBASE_AUTH_DOMAIN'],
        'databaseURL': os.environ['FIREBASE_DB_URL'],
        'storageBucket': os.environ['FIREBASE_STORAGE_BUCKET']
    }

    tweepy_api = tweepy.API(auth, wait_on_rate_limit=True)
    logging.basicConfig(level=os.environ.get('SCREENSHOT_LOG_LEVEL', 'INFO').upper(),
                        format='%(asctime)s - %(levelname)s - %(message)s')

    bot = ScreenshotForBlocked(tweepy_api, FirebaseService(firebase_config))
    bot.run()
