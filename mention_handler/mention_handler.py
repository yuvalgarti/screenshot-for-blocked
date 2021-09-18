import asyncio
import logging
import os
import time

import tweepy


class MentionHandler:
    def __init__(self, api, mention_action, last_mention_service, timeout=30, retry_count=3):
        self.api = api
        self.mention_action = mention_action
        self.last_mention_service = last_mention_service
        self.logger = logging.getLogger(__name__)
        self.timeout = timeout
        self.retry_count = retry_count

    def is_mention_inside_text(self, mention):
        extended_mention = self.api.get_status(mention.id, tweet_mode='extended')
        blocked_screen = '@' + self.api.me().screen_name
        start_text = int(extended_mention.display_text_range[0])
        end_text = int(extended_mention.display_text_range[1])
        return blocked_screen in extended_mention.full_text[start_text:end_text]

    def handle_mention_with_retries(self, mention, retries_count=3):
        for i in range(retries_count):
            try:
                asyncio.get_event_loop().run_until_complete(
                    asyncio.wait_for(self.mention_action.run(mention), self.timeout))
                break
            except asyncio.exceptions.TimeoutError:
                self.logger.warning('Timeout occurred! mention id: ' + str(mention.id))
            except tweepy.TweepError as tweepy_exp:
                raise tweepy_exp
            except Exception as exp:
                if i < retries_count - 1:
                    self.logger.warning('Failed to tweet reaction due to unknown error.'
                                        ' trying again... retry count: {}/{}'.format(i + 1, retries_count))
                else:
                    self.logger.error('Failed to screenshot. will not try again')
                    raise exp

    def handle_mentions(self, mentions):
        for mention in mentions:
            self.logger.info('Mention by: @' + mention.user.screen_name)
            if mention.user.id != self.api.me().id and self.is_mention_inside_text(mention) and \
                    mention.in_reply_to_status_id is not None:
                self.handle_mention_with_retries(mention, self.retry_count)
            else:
                self.logger.info('should not reply - mention by me or no mention inside text')

    def run(self):
        self.mention_action.setup()
        max_mention_id = int(self.last_mention_service.get_last_mention())
        mentions_per_request = os.environ.get('MENTIONS_PER_REQUEST', 5)
        self.logger.info('mentions per request: {}'.format(mentions_per_request))
        while True:
            try:
                self.logger.debug('getting mentions since ' + str(max_mention_id))
                mentions = self.api.mentions_timeline(count=mentions_per_request, since_id=max_mention_id)
                mentions.sort(key=lambda tweet: tweet.id)
                self.handle_mentions(mentions)
                if mentions:
                    max_mention_id = mentions[-1].id
                    self.logger.info('writing ' + str(max_mention_id) + ' to DB')
                    self.last_mention_service.set_last_mention(str(max_mention_id))
                time.sleep(15)
            except tweepy.TweepError as exp:
                self.logger.warning('Unexpected Tweepy error occurred. error: {}'.format(str(exp)))
            except Exception as unknown_exp:
                self.logger.exception('ERROR! {}'.format(str(unknown_exp)))
