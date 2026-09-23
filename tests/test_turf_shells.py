"""Shell grass: blades at field level, and why the patch is not a rectangle.

The flat turf carries blades in a 1024 px tile, and measured against the
rendered frame it loses about 94% of that detail by the time it reaches the
eye at the field-level seat. Only part of that is the grazing sheen, which is
deliberate; the rest is that a tiled texture seen at a 16 degree graze is
sampled along its depth axis over many texels, and no amount of extra texture
detail survives it. So the blades are geometry - six alpha-tested shell layers
over the near field - and not a finer tile.

Shells were built once before and shipped disabled because "from the
field-level seat the 24x10 yd patch still reads as a darker rectangle". The
cause is here in a form a test can hold: the turf around the patch is lifted
toward `SheenColor` as the view flattens, and the shells drew their blades
from the raw albedo with no such lift, so the patch read as a hole. Both
surfaces now take the same sheen, so they agree at every angle by
construction rather than by a tint tuned at one distance.
"""

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text())
FIELD = TOKENS["visual"]["field"]
SHELLS = FIELD["shells"]
MATS = TOKENS["shaderGraph"]["materials"]
USDA = ROOT / "tools/blender/field/shadergraph/Shells.rkassets/FieldShells.usda"


class TheShellsAndTheTurfAgreeOnTheSheen(unittest.TestCase):
    """The darker-rectangle bug, pinned. Either surface may change its sheen;
    they may not change it apart."""

    def test_both_surfaces_take_the_same_sheen_colour_and_power(self):
        turf = MATS["turfSheen"]["parameters"]
        shell = MATS[SHELLS["material"]]["parameters"]
        self.assertEqual(turf["SheenColor"], shell["SheenColor"])
        self.assertEqual(turf["SheenPower"], shell["SheenPower"])

    def test_the_shells_sheen_sits_within_the_turfs_per_stripe_pair(self):
        """The turf sheens per stripe and the shells cannot, so one value has
        to stand for both. It must at least lie between them."""
        lo, hi = sorted(FIELD["turf"]["stripeSheen"])
        self.assertGreaterEqual(MATS[SHELLS["material"]]["parameters"]["Sheen"], lo)
        self.assertLessEqual(MATS[SHELLS["material"]]["parameters"]["Sheen"], hi)

    def test_the_shell_graph_actually_applies_its_sheen(self):
        """A parameter the tokens set and the graph ignores is the same bug
        with a passing test, so read the graph: the surface's base colour has
        to come through the sheen mix, not straight off the blades."""
        src = USDA.read_text()
        surface = re.search(r'def Shader "Surface"\s*\{(.*?)\n        \}', src, re.S)
        self.assertIsNotNone(surface)
        self.assertIn("Sheened.outputs:out", surface.group(1))
        sheened = re.search(r'def Shader "Sheened"\s*\{(.*?)\n        \}', src, re.S)
        self.assertIsNotNone(sheened)
        self.assertIn("inputs:SheenColor", sheened.group(1))
        self.assertIn("SheenAmount.outputs:out", sheened.group(1))


class TheBladesAreThereToBeSeen(unittest.TestCase):

    def test_the_shells_are_enabled(self):
        """They shipped disabled for two rounds. The bar - 'up close at field
        level, the grass has blades' - is not met with them off."""
        self.assertTrue(SHELLS["enabled"])

    def test_the_patch_reaches_past_the_view_from_the_field_seat(self):
        """A patch narrower than the view ends inside the frame, and a patch
        of grass that stops in a straight line is worse than no patch at all -
        that is the rectangle this round exists to remove. The field seat sits
        4.5 yd outside the near sideline, so at the patch's far edge the eye is
        depth + 4.5 yd away, and a 90 degree view spans that either side of
        centre. Both edges have to be at least that far out."""
        seen_half = SHELLS["depth"] + 4.5           # 90 deg: half-width == distance
        self.assertGreaterEqual(50 - SHELLS["fromX"], seen_half,
                                "the patch's near-side edge ends inside the frame")
        self.assertGreaterEqual(SHELLS["toX"] - 50, seen_half,
                                "the patch's far-side edge ends inside the frame")

    def test_the_far_edge_dissolves_rather_than_ending(self):
        """A hard far edge would read as a line across the field. The fade has
        to be a real fraction of the patch, not a token gesture."""
        self.assertGreaterEqual(SHELLS["fade"], SHELLS["depth"] / 4)

    def test_the_fade_cannot_eat_the_whole_patch(self):
        """It did. The shader fades in from PatchZ0 over `fade` and out to
        PatchZ1 over `fade`, so with both ends faded only depth - 2 x fade
        survives at full strength - four yards out of twelve, in the middle of
        the patch, which measured as the only band of the field-level frame
        that changed at all. The near edge is not faded now (`FieldActor`
        pushes PatchZ1 past the sideline), so only one fade is spent; this
        holds even if someone puts it back."""
        self.assertGreater(SHELLS["depth"] - 2 * SHELLS["fade"], 0,
                           "both fades together would leave no full-strength grass")

    def test_the_sideline_end_of_the_patch_is_not_faded(self):
        """`FieldActor` sets PatchZ1 to half + fade rather than half. The fade
        hides an edge that would read as a line drawn across the grass; the
        sideline is not such an edge - the grass really does stop there and the
        border takes over - and fading it removed the blades exactly where the
        wearer is closest to them."""
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Field/FieldActor.swift").read_text()
        self.assertRegex(src, r'"PatchZ1",\s*half \+ Sh\.fade')

    def test_the_layers_stay_inside_the_baked_atlas(self):
        self.assertTrue(0 <= SHELLS["firstLayer"] <= SHELLS["lastLayer"] <= 7)


if __name__ == "__main__":
    unittest.main()
