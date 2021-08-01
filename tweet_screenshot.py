import asyncio
import pyppeteer
import tweepy
import os
import time
import pyrebase


class NoRetweetException(Exception):
    pass


async def screenshot_tweet(api, tweet_id, path_to_image):
    tweet = api.get_status(tweet_id)
    tweet_url = os.environ['TWITTER_STATUS_URL'].format(tweet.user.screen_name, tweet.id_str)
    result = api.get_oembed(tweet_url)
    tweet_html = result['html'].strip()
    browser = await pyppeteer.launch(args=['--no-sandbox'])
    page = await browser.newPage()
    await page.setContent(tweet_html)
    await page.waitForSelector('iframe', {'visible': True})
    await page.waitFor(2 * 1000)
    tweet_frame = await page.querySelector('iframe')
    await tweet_frame.screenshot({'path': path_to_image})
    await browser.close()


async def reply_to_mention_with_screenshot(api, mention, tweet_to_screenshot, add_to_status=''):
    path_to_file = tweet_to_screenshot.id_str + '.png'
    await screenshot_tweet(api, tweet_to_screenshot.id, path_to_file)
    media = api.media_upload(path_to_file)
    status = '@' + mention.user.screen_name + ' ' + add_to_status
    api.update_status(status=status, in_reply_to_status_id=mention.id,
                      media_ids=[media.media_id])
    print('path_to_file: {}, status: {}, in_reply_to_status_id: {}'.format(path_to_file, status,
                                                                           mention.id))
    if os.path.exists(path_to_file):
        os.remove(path_to_file)


def get_all_links_from_tweet(tweet):
    links = ''
    if 'urls' in tweet.entities:
        for url in tweet.entities['urls']:
            links += url['url'] + '\n'
    return links


async def reply_blocked_tweet(api, mention, tweet_id):
    blocked_tweet = api.get_status(tweet_id)
    links = get_all_links_from_tweet(blocked_tweet)
    await reply_to_mention_with_screenshot(api, mention, blocked_tweet, links)


async def blocked_retweet(api, mention):
    if mention.in_reply_to_status_id:
        viewed_tweet = api.get_status(mention.in_reply_to_status_id)
        if hasattr(viewed_tweet, 'quoted_status'):
            print('This is a retweet')
            await reply_blocked_tweet(api, mention, viewed_tweet.quoted_status.id)
            return True
    return False


async def blocked_comment(api, mention):
    if mention.in_reply_to_status_id:
        viewed_tweet = api.get_status(mention.in_reply_to_status_id)
        if viewed_tweet.in_reply_to_status_id:
            print('This is a comment')
            await reply_blocked_tweet(api, mention, viewed_tweet.in_reply_to_status_id)
            return True
    return False


async def tweet_reaction(api, mention):
    retweet = await blocked_retweet(api, mention)
    if not retweet:
        comment = await blocked_comment(api, mention)
        if not comment:
            msg = 'לצערי אין תגובה ואין ריטוויט (או שהמשתמש נעול, או שהציוץ נמחק)'
            print(msg)
            api.update_status(status='@' + mention.user.screen_name + ' ' + msg, in_reply_to_status_id=mention.id)


def run(api, db):
    last_mention = int(db.child("last_mention_id").get().val())
    max_mention_id = last_mention
    while True:
        try:
            print('getting mentions since ' + str(max_mention_id))
            mentions = api.mentions_timeline(count=1, since_id=max_mention_id)
            for mention in mentions:
                last_mention = mention.id
                if last_mention > max_mention_id:
                    max_mention_id = last_mention
                print('Mention by: @' + mention.user.screen_name)
                if mention.user.id != api.me().id:
                    asyncio.get_event_loop().run_until_complete(tweet_reaction(api, mention))
            print('writing ' + str(max_mention_id) + ' to DB')
            db.child("last_mention_id").set(str(max_mention_id))
            time.sleep(15)
        except tweepy.TweepError as exp:
            print('Error! ' + str(exp))


pyppeteer.chromium_downloader.download_chromium()

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

run(tweepy_api, firebase.database())
