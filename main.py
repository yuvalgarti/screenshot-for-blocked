import logging
import os
import sys

import tweepy
from mention_bot import MentionHandler

from screenshot_for_blocked.firebase_service import FirebaseService
from screenshot_for_blocked.screenshot_for_blocked import ScreenshotForBlocked

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
    is_production = os.environ.get('IS_PRODUCTION', 'True') == 'True'
    print('is_production: ' + str(is_production))

    log_modules = ['screenshot_for_blocked', 'mention_bot']
    logFormat = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logFormat)

    for module_name in log_modules:
        logger = logging.getLogger(module_name)
        logger.setLevel('DEBUG')
        logger.addHandler(console_handler)

    bot = ScreenshotForBlocked(tweepy_api, int(os.environ.get('SCREENSHOT_TIMEOUT', 30)), is_production)
    mention_handler = MentionHandler(tweepy_api,
                                     bot,
                                     FirebaseService(firebase_config),
                                     is_production,
                                     int(os.environ.get('SCREENSHOT_TIMEOUT', 30)),
                                     int(os.environ.get('RETRY_COUNT', 3)))
    mention_handler.run()
