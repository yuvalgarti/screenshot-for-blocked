import asyncio
import pyppeteer
import tweepy
import os
import time

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
    

async def screenshot_quoted_tweet(api, tweet_id, path_to_image):
    tweet = api.get_status(tweet_id)
    if hasattr(tweet, 'quoted_status'):
        await screenshot_tweet(api, tweet.quoted_status.id_str, path_to_image)
    else:
        raise NoRetweetException('No quoted tweet')
        
async def reply_to_tweet_with_screenshot(api, tweet_id, path_to_image):
    tweet = api.get_status(tweet_id)
    user = tweet.user
    print('screenshotting tweet')
    try:
        await screenshot_quoted_tweet(api, tweet_id, path_to_image)
        print('uploading tweet')
        api.update_with_media(path_to_image, status='@'+user.screen_name, in_reply_to_status_id=tweet_id)
        if os.path.exists(path_to_image):
            os.remove(path_to_image)
        else:
            print(path_to_image + ' does not exist')
    except NoRetweetException as exp:
        msg = 'אין מה לצלם פה...'
        api.update_status(status='@'+user.screen_name + ' ' + msg, in_reply_to_status_id=tweet_id)


async def reply_to_mention_with_screenshot(api, mention, path_to_image):
    tweet = api.get_status(mention.id)
    user = tweet.user
    try:
        print('screenshotting quoted tweet of tweet id: ' + str(mention.in_reply_to_status_id))
        await screenshot_quoted_tweet(api, mention.in_reply_to_status_id, path_to_image)
        print('uploading screenshot in reply to mention id: ' + mention.id_str)
        api.update_with_media(path_to_image, status='@'+user.screen_name, in_reply_to_status_id=mention.id)
        if os.path.exists(path_to_image):
            os.remove(path_to_image)
        else:
            print(path_to_image + ' does not exist')
    except NoRetweetException as exp:
        msg = 'אין מה לצלם פה...'
        api.update_status(status='@'+user.screen_name + ' ' + msg, in_reply_to_status_id=mention.id)


def run(api):
    last_mention = 1
    with open('last_mention.txt', 'r') as last_mention_file:
        last_mention = int(last_mention_file.read())
    while True:
        print('getting mentions since ' + str(last_mention))
        mentions = api.mentions_timeline(count=1, since_id=last_mention)
        max_mention_id = 0
        for mention in mentions:
            last_mention = mention.id
            if last_mention > max_mention_id:
                max_mention_id = last_mention
            print('Mention by: @' + mention.user.screen_name)
            asyncio.get_event_loop().run_until_complete(reply_to_mention_with_screenshot(api, mention, mention.id_str + '.png'))
        print('writing ' + str(max_mention_id) + ' to last_mention_file.txt')
        with open('last_mention.txt', 'w') as last_mention_file:
            last_mention_file.write(str(max_mention_id))
        time.sleep(15)




pyppeteer.chromium_downloader.download_chromium()

auth = tweepy.OAuthHandler(os.environ['SCREENSHOT_CONSUMER_KEY'], os.environ['SCREENSHOT_CONSUMER_VALUE'])
auth.set_access_token(os.environ['SCREENSHOT_ACCESS_TOKEN_KEY'], os.environ['SCREENSHOT_ACCESS_TOKEN_VALUE'])

api = tweepy.API(auth, wait_on_rate_limit=True)

id = 1421511310051840003
file = str(id) + '.png'
#run(api)
while True:
    print('start screenshot')
    asyncio.get_event_loop().run_until_complete(screenshot_tweet(api, id, file))
    if os.path.exists(file):
        print('removing file')
        os.remove(file)
    print('sleeping')
    time.sleep(15)