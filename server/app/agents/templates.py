"""A deterministic reply writer: sentences filled from facts, each citing what it uses.

Two users: the offline demo model (``LLM_PROVIDER=fake``) answers with it, and the chat
agent falls back to it if every sentence Claude wrote was dropped by the citation check,
so a passenger always gets an answer built only from computed facts.

It reads the same payload the real model gets: ``{"kind", "language", "facts": [...]}``.
"""

from __future__ import annotations

from typing import Any

from app.schemas.llm import ChatReply, Claim


class _Facts:
    def __init__(self, facts: list[dict[str, Any]]) -> None:
        self.by_id = {f["id"]: f["value"] for f in facts}

    def has(self, *ids: str) -> bool:
        return all(i in self.by_id for i in ids)

    def __getitem__(self, fact_id: str) -> Any:
        return self.by_id[fact_id]

    def m(self, fact_id: str) -> str:
        """A number of minutes, rounded."""
        return f"{float(self.by_id[fact_id]):.0f}"


def write_reply(payload: dict[str, Any]) -> ChatReply:
    f = _Facts(payload.get("facts", []))
    hi = payload.get("language") == "hinglish"
    kind = payload.get("kind")
    claims: list[Claim] = []
    if kind == "train_status":
        claims += _status(f, hi)
        claims += _badge(f, hi)
    elif kind == "train_history":
        claims += _badge(f, hi, history=True)
    elif kind == "hotspots":
        claims += _hotspots(f, hi)
    return ChatReply(claims=claims)


def _claim(text: str, *ids: str) -> Claim:
    return Claim(text=text, fact_ids=list(ids))


def _status(f: _Facts, hi: bool) -> list[Claim]:
    who = f"{f['train.name']} ({f['train.number']})"
    state = f["live.state"] if f.has("live.state") else None
    if state == "not_started":
        origin, at = f["train.from"], f["live.scheduled_departure"]
        text = (
            f"{who} abhi {origin} se nikli nahi hai; departure time {at} hai."
            if hi
            else f"{who} has not left {origin} yet; it is scheduled to depart at {at}."
        )
        return [
            _claim(text, "train.name", "train.number", "train.from", "live.scheduled_departure")
        ]

    place, at, delay = f["live.last_station_name"], f["live.last_event_at"], f.m("live.delay_min")
    ids = ("train.name", "train.number", "live.last_station_name", "live.last_event_at")
    if state == "arrived":
        text = (
            f"{who} {at} baje {place} pahunch gayi, {delay} min late."
            if hi
            else f"{who} reached {place} at {at}, {delay} min late."
        )
        return [_claim(text, *ids, "live.delay_min")]

    out: list[Claim] = []
    late = float(f["live.delay_min"]) > 0
    if hi:
        verb = "pahunchi" if f["live.last_event"] == "arrived at" else "se nikli"
        running = f"abhi {delay} min late chal rahi hai" if late else "time pe chal rahi hai"
        text = f"{who} {at} baje {place} {verb}, {running}."
    else:
        running = f"running {delay} min late" if late else "running on time"
        text = f"{who} {f['live.last_event']} {place} at {at} and is {running}."
    out.append(_claim(text, *ids, "live.last_event", "live.delay_min"))

    if f.has("live.unusual", "live.usual_median") and f["live.unusual"]:
        usual = f.m("live.usual_median")
        text = (
            f"Aaj ka delay normal se kaafi zyada hai: yahan yeh aam taur pe {usual} min "
            "late hoti hai."
            if hi
            else f"That is far worse than usual: it is normally {usual} min late here."
        )
        out.append(_claim(text, "live.unusual", "live.usual_median"))
    if f.has("live.target.eta_p50"):
        out.append(_eta(f, "live.target", hi))
    elif f.has("live.target.passed"):
        name = f["live.target.station_name"]
        text = (
            f"Yeh {name} pehle hi cross kar chuki hai." if hi else f"It has already passed {name}."
        )
        out.append(_claim(text, "live.target.passed", "live.target.station_name"))
    if f.has("live.next.eta_p50"):
        out.append(_eta(f, "live.next", hi))
    if f.has("live.destination.eta_p50"):
        out.append(_eta(f, "live.destination", hi))
    return out


def _eta(f: _Facts, prefix: str, hi: bool) -> Claim:
    name = f[f"{prefix}.station_name"]
    p50, p90 = f[f"{prefix}.eta_p50"], f[f"{prefix}.eta_p90"]
    ids = [f"{prefix}.station_name", f"{prefix}.eta_p50", f"{prefix}.eta_p90"]
    if prefix == "live.target":
        d50, d90 = f.m(f"{prefix}.p50_delay"), f.m(f"{prefix}.p90_delay")
        ids += [f"{prefix}.p50_delay", f"{prefix}.p90_delay"]
        text = (
            f"{name} pe lagbhag {p50} tak pahunchegi ({d50} min late); "
            f"der hui toh {p90} tak ({d90} min)."
            if hi
            else f"Expect it at {name} around {p50}, {d50} min late; "
            f"in a bad case by {p90} ({d90} min late)."
        )
    elif prefix == "live.next":
        due = f[f"{prefix}.sched"]
        ids.append(f"{prefix}.sched")
        text = (
            f"Agla station {name}: time {due}, ummeed {p50} tak (der hui toh {p90})."
            if hi
            else f"Next stop {name}: due {due}, likely {p50} (by {p90} in a bad case)."
        )
    else:
        text = (
            f"{name} lagbhag {p50} tak (der hui toh {p90})."
            if hi
            else f"It should reach {name} around {p50} (by {p90} in a bad case)."
        )
    return Claim(text=text, fact_ids=ids)


def _badge(f: _Facts, hi: bool, history: bool = False) -> list[Claim]:
    if not f.has("badge.mean"):
        return []
    out: list[Claim] = []
    ids = ["badge.window_days", "badge.station_name", "badge.mean", "badge.median"]
    ids.append("badge.on_time_pct")
    if history and f.has("train.number"):
        ids += ["train.name", "train.number"]
        who = f"{f['train.name']} ({f['train.number']})"
    else:
        who = "yeh" if hi else "it"
    days, place = f["badge.window_days"], f["badge.station_name"]
    mean, median, on_time = f.m("badge.mean"), f.m("badge.median"), f.m("badge.on_time_pct")
    text = (
        f"Pichhle {days} din ke hisaab se {who} {place} average {mean} min late pahunchti hai "
        f"(median {median} min), aur {on_time}% din time pe."
        if hi
        else f"Based on the last {days} days, {who} reaches {place} {mean} min late on average "
        f"(median {median} min) and is on time on {on_time}% of days."
    )
    out.append(Claim(text=text, fact_ids=ids))
    if history:
        p90, margin = f.m("badge.p90"), f["badge.on_time_minutes"]
        text = (
            f"Bure din (p90) pe {p90} min tak late; on time matlab {margin} min ke andar."
            if hi
            else f"On a bad day (p90) it is {p90} min late; on time means within {margin} min."
        )
        out.append(_claim(text, "badge.p90", "badge.on_time_minutes"))
    if f.has("badge.month", "badge.month_mean"):
        month, month_mean = f["badge.month"], f.m("badge.month_mean")
        text = (
            f"{month} mein yahan average {month_mean} min late rahi hai."
            if hi
            else f"In {month} it has averaged {month_mean} min late there."
        )
        out.append(_claim(text, "badge.month", "badge.month_mean"))
    return out


def _hotspots(f: _Facts, hi: bool) -> list[Claim]:
    if not f.has("hotspots.1.station"):
        return []
    period = f["hotspots.period"]
    if period == "all year":
        when = "Poore saal" if hi else "Over the whole year"
    else:
        when = f"{period} mein" if hi else f"In {period}"
    name, code = f["hotspots.1.name"], f["hotspots.1.station"]
    added, low, high = f.m("hotspots.1.added"), f.m("hotspots.1.ci_low"), f.m("hotspots.1.ci_high")
    text = (
        f"{when} sabse zyada delay {name} ({code}) se pehle judta hai: average {added} min "
        f"(range {low} to {high} min)."
        if hi
        else f"{when}, trains lose the most time approaching {name} ({code}): {added} min "
        f"added on average (likely range {low} to {high} min)."
    )
    top_ids = ("hotspots.period", "hotspots.1.name", "hotspots.1.station", "hotspots.1.added")
    out = [_claim(text, *top_ids, "hotspots.1.ci_low", "hotspots.1.ci_high")]

    others = [k for k in ("hotspots.2", "hotspots.3") if f.has(f"{k}.name", f"{k}.added")]
    if others:
        parts = [f"{f[k + '.name']} ({f.m(k + '.added')} min)" for k in others]
        joined = (" aur " if hi else " and ").join(parts)
        text = f"Uske baad {joined}." if hi else f"Next come {joined}."
        out.append(_claim(text, *[i for k in others for i in (f"{k}.name", f"{k}.added")]))

    if (
        f.has("hotspots.naive_top", "hotspots.naive_top.arrival")
        and f["hotspots.naive_top"] != code
    ):
        naive = f["hotspots.naive_top"]
        arrival = f.m("hotspots.naive_top.arrival")
        naive_added = float(f["hotspots.naive_top.added"])
        gained = f.m("hotspots.naive_top.added")
        inherited = f.m("hotspots.naive_top.inherited")
        if naive_added > 0.5:
            text = (
                f"{naive} pe arrival delay sabse zyada ({arrival} min) dikhta hai, par usme se "
                f"sirf {gained} min wahan judta hai; baaki {inherited} min pichhle stations se "
                "aata hai."
                if hi
                else f"{naive} has the worst arrival delay ({arrival} min), but only {gained} min "
                f"of it is added there; {inherited} min is inherited from earlier stops."
            )
        else:
            recovered = f"{abs(naive_added):.0f}"
            text = (
                f"{naive} pe arrival delay sabse zyada ({arrival} min) dikhta hai, par wahan delay "
                f"judta nahi: {inherited} min pichhle stations se aata hai, aur aakhri section pe "
                f"train {recovered} min recover karti hai."
                if hi
                else f"{naive} has the worst arrival delay ({arrival} min), but none of it is "
                f"added there: {inherited} min is inherited from earlier stops, and trains recover "
                f"{recovered} min on the last section."
            )
        out.append(
            _claim(
                text,
                "hotspots.naive_top",
                "hotspots.naive_top.arrival",
                "hotspots.naive_top.added",
                "hotspots.naive_top.inherited",
            )
        )
    return out
