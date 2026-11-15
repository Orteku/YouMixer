"""YouMixer: true shuffle and personal mixes with music from YouTube, running locally."""
import time


def log(*parts):
    """Timestamped line for the console, or for data/youmixer.log when there is no console."""
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *parts, flush=True)
