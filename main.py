import os

import tweepy

from mention_action.screenshot_for_blocked import ScreenshotForBlocked
from mention_handler.mention_handler import MentionHandler
from mention_handler.services.firebase_service import FirebaseService

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
    is_production = os.environ.get('IS_PRODUCTION', True) == 'True'
    print('is_production: ' + str(is_production))

    bot = ScreenshotForBlocked(tweepy_api, is_production)
    mention_handler = MentionHandler(tweepy_api,
                                     bot,
                                     FirebaseService(firebase_config),
                                     int(os.environ.get('SCREENSHOT_TIMEOUT', 30)),
                                     int(os.environ.get('RETRY_COUNT', 3)),
                                     is_production)
    mention_handler.run()
