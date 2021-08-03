import asyncio
from enum import Enum
import pyppeteer
import tweepy
import os
import time
import pyrebase


class ApiError(Enum):
    RESTRICTED_TWEET = 179
    RESTRICTED_COMMENTS = 433


def get_all_links_from_tweet(tweet):
    links = ''
    if 'urls' in tweet.entities:
        for url in tweet.entities['urls']:
            links += url['url'] + '\n'
    return links


class ScreenshotForBlocked:
    def __init__(self, api, db):
        self.api = api
        self.db = db

    def is_mention_inside_text(self, mention):
        extended_mention = self.api.get_status(mention.id, tweet_mode="extended")
        blocked_screen = '@' + self.api.me().screen_name
        start_text = int(extended_mention.display_text_range[0])
        end_text = int(extended_mention.display_text_range[1])
        return blocked_screen in extended_mention.full_text[start_text:end_text]

    async def screenshot_tweet(self, tweet_id, path_to_image):
        tweet = self.api.get_status(tweet_id)
        tweet_url = os.environ['TWITTER_STATUS_URL'].format(tweet.user.screen_name, tweet.id_str)
        result = self.api.get_oembed(tweet_url)
        tweet_html = result['html'].strip()
        browser = await pyppeteer.launch(args=['--no-sandbox'])
        page = await browser.newPage()
        await page.setContent(tweet_html)
        await page.waitForSelector('iframe', {'visible': True})
        await page.waitFor(2 * 1000)
        tweet_frame = await page.querySelector('iframe')
        await tweet_frame.screenshot({'path': path_to_image})
        await browser.close()

    async def reply_to_mention_with_screenshot(self, mention, tweet_to_screenshot, add_to_status=''):
        path_to_file = tweet_to_screenshot.id_str + '.png'
        await self.screenshot_tweet(tweet_to_screenshot.id, path_to_file)
        media = self.api.media_upload(path_to_file)
        status = '@' + mention.user.screen_name + ' ' + add_to_status
        self.api.update_status(status=status, in_reply_to_status_id=mention.id,
                               media_ids=[media.media_id])
        print('path_to_file: {}, status: {}, in_reply_to_status_id: {}'.format(path_to_file, status,
                                                                               mention.id))
        if os.path.exists(path_to_file):
            os.remove(path_to_file)

    async def reply_blocked_tweet(self, mention, tweet_id):
        blocked_tweet = self.api.get_status(tweet_id)
        links = get_all_links_from_tweet(blocked_tweet)
        await self.reply_to_mention_with_screenshot(mention, blocked_tweet, links)

    async def blocked_retweet(self, mention):
        if mention.in_reply_to_status_id:
            viewed_tweet = self.api.get_status(mention.in_reply_to_status_id)
            if hasattr(viewed_tweet, 'quoted_status'):
                print('This is a retweet')
                await self.reply_blocked_tweet(mention, viewed_tweet.quoted_status.id)
                return True
        return False

    async def blocked_comment(self, mention):
        if mention.in_reply_to_status_id:
            viewed_tweet = self.api.get_status(mention.in_reply_to_status_id)
            if viewed_tweet.in_reply_to_status_id:
                print('This is a comment')
                await self.reply_blocked_tweet(mention, viewed_tweet.in_reply_to_status_id)
                return True
        return False

    async def tweet_reaction(self, mention):
        try:
            retweet = await self.blocked_retweet(mention)
            if not retweet:
                comment = await self.blocked_comment(mention)
                if not comment:
                    msg = 'לצערי אין תגובה ואין ריטוויט (או שהמשתמש נעול, או שהציוץ נמחק)'
                    print(msg)
                    self.api.update_status(status='@' + mention.user.screen_name + ' ' + msg,
                                           in_reply_to_status_id=mention.id)
        except tweepy.TweepError as err:
            try:
                if err.api_code == ApiError.RESTRICTED_TWEET.value:
                    msg = 'אין לי אפשרות לצפות בציוצים של המשתמש הזה (אולי הוא נעול?)'
                    print(msg)
                    self.api.update_status(status='@' + mention.user.screen_name + ' ' + msg,
                                           in_reply_to_status_id=mention.id)
                else:
                    print('Error! ' + str(err))
            except tweepy.TweepError as another_err:
                print('Error! ' + str(another_err))

    def run(self):
        pyppeteer.chromium_downloader.download_chromium()
        last_mention = int(self.db.child("last_mention_id").get().val())
        max_mention_id = last_mention
        while True:
            try:
                print('getting mentions since ' + str(max_mention_id))
                mentions = self.api.mentions_timeline(count=1, since_id=max_mention_id)
                for mention in mentions:
                    last_mention = mention.id
                    if last_mention > max_mention_id:
                        max_mention_id = last_mention
                    print('Mention by: @' + mention.user.screen_name)
                    if mention.user.id != self.api.me().id and self.is_mention_inside_text(mention):
                        asyncio.get_event_loop().run_until_complete(self.tweet_reaction(mention))
                print('writing ' + str(max_mention_id) + ' to DB')
                self.db.child("last_mention_id").set(str(max_mention_id))
                time.sleep(15)
            except tweepy.TweepError as exp:
                print('Error! ' + str(exp))


auth = tweepy.OAuthHandler(os.environ['SCREENSHOT_CONSUMER_KEY'], os.environ['SCREENSHOT_CONSUMER_VALUE'])
auth.set_access_token(os.environ['SCREENSHOT_ACCESS_TOKEN_KEY'], os.environ['SCREENSHOT_ACCESS_TOKEN_VALUE'])

firebase_config = {
    "apiKey": os.environ['FIREBASE_API_KEY'],
    "authDomain": os.environ['FIREBASE_AUTH_DOMAIN'],
    "databaseURL": os.environ['FIREBASE_DB_URL'],
    "storageBucket": os.environ['FIREBASE_STORAGE_BUCKET']
}

tweepy_api = tweepy.API(auth, wait_on_rate_limit=True)
firebase = pyrebase.initialize_app(firebase_config)

bot = ScreenshotForBlocked(tweepy_api, firebase.database())
bot.run()
