"""Voice comfort: slower, faster, quieter, louder, and switching between Mary and Sam. No screen."""

# Copied from server.VOICE_LIMITS (a skill may not import server); a test keeps them equal.
RATE_MIN, RATE_MAX, RATE_DEFAULT = 0.6, 1.4, 0.92
VOLUME_MIN, VOLUME_MAX, VOLUME_DEFAULT = 0.2, 1.0, 1.0
RATE_STEP, VOLUME_STEP = 0.08, 0.1


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
    return _step(ctx, "voice_rate", RATE_DEFAULT, RATE_MIN, RATE_MAX, -RATE_STEP,
                 "I'm already as slow as I can go.")


def faster(ctx):
    return _step(ctx, "voice_rate", RATE_DEFAULT, RATE_MIN, RATE_MAX, RATE_STEP,
                 "I'm already as fast as I can go.")


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
            f"volume {state.get('voice_volume', VOLUME_DEFAULT)}, companion {name}.")
