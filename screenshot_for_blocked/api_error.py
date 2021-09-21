from enum import Enum


class ApiError(Enum):
    URL_DOESNT_EXIST = 34
    BLOCKED_TWEET = 136
    NO_TWEET_WITH_ID = 144
    RESTRICTED_TWEET = 179
    RESTRICTED_COMMENTS = 433
