import pyrebase

from service import Service


class FirebaseService(Service):
    def __init__(self, firebase_config):
        self.db = pyrebase.initialize_app(firebase_config).database()

    def get_last_mention(self):
        return self.db.child('last_mention_id').get().val()

    def set_last_mention(self, last_mention):
        self.db.child('last_mention_id').set(str(last_mention))
