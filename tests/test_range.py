import unittest
from poker.range import parse_range, filter_blocked, RangeError, expand_hand_token


class TestExpandHandToken(unittest.TestCase):
    def test_pair_aa(self):
        combos = expand_hand_token("AA")
        self.assertEqual(len(combos), 6)
        for c1, c2 in combos:
            self.assertEqual(c1[0], "A")
            self.assertEqual(c2[0], "A")
            self.assertNotEqual(c1[1], c2[1])

    def test_pair_kk(self):
        self.assertEqual(len(expand_hand_token("KK")), 6)

    def test_suited_aks(self):
        combos = expand_hand_token("AKs")
        self.assertEqual(len(combos), 4)
        for c1, c2 in combos:
            self.assertEqual(c1[0], "A")
            self.assertEqual(c2[0], "K")
            self.assertEqual(c1[1], c2[1])

    def test_offsuit_ako(self):
        combos = expand_hand_token("AKo")
        self.assertEqual(len(combos), 12)
        for c1, c2 in combos:
            self.assertNotEqual(c1[1], c2[1])

    def test_unspecified_ak(self):
        combos = expand_hand_token("AK")
        self.assertEqual(len(combos), 16)

    def test_invalid_rank(self):
        with self.assertRaises(RangeError):
            expand_hand_token("ZZ")

    def test_pair_with_suit_raises(self):
        with self.assertRaises(RangeError):
            expand_hand_token("AAs")


class TestParseRange(unittest.TestCase):
    def test_single_pair(self):
        self.assertEqual(len(parse_range("AA")), 6)

    def test_pair_plus(self):
        # QQ+ = QQ, KK, AA = 18 combos
        combos = parse_range("QQ+")
        self.assertEqual(len(combos), 18)

    def test_pair_range(self):
        # QQ-TT = TT, JJ, QQ = 18 combos
        combos = parse_range("QQ-TT")
        self.assertEqual(len(combos), 18)

    def test_pair_range_99_qq(self):
        # 99-QQ = 99,TT,JJ,QQ = 24 combos
        combos = parse_range("99-QQ")
        self.assertEqual(len(combos), 24)

    def test_suited_plus(self):
        # ATs+ = ATs,AJs,AQs,AKs = 16 combos
        combos = parse_range("ATs+")
        self.assertEqual(len(combos), 16)

    def test_suited_range(self):
        # AQs-ATs = ATs,AJs,AQs = 12 combos
        combos = parse_range("AQs-ATs")
        self.assertEqual(len(combos), 12)

    def test_offsuit_plus(self):
        # AQo+ = AQo,AKo = 24 combos
        combos = parse_range("AQo+")
        self.assertEqual(len(combos), 24)

    def test_unspecified_both_suits(self):
        # AK = 16 combos
        self.assertEqual(len(parse_range("AK")), 16)

    def test_comma_separated(self):
        combos = parse_range("AA,KK")
        self.assertEqual(len(combos), 12)

    def test_deduplication(self):
        # AKs + AKo = AK = 16 unique combos
        combos = parse_range("AKs,AKo")
        self.assertEqual(len(combos), 16)

    def test_deduplication_repeated(self):
        # AK,AK should still be 16
        combos = parse_range("AK,AK")
        self.assertEqual(len(combos), 16)

    def test_empty_raises(self):
        with self.assertRaises(RangeError):
            parse_range("")

    def test_invalid_token_raises(self):
        with self.assertRaises(RangeError):
            parse_range("ZZ")

    def test_whitespace_ignored(self):
        combos = parse_range("AA, KK, QQ")
        self.assertEqual(len(combos), 18)

    def test_jj_plus(self):
        # JJ+ = JJ,QQ,KK,AA = 24 combos
        combos = parse_range("JJ+")
        self.assertEqual(len(combos), 24)


class TestFilterBlocked(unittest.TestCase):
    def test_removes_blocked(self):
        combos = [("Ah", "Kd"), ("Qs", "Qh"), ("As", "Ad")]
        result = filter_blocked(combos, {"Ah"})
        self.assertNotIn(("Ah", "Kd"), result)
        self.assertIn(("Qs", "Qh"), result)

    def test_removes_both_cards(self):
        combos = [("Ah", "Kd"), ("Ks", "Kh")]
        result = filter_blocked(combos, {"Ah", "Kd"})
        self.assertEqual(result, [("Ks", "Kh")])

    def test_empty_blocked_set(self):
        combos = [("Ah", "Kd"), ("Qs", "Qh")]
        self.assertEqual(filter_blocked(combos, set()), combos)

    def test_all_blocked(self):
        combos = [("Ah", "Kd")]
        self.assertEqual(filter_blocked(combos, {"Ah", "Kd"}), [])


if __name__ == "__main__":
    unittest.main()
