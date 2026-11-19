"""Complete NPC turns reach the bubble, with enough time for full sentences."""
from unittest.mock import patch
import unittest

from engine import speech_bubbles
from tests.test_npc_emotions import fixture


class SpeechCompletenessTests(unittest.TestCase):
    def test_complete_route_advice_is_not_cut_at_the_old_three_line_boundary(self):
        world,speaker,_,listener,viewer=fixture()
        words='If you are heading to Open meadow, start east from here. I can describe the route I know if you need more directions.'
        answer='Thank you. I would rather ask someone who knows the road than guess.'
        with patch.object(speech_bubbles,'monotonic',return_value=100):
            speech_bubbles.mark(speaker,listener,'happy','happy',('says',words,answer))
        occupants={person.id:person for person in world.entities_in_room('square')}
        with patch.object(speech_bubbles,'monotonic',return_value=104):
            ident,bubble=speech_bubbles.visible(world,viewer,occupants)
        self.assertEqual(ident,speaker.id)
        self.assertEqual(bubble['words'],words)
        self.assertTrue(bubble['words'].endswith('more directions.'))
        with patch.object(speech_bubbles,'monotonic',return_value=100+speech_bubbles.turn_seconds(words)+.1):
            ident,bubble=speech_bubbles.visible(world,viewer,occupants)
        self.assertEqual(ident,listener.id)
        self.assertEqual(bubble['words'],answer)

    def test_short_greeting_timing_and_room_visibility_are_preserved(self):
        world,speaker,_,listener,viewer=fixture()
        with patch.object(speech_bubbles,'monotonic',return_value=100):
            speech_bubbles.mark(speaker,listener,'happy','happy',('says','Hello!','Hello there!'))
        occupants={person.id:person for person in world.entities_in_room('square')}
        with patch.object(speech_bubbles,'monotonic',return_value=103.6):
            self.assertEqual(speech_bubbles.visible(world,viewer,occupants)[0],listener.id)
        listener.location='lane'
        with patch.object(speech_bubbles,'monotonic',return_value=104):
            self.assertEqual(speech_bubbles.visible(world,viewer,occupants),(None,None))


if __name__=='__main__':unittest.main()
