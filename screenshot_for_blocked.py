import asyncio
from enum import Enum
import pyppeteer
import time
import logging
import tweepy
import os


class ApiError(Enum):
    URL_DOESNT_EXIST = 34
    BLOCKED_TWEET = 136
    NO_TWEET_WITH_ID = 144
    RESTRICTED_TWEET = 179
    RESTRICTED_COMMENTS = 433


def get_all_links_from_tweet(tweet):
    links = ''
    if 'urls' in tweet.entities:
        for url in tweet.entities['urls']:
            links += url['url'] + '\n'
    return links


class ScreenshotForBlocked:
    def __init__(self, api, service):
        self.api = api
        self.service = service
        self.logger = logging.getLogger('screenshot_for_the_blocked')
        self.timeout = int(os.environ['SCREENSHOT_TIMEOUT'])
        self.max_mention_id = 0

    def is_mention_inside_text(self, mention):
        extended_mention = self.api.get_status(mention.id, tweet_mode='extended')
        blocked_screen = '@' + self.api.me().screen_name
        start_text = int(extended_mention.display_text_range[0])
        end_text = int(extended_mention.display_text_range[1])
        return blocked_screen in extended_mention.full_text[start_text:end_text]

    async def screenshot_tweet(self, tweet_id, path_to_image):
        self.logger.debug('Started screenshotting')
        tweet_url = os.environ['TWITTER_STATUS_URL'].format('AnyUser', tweet_id)
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
        self.logger.debug('Finished screenshotting')

    async def reply_to_mention_with_screenshot(self, mention, tweet_to_screenshot_id, add_to_status=''):
        path_to_file = str(tweet_to_screenshot_id) + '.png'
        await self.screenshot_tweet(tweet_to_screenshot_id, path_to_file)
        media = self.api.media_upload(path_to_file)
        status = '@' + mention.user.screen_name + ' ' + add_to_status
        try:
            self.api.update_status(status=status, in_reply_to_status_id=mention.id,
                                   media_ids=[media.media_id])
        except tweepy.TweepError as twe:
            if twe.api_code == ApiError.RESTRICTED_COMMENTS.value:
                text = 'נראה שאין לי הרשאות להגיב על הציוץ שביקשת, הנה הציוץ המבוקש'
                self.logger.info('Cannot comment on mention. sending DM instead of replying')
                self.api.send_direct_message(recipient_id=mention.user.id, text=text, attachment_type='media',
                                             attachment_media_id=media.media_id)
            else:
                raise twe
        else:
            self.logger.info('Reply is successful. path_to_file: {}, status: {}, in_reply_to_status_id: {}'
                         .format(path_to_file, status, mention.id))
        finally:
            if os.path.exists(path_to_file):
                self.logger.debug('removing media file')
                os.remove(path_to_file)

    async def reply_blocked_tweet(self, mention, tweet_id):
        links = ''
        try:
            blocked_tweet = self.api.get_status(tweet_id)
            links = get_all_links_from_tweet(blocked_tweet)
        except tweepy.TweepError as twe:
            self.logger.warning('Cannot get links - the user blocked me or they are locked')
        await self.reply_to_mention_with_screenshot(mention, tweet_id, links)

    async def blocked_retweet(self, mention):
        if mention.in_reply_to_status_id:
            viewed_tweet = self.api.get_status(mention.in_reply_to_status_id)
            if viewed_tweet.is_quote_status and hasattr(viewed_tweet, 'quoted_status_id'):
                self.logger.info('Found a retweet')
                await self.reply_blocked_tweet(mention, viewed_tweet.quoted_status_id)
                return True
        return False

    async def blocked_comment(self, mention):
        if mention.in_reply_to_status_id:
            viewed_tweet = self.api.get_status(mention.in_reply_to_status_id)
            if viewed_tweet.in_reply_to_status_id:
                self.logger.info('Found a comment')
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
                    self.logger.info(msg)
                    self.api.update_status(status='@' + mention.user.screen_name + ' ' + msg,
                                           in_reply_to_status_id=mention.id)
        except tweepy.TweepError as err:
            try:
                msg = str(err)
                if err.api_code == ApiError.RESTRICTED_TWEET.value or err.response.status_code == 403:
                    msg = 'אין לי אפשרות לצפות בציוצים של המשתמש הזה (אולי הוא נעול?)'
                elif err.api_code == ApiError.BLOCKED_TWEET.value:
                    msg = 'יש ציוץ בדרך שאין לי אפשרות לראות 😰'
                elif err.api_code == ApiError.NO_TWEET_WITH_ID.value or err.api_code == ApiError.URL_DOESNT_EXIST.value:
                    msg = 'לא הצלחתי למצוא את הציוץ (אולי הוא נמחק?)'
                if msg != str(err):
                    self.api.update_status(status='@' + mention.user.screen_name + ' ' + msg,
                                           in_reply_to_status_id=mention.id)
                self.logger.warning(msg)
            except tweepy.TweepError as another_err:
                self.logger.warning('Unexpected error occurred. error: {}'.format(str(another_err)))

    def handle_mentions(self, mentions):
        for mention in mentions:
            last_mention = mention.id
            if last_mention > self.max_mention_id:
                self.max_mention_id = last_mention
            self.logger.info('Mention by: @' + mention.user.screen_name)
            if mention.user.id != self.api.me().id and self.is_mention_inside_text(mention) and \
                    mention.in_reply_to_status_id is not None:
                try:
                    asyncio.get_event_loop().run_until_complete(
                        asyncio.wait_for(self.tweet_reaction(mention), self.timeout))
                except asyncio.exceptions.TimeoutError:
                    self.logger.warning('Timeout occurred! mention id: ' + str(mention.id))
            else:
                self.logger.info('should not reply - mention by me or no mention inside text')

    def run(self):
        pyppeteer.chromium_downloader.download_chromium()
        last_mention = int(self.service.get_last_mention())
        self.max_mention_id = last_mention
        mentions_per_request = os.environ['MENTIONS_PER_REQUEST']
        self.logger.info('mentions per request: {}'.format(mentions_per_request))
        while True:
            try:
                self.logger.debug('getting mentions since ' + str(self.max_mention_id))
                mentions = self.api.mentions_timeline(count=mentions_per_request, since_id=self.max_mention_id)
                self.handle_mentions(mentions)
                if mentions:
                    self.logger.info('writing ' + str(self.max_mention_id) + ' to DB')
                    self.service.set_last_mention(str(self.max_mention_id))
                time.sleep(15)
            except tweepy.TweepError as exp:
                self.logger.warning('Unexpected Tweepy error occurred. error: {}'.format(str(exp)))
            except Exception as unknown_exp:
                self.logger.error('ERROR! {}'.format(str(unknown_exp)))
