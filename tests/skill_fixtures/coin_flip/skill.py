"""Coin flip, a tiny test skill: flips a coin, counts flips in its store, and shows the coin on screen."""
import random


def flip(ctx):
    """Heads or tails, shown on screen, with a short line for offline mode."""
    side = random.choice(["heads", "tails"])
    count = (ctx.store.get("flips") or 0) + 1
    ctx.store.put("flips", count)
    ctx.state["last"] = side
    ctx.effect("show_screen", {"screen": "coin_flip"})
    ctx.effect("coin", {"side": side, "coin": ctx.state.get("coin", "quarter")})
    return {"side": side, "flips": count, "say": f"It's {side}."}


def set_coin(ctx, coin):
    """Which coin the screen shows."""
    ctx.state["coin"] = coin
    ctx.effect("coin", {"coin": coin})
    return {"coin": coin, "say": f"I'll use a {coin}."}


def on_event(ctx, event):
    """A tap on the coin flips it."""
    if event.get("type") == "tap":
        return flip(ctx)
    return {"ignored": True}


def view(state):
    """What Mary sees on the screen."""
    if "last" not in state:
        return "A coin, not flipped yet."
    return f"A {state.get('coin', 'quarter')} showing {state['last']}."
