import asyncio
import logging
import os

import pyppeteer
import tweepy
from mention_bot import MentionAction

from .api_error import ApiError


def get_all_links_from_tweet(tweet):
    links = ''
    if 'urls' in tweet.entities:
        for url in tweet.entities['urls']:
            links += url['url'] + '\n'
    return links


class ScreenshotForBlocked(MentionAction):
    def __init__(self, api, timeout, is_production):
        self.api = api
        self.logger = logging.getLogger(__name__)
        self.twitter_status_url = os.environ.get('TWITTER_STATUS_URL', 'https://twitter.com/{}/status/{}')
        self.dark_mode_options = os.environ.get('DARK_MODE_OPTIONS', 'dark').split(',')
        self.timeout = timeout
        self.is_production_mode = is_production

    async def screenshot_tweet(self, tweet_id, path_to_image, is_dark_mode=False):
        browser = None
        try:
            self.logger.debug('Started screenshotting')
            tweet_url = self.twitter_status_url.format('AnyUser', tweet_id)
            result = self.api.get_oembed(tweet_url, theme=('dark' if is_dark_mode else ''))
            tweet_html = result['html'].strip()
            browser = await pyppeteer.launch(args=['--no-sandbox'])
            page = await browser.newPage()
            await page.setContent(tweet_html)
            await page.waitForSelector('iframe', {'visible': True})
            await page.waitFor(2 * 1000)
            tweet_frame = await page.querySelector('iframe')
            await tweet_frame.screenshot({'path': path_to_image})
            self.logger.debug('Finished screenshotting')
        finally:
            if browser is not None:
                await browser.close()

    def reply_to_mention_with_screenshot(self, mention, tweet_to_screenshot_id, add_to_status=''):
        path_to_file = str(tweet_to_screenshot_id) + '.png'
        is_dark_mode = any(dark in mention.text.lower() for dark in self.dark_mode_options)
        status = '@' + mention.user.screen_name + ' ' + add_to_status
        asyncio.run(
            asyncio.wait_for(self.screenshot_tweet(tweet_to_screenshot_id, path_to_file, is_dark_mode),
                             self.timeout))
        if self.is_production_mode:
            media = self.api.media_upload(path_to_file)
            try:
                self.api.update_status(status=status, in_reply_to_status_id=mention.id,
                                       media_ids=[media.media_id])
            except tweepy.TweepError as twe:
                if twe.api_code == ApiError.RESTRICTED_COMMENTS.value:
                    text = '???????? ???????? ???? ???????????? ?????????? ???? ?????????? ????????????, ?????? ?????????? ????????????'
                    self.logger.info('Cannot comment on mention. sending DM instead of replying')
                    self.api.send_direct_message(recipient_id=mention.user.id, text=text, attachment_type='media',
                                                 attachment_media_id=media.media_id)
                else:
                    raise twe
            else:
                self.logger.info('Reply is successful. path_to_file: {}, status: {}, in_reply_to_status_id: {}, '
                                 'is_dark_mode: {}'
                                 .format(path_to_file, status, mention.id, is_dark_mode))
            finally:
                if os.path.exists(path_to_file):
                    self.logger.debug('removing media file')
                    os.remove(path_to_file)
        else:
            self.logger.info('TESTING MODE - path_to_file: {}, status: {}, in_reply_to_status_id: {}, '
                             'is_dark_mode: {}'
                             .format(path_to_file, status, mention.id, is_dark_mode))

    def reply_blocked_tweet(self, mention, tweet_id):
        links = ''
        try:
            blocked_tweet = self.api.get_status(tweet_id)
            links = get_all_links_from_tweet(blocked_tweet)
        except tweepy.TweepError as twe:
            self.logger.warning('Cannot get links - the user blocked me or they are locked')
        self.reply_to_mention_with_screenshot(mention, tweet_id, links)

    def no_retweet_or_comment(self, mention, viewed_tweet):
        msg = '?????????? ?????? ?????????? ???????? ?????????????? (???? ?????????????? ????????, ???? ???????????? ????????)'
        if viewed_tweet.user.id == self.api.me().id:
            msg = '?????????? ???? ?????????? ?????????????? ?????? ??????? ?????? ????????, ?????'
        self.logger.info(msg)
        if self.is_production_mode:
            self.api.update_status(status='@' + mention.user.screen_name + ' ' + msg,
                                   in_reply_to_status_id=mention.id)

    def blocked_retweet_or_comment(self, mention):
        viewed_tweet = self.api.get_status(mention.in_reply_to_status_id)
        if viewed_tweet.is_quote_status and hasattr(viewed_tweet, 'quoted_status_id'):
            self.logger.info('Found a retweet')
            self.reply_blocked_tweet(mention, viewed_tweet.quoted_status_id)
            return True
        elif viewed_tweet.in_reply_to_status_id:
            self.logger.info('Found a comment')
            self.reply_blocked_tweet(mention, viewed_tweet.in_reply_to_status_id)
            return True
        self.no_retweet_or_comment(mention, viewed_tweet)
        return False

    def tweet_reaction(self, mention):
        try:
            self.blocked_retweet_or_comment(mention)
        except tweepy.TweepError as err:
            try:
                msg = str(err)
                if err.api_code == ApiError.RESTRICTED_TWEET.value or err.response.status_code == 403:
                    msg = '?????? ???? ???????????? ?????????? ?????????????? ???? ???????????? ?????? (???????? ?????? ?????????)'
                elif err.api_code == ApiError.BLOCKED_TWEET.value:
                    msg = '???? ???????? ???????? ???????? ???? ???????????? ?????????? ????'
                elif err.api_code == ApiError.NO_TWEET_WITH_ID.value or err.api_code == ApiError.URL_DOESNT_EXIST.value:
                    msg = '???? ???????????? ?????????? ???? ?????????? (???????? ?????? ?????????)'
                if msg != str(err):
                    if self.is_production_mode:
                        self.api.update_status(status='@' + mention.user.screen_name + ' ' + msg,
                                               in_reply_to_status_id=mention.id)
                    else:
                        pass
                self.logger.warning(msg)
            except tweepy.TweepError as another_err:
                self.logger.warning('Unexpected error occurred. error: {}'.format(str(another_err)))

    def run(self, mention):
        self.tweet_reaction(mention)

    def setup(self):
        pyppeteer.chromium_downloader.download_chromium()
