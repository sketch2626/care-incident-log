"""Voice comfort: slower, faster, quieter, louder, and switching between Mary and Sam. No screen."""

# Copied from server.VOICE_LIMITS (a skill may not import server); a test keeps them equal.
RATE_MIN, RATE_MAX, RATE_DEFAULT = 0.6, 1.4, 0.92
VOLUME_MIN, VOLUME_MAX, VOLUME_DEFAULT = 0.2, 1.0, 1.0
RATE_STEP, VOLUME_STEP = 0.08, 0.1
# M4a: copied from server.VOICE_LIMITS["listen_wait"]: seconds of quiet before she answers
WAIT_MIN, WAIT_MAX, WAIT_DEFAULT = 1.5, 6.0, 2.5


def _number(ctx, key, default, low, high):
    """The saved setting as a number inside its range."""
    try:
        value = float(ctx.settings_get(key, default))
    except (TypeError, ValueError):
        value = default
    return min(high, max(low, value))


def _step(ctx, key, default, low, high, delta, limit_line):
    cur = _number(ctx, key, default, low, high)
    ctx.state[key] = cur
    nxt = round(min(high, max(low, cur + delta)), 2)
    if nxt == cur:
        return {key: cur, "changed": False, "say": limit_line}
    ctx.settings_put(key, nxt)
    ctx.state[key] = nxt
    return {key: nxt, "changed": True, "say": "Is this better?"}


def slower(ctx):
    out = _step(ctx, "voice_rate", RATE_DEFAULT, RATE_MIN, RATE_MAX, -RATE_STEP,
                "I'm already as slow as I can go.")
    out["note"] = "Speak noticeably slower from now on."  # M4a: a Live session adapts on the spot
    return out


def faster(ctx):
    out = _step(ctx, "voice_rate", RATE_DEFAULT, RATE_MIN, RATE_MAX, RATE_STEP,
                "I'm already as fast as I can go.")
    out["note"] = "Speak a little faster from now on."  # M4a
    return out


def more_time(ctx):  # M4a: wait longer before answering
    cur = _number(ctx, "listen_wait", WAIT_DEFAULT, WAIT_MIN, WAIT_MAX)
    ctx.state["listen_wait"] = cur
    if cur >= WAIT_MAX:
        return {"listen_wait": cur, "changed": False, "say": "I'll wait as long as I can for you."}
    nxt = round(min(WAIT_MAX, cur + 1.0 if cur >= 4.0 else 4.0), 2)
    ctx.settings_put("listen_wait", nxt)
    ctx.state["listen_wait"] = nxt
    return {"listen_wait": nxt, "changed": True,
            "say": "All right, I'll give you more time to finish. Take all the time you need."}


def less_time(ctx):  # M4a
    ctx.settings_put("listen_wait", WAIT_DEFAULT)
    ctx.state["listen_wait"] = WAIT_DEFAULT
    return {"listen_wait": WAIT_DEFAULT, "changed": True, "say": "All right, I'll answer a little quicker."}


def quieter(ctx):
    return _step(ctx, "voice_volume", VOLUME_DEFAULT, VOLUME_MIN, VOLUME_MAX, -VOLUME_STEP,
                 "I'm already as quiet as I can be.")


def louder(ctx):
    return _step(ctx, "voice_volume", VOLUME_DEFAULT, VOLUME_MIN, VOLUME_MAX, VOLUME_STEP,
                 "I'm already as loud as I can be. You can turn up the computer's sound too.")


def switch_companion(ctx):
    now = "mary" if ctx.settings_get("companion", "mary") == "him" else "him"  # unset ("") means Mary
    ctx.settings_put("companion", now)
    ctx.state["companion"] = now
    say = ("Hi, I'm Sam. It's nice to meet you." if now == "him"
           else "Hi, I'm Mary. It's so nice to meet you.")
    return {"companion": now, "say": say}


def view(state):
    """What Mary knows: the numbers last set or seen in this run (the defaults until then)."""
    name = "Sam" if state.get("companion") == "him" else "Mary"
    return (f"Speaking speed {state.get('voice_rate', RATE_DEFAULT)} ({RATE_MIN}-{RATE_MAX}), "
            f"volume {state.get('voice_volume', VOLUME_DEFAULT)}, companion {name}, "
            f"waits {state.get('listen_wait', WAIT_DEFAULT)} s before answering.")  # M4a
