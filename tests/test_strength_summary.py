"""Series de fuerza: el resumen de Garmin Connect manda cuando se editó después en la app (el FIT no cambia)."""

from garmin_stats import extras as E

EDITED = {"summarizedExerciseSets": [
    {"category": "CALF_RAISE", "subCategory": "STANDING_CALF_RAISE", "reps": 30, "volume": 300000, "sets": 3, "maxWeight": 10000},
    {"category": "PLANK", "subCategory": "EXTENDED_PLANK", "reps": 0, "volume": 0, "sets": 2, "maxWeight": 0, "duration": 120000.0},
    {"category": "SQUAT", "reps": 34, "volume": 1600000, "sets": 4, "maxWeight": 50000},
]}


def test_summary_becomes_sets_with_even_reps_and_average_weight():
    sets = E.sets_from_summary(EDITED)
    assert [(s["ex"], s["reps"], s["kg"]) for s in sets if s["ex"] == "Gemelos"] == [("Gemelos", 10, 10.0)] * 3
    squat = [s for s in sets if s["ex"] == "Sentadilla"]
    assert [s["reps"] for s in squat] == [9, 9, 8, 8] and squat[0]["kg"] == 47.1
    plank = [s for s in sets if s["ex"] == "Plancha"]
    assert [(s["reps"], s["dur"]) for s in plank] == [(0, 60), (0, 60)]  # por tiempo: 2 series de 1 min
    assert squat[0]["kgMax"] == 50.0 and "kgMax" not in sets[0]  # no todas las sentadillas pesaron igual


def test_edited_in_connect_wins_over_the_watch_file():
    fit = [{"ex": "Sentadilla", "reps": 8, "kg": 0.0, "dur": 54}]  # el reloj no guardó pesos
    best = E.best_sets(fit, EDITED)
    assert len(best) == 9 and best != fit
    assert {s["name"] for s in best} >= {"Plancha extendida"}  # nombre concreto en castellano


def test_untouched_session_keeps_the_per_set_detail_of_the_watch():
    fit = [{"ex": "Gemelos", "reps": r, "kg": 10.0, "dur": 30} for r in (12, 10, 8)]
    same = {"summarizedExerciseSets": [{"category": "CALF_RAISE", "reps": 30, "volume": 300000, "sets": 3, "maxWeight": 10000}]}
    assert E.best_sets(fit, same) is fit
    assert E.best_sets(fit, {}) is fit
    assert E.best_sets([], {"summarizedExerciseSets": [{"category": "MYSTERY", "reps": 3, "sets": 1}]}) == []


def test_timed_exercises_are_added_to_an_untouched_watch_session():
    fit = [{"ex": "Gemelos", "reps": r, "kg": 10.0, "dur": 30} for r in (12, 10, 8)]
    a = {"summarizedExerciseSets": [{"category": "CALF_RAISE", "reps": 30, "volume": 300000, "sets": 3, "maxWeight": 10000},
                                    {"category": "PLANK", "subCategory": "EXTENDED_PLANK", "reps": 0, "sets": 3, "duration": 135000.0}]}
    best = E.best_sets(fit, a)
    assert best[:3] == fit and [(s["name"], s["dur"]) for s in best[3:]] == [("Plancha extendida", 45)] * 3
