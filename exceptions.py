class SettingsError(Exception):
    """
    Gets raised when the settings.cfg file is missing.
    """


class SkipThis(Exception):
    """
    Gets raised when a subreddit or function needs to be skipped.
    """
