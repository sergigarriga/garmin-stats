from datetime import date, timedelta

from garmin_stats import odds


def test_goal_seconds_formats():
    assert odds.goal_seconds("1:30", 21097.5) == 5400
    assert odds.goal_seconds("45:00", 10000) == 2700
    assert odds.goal_seconds("45.00", 10000) == 2700
    assert odds.goal_seconds("1:35:40", 21097.5) == 5740
    assert odds.goal_seconds("45", 10000) == 2700
    assert odds.goal_seconds("", 10000) is None


def _plan(goal_time, weeks_ahead=12, status="done"):
    t = date.today()
    sess = [{"date": (t - timedelta(days=i)).isoformat(), "status": status} for i in range(1, 15)]
    return {"goal": "10 km", "goalTime": goal_time, "raceDate": (t + timedelta(weeks=weeks_ahead)).isoformat(),
            "weeks": [{"sessions": sess}]}


def test_probability_moves_with_goal_and_adherence():
    paces = {"vdot": 45.0, "source": "race", "stale": False}
    easy = odds.compute(_plan("50:00"), paces)
    hard = odds.compute(_plan("40:00"), paces)
    assert easy["pct"] > 90 and hard["pct"] < 10
    lazy = odds.compute(_plan("45:00", status="missed"), paces)
    keen = odds.compute(_plan("45:00"), paces)
    assert keen["pct"] > lazy["pct"] and lazy["gain"] == 0


def test_no_goal_time_no_odds():
    assert odds.compute(_plan(None), {"vdot": 45}) is None
