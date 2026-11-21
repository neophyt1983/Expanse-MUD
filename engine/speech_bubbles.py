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


def end(world, participant):
    """A room change ends the live exchange, even if someone quickly returns."""
    exchange = getattr(participant, '_public_expression', None)
    if exchange is None:
        return
    for ident in exchange[2:4]:
        actor = world.entities.get(ident)
        if actor is not None and getattr(actor, '_public_expression', None) is exchange:
            del actor._public_expression
            if getattr(actor, '_town_words', (None, None))[0] is exchange:
                del actor._town_words


def valid_phrase(value):
    return isinstance(value, str) and len(value) <= 30 and 1 <= len(value.split()) <= 3 and value.isprintable()


def visible(w, viewer, occupants):
    now = monotonic()
    chosen = None
    for actor in occupants.values():
        record = getattr(actor, '_public_expression', None)
        if not record or actor.location != viewer.location:
            continue
        when, room, first, second, emotion, reply = record
        if (room != viewer.location or now - when >= TURN_SECONDS * (2 if reply else 1)
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
    answering = now - when >= TURN_SECONDS
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
    if lines and marked == chosen[1] and not speaker.is_player:
        tone, first_line, answer = lines
        bubble['tone'] = 'says' if answering else tone
        bubble['words'] = society.speech(answer if answering else first_line, society.friendliness(w,speaker,viewer))
    return speaker.id, bubble
