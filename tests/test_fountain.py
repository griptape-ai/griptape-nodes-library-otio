from pathlib import Path

from otio_nodes.fountain import parse

SAMPLE = """Title: Test Film
Author: Someone
Notes: First line
    second line

===

INT. KITCHEN - DAY #1A#

JACK stirs a pot.

JACK (V.O.)
Hello there.

JILL (CONT'D)
(whispering)
Shh.

CUT TO:

EXT. STREET - NIGHT

WIDE SHOT of the street.
"""


def by_type(result: dict, kind: str) -> list[dict]:
    return [e for e in result["elements"] if e["type"] == kind]


def test_title_page_with_multiline_value():
    result = parse(SAMPLE)
    assert result["title_page"] == {"Title": "Test Film", "Author": "Someone", "Notes": "First line\nsecond line"}


def test_fade_in_is_not_a_title_page():
    result = parse("FADE IN:\n\nINT. ROOM - DAY\n\nAction here.\n")
    assert result["title_page"] == {}
    assert result["elements"][0]["text"] == "FADE IN:"


def test_scene_heading_parts_and_number():
    heading = by_type(parse(SAMPLE), "scene_heading")[0]
    assert heading["int_ext"] == "INT"
    assert heading["location"] == "KITCHEN"
    assert heading["time_of_day"] == "DAY"
    assert heading["scene_number"] == "1A"
    assert heading["text"] == "INT. KITCHEN - DAY"


def test_scene_heading_without_time_of_day():
    heading = by_type(parse("INT. HALLWAY\n\nAction.\n"), "scene_heading")[0]
    assert heading["location"] == "HALLWAY"
    assert heading["time_of_day"] == ""


def test_dialogue_extension_continued_and_parenthetical():
    dialogue = by_type(parse(SAMPLE), "dialogue")
    assert dialogue[0]["character"] == "JACK"
    assert dialogue[0]["extension"] == "V.O."
    assert dialogue[0]["text"] == "Hello there."
    assert dialogue[1]["character"] == "JILL"
    assert dialogue[1]["continued"] is True
    assert dialogue[1]["extension"] == ""
    assert dialogue[1]["parentheticals"] == ["whispering"]
    assert dialogue[1]["text"] == "Shh."


def test_transition_and_action():
    result = parse(SAMPLE)
    assert by_type(result, "transition")[0]["text"] == "CUT TO:"
    assert by_type(result, "action")[0]["text"] == "JACK stirs a pot."


def test_scenes_group_elements():
    result = parse(SAMPLE)
    assert [s["heading"] for s in result["scenes"]] == ["INT. KITCHEN - DAY", "EXT. STREET - NIGHT"]
    assert result["scenes"][0]["scene_number"] == "1A"
    scene_of = {e["type"]: e["scene"] for e in result["elements"] if e["type"] == "dialogue"}
    assert scene_of["dialogue"] == 0
    assert by_type(result, "action")[-1]["scene"] == 1


def test_elements_before_first_heading_form_untitled_scene():
    result = parse("Just some action.\n\nINT. ROOM - DAY\n\nMore.\n")
    assert result["scenes"][0]["heading"] == ""
    assert result["scenes"][1]["heading"] == "INT. ROOM - DAY"


def test_line_numbers_are_original_lines():
    result = parse(SAMPLE)
    heading = by_type(result, "scene_heading")[0]
    assert (heading["line_start"], heading["line_end"]) == (8, 8)
    dialogue = by_type(result, "dialogue")[1]
    assert (dialogue["line_start"], dialogue["line_end"]) == (15, 17)


def test_boneyard_is_ignored_and_keeps_line_numbers():
    text = "INT. ROOM - DAY\n\n/* gone\nstill gone */\n\nVisible action.\n"
    result = parse(text)
    actions = by_type(result, "action")
    assert [a["text"] for a in actions] == ["Visible action."]
    assert actions[0]["line_start"] == 6


def test_inline_note_is_removed_and_attached():
    text = "INT. ROOM - DAY\n\nJack waves [[check the wave]] and leaves.\n"
    result = parse(text)
    action = by_type(result, "action")[0]
    assert action["text"] == "Jack waves  and leaves."
    assert action["notes"] == ["check the wave"]


def test_multiline_note_keeps_later_line_numbers():
    text = "INT. ROOM - DAY\n\nJack waves [[a note\nover two lines]] now.\n\nLater action.\n"
    result = parse(text)
    actions = by_type(result, "action")
    assert actions[0]["text"] == "Jack waves  now."
    assert actions[1]["line_start"] == 6


def test_section_synopsis_page_break_centered():
    text = "# Act One\n\n= Jack arrives.\n\n===\n\n>THE END<\n"
    kinds = [e["type"] for e in parse(text)["elements"]]
    assert kinds == ["section", "synopsis", "page_break", "centered"]


def test_forced_elements():
    text = ".FORCED HEADING\n\n!SHOUT\n\n@mcCLOUD\nI am here.\n\n> FADE OUT.\n"
    result = parse(text)
    assert by_type(result, "scene_heading")[0]["text"] == "FORCED HEADING"
    assert by_type(result, "action")[0]["text"] == "SHOUT"
    assert by_type(result, "dialogue")[0]["character"] == "mcCLOUD"
    assert by_type(result, "transition")[0]["text"] == "FADE OUT."


def test_dual_dialogue():
    text = "BRICK\nScrew you.\n\nSTEEL ^\nNo, you.\n"
    dialogue = by_type(parse(text), "dialogue")
    assert [d["dual"] for d in dialogue] == ["left", "right"]


def test_single_uppercase_line_is_action():
    assert by_type(parse("THE END\n"), "action")[0]["text"] == "THE END"


def test_crlf_input():
    result = parse("INT. ROOM - DAY\r\n\r\nAction.\r\n")
    assert [e["type"] for e in result["elements"]] == ["scene_heading", "action"]


SCRIPT = Path(__file__).parent / "fixtures" / "sample_script.fountain"


def test_sample_script():
    result = parse(SCRIPT.read_text(encoding="utf-8"))
    assert result["title_page"]["Title"] == "The Lighthouse Robot"
    headings = [s["heading"] for s in result["scenes"]]
    assert headings[0] == "INT. LIGHTHOUSE KEEPER'S ROOM - DAY"
    assert len(headings) == 7
    voices = [e for e in result["elements"] if e["type"] == "dialogue" and e["character"] == "NARRATOR"]
    assert voices and all(v["extension"] == "V.O." for v in voices)
    assert {e["character"] for e in result["elements"] if e["type"] == "dialogue"} == {
        "NARRATOR",
        "MARA",
        "ROBOT",
        "OLD SAILOR",
    }
    assert sum(1 for e in result["elements"] if e["type"] == "transition") == 4
    assert [n["text"] for n in result["notes"]] == ["Check the weather in this scene."]


def test_a_note_on_its_own_line_does_not_split_the_block():
    parsed = parse("JOHN\nHello.\n[[check this]]\nMore.\n")
    assert [e["type"] for e in parsed["elements"]] == ["dialogue"]
    assert parsed["elements"][0]["text"] == "Hello. More."
    assert parsed["elements"][0]["notes"] == ["check this"]


def test_a_boneyard_on_its_own_line_does_not_split_the_block():
    parsed = parse("Rain falls.\n/* cut this */\nThunder.\n")
    assert [e["type"] for e in parsed["elements"]] == ["action"]
    assert parsed["elements"][0]["text"] == "Rain falls. Thunder."


def test_an_indented_note_line_does_not_split_the_block():
    parsed = parse("JOHN\nHello.\n   [[check this]]  \nMore.\n")
    assert [e["type"] for e in parsed["elements"]] == ["dialogue"]
    assert parsed["elements"][0]["text"] == "Hello. More."


def test_a_line_of_only_notes_and_boneyard_does_not_split_the_block():
    parsed = parse("JOHN\nHello.\n[[a]] [[b]]\nMore.\n/* x */ [[c]]\nEnd.\n")
    assert [e["type"] for e in parsed["elements"]] == ["dialogue"]
    assert parsed["elements"][0]["text"] == "Hello. More. End."
