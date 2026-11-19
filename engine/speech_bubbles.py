"""Brief public expressions, rendered for a single room and viewer."""
from time import monotonic
from engine import society

TURN_SECONDS = 3.5
WORDS = {
    'happy': ('Hello!', 'Hello there!'), 'excited': ('Oh, look!', 'Wonderful!'),
    'in_love': ('Love you.', 'Love you too.'), 'amusement': ('Ha!', 'Oh, you!'),
    'sleepy': ('So tired.', 'Rest well.'), 'serious': ('Listen.', 'I hear you.'),
    'irritated': ('Enough.', 'All right.'),
    'angry': ('Back off.', 'Enough!'), 'insulted': ('How rude!', 'That stung.'),
    'insulting': ('Some nerve!', 'Oh, please.'),
}


def mark(a, b, emotion, reply, lines=None):
    exchange = (monotonic(), a.location, a.id, b.id, emotion, reply)
    a._public_expression = b._public_expression = exchange
    a._town_words = b._town_words = (exchange, lines)


def valid_phrase(value):
    return isinstance(value, str) and len(value) <= 30 and 1 <= len(value.split()) <= 3 and value.isprintable()


def turn_seconds(text):
    """A complete utterance needs reading time; short greetings remain brisk."""
    return max(TURN_SECONDS, min(20, 1 + len(str(text or '').split()) / 3))


def durations(actor, record):
    marked, lines = getattr(actor, '_town_words', (None, None))
    if lines and marked == record:
        return turn_seconds(lines[1]), turn_seconds(lines[2])
    return TURN_SECONDS, TURN_SECONDS


def visible(w, viewer, occupants):
    now = monotonic()
    chosen = None
    for actor in occupants.values():
        record = getattr(actor, '_public_expression', None)
        if not record or actor.location != viewer.location:
            continue
        when, room, first, second, emotion, reply = record
        first_seconds, second_seconds = durations(actor, record)
        if (room != viewer.location or now - when >= first_seconds + (second_seconds if reply else 0)
                or first not in occupants or second not in occupants):
            continue
        if any(not occupants[i].alive or occupants[i].location != room for i in (first, second)):
            continue
        rank = (viewer.id in (first, second), when)
        if chosen is None or rank > chosen[0]:
            chosen = (rank, record)
    if chosen is None:
        return None, None
    _, (when, _, first, second, emotion, reply) = chosen
    first_seconds, _ = durations(occupants[first], chosen[1])
    answering = now - when >= first_seconds
    speaker = occupants[second if answering else first]
    feeling = reply if answering else emotion
    from engine.social import EMOTIONS
    # An emoji selected by a player never supplies words on their behalf.
    words = ''
    if not speaker.is_player:
        phrases = w.npcs.get(speaker.source_def, {}).get('gift_preferences', {}).get('speech_lines', {})
        phrase = phrases.get(feeling) if isinstance(phrases, dict) else None
        if not valid_phrase(phrase):
            phrase = WORDS[feeling][int(answering)]
        words = society.speech(phrase, society.friendliness(w, speaker, viewer))
    marked, lines = getattr(speaker, '_town_words', (None, None))
    bubble = {'symbol': EMOTIONS[feeling], 'words': words}
    if not speaker.is_player:
        from engine import npc_emotions
        other=occupants[first if answering else second]
        expression=npc_emotions.project(w,speaker,partner=other)
        bubble['emotions']=expression['emotions']
        bubble['emotion_summary']=expression['summary']
        bubble['symbol']=''.join(row['symbol'] for row in expression['emotions'][:3])
    if lines and marked == chosen[1] and not speaker.is_player:
        tone, first_line, answer = lines
        bubble['tone'] = 'says' if answering else tone
        bubble['words'] = society.speech(answer if answering else first_line, society.friendliness(w,speaker,viewer))
    return speaker.id, bubble
