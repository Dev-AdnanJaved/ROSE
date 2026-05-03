from app.core.config import Config

def get_tp(cap):

    if cap == "LOW":
        return Config.LOW_CAP_TP

    if cap == "MID":
        return Config.MID_CAP_TP

    return Config.BIG_CAP_TP