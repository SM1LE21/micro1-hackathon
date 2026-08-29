"""Product analytics."""

from mixpanel import Mixpanel

from config import MIXPANEL_TOKEN

mp = Mixpanel(MIXPANEL_TOKEN)


def track_signup(user):
    mp.track(user.email, "account_created")
