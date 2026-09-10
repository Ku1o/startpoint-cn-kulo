import io
import unittest
import zipfile

import publish_sponsor_special_thanks as sponsor


class SponsorAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = sponsor.ROOT
        with zipfile.ZipFile(root / "assets/asset-patch/active/pinball-1.4.99-1.4.100-2-rank-title-conditions.zip") as z:
            cls.before = z.read(sponsor.p.member(("common", sponsor.p.hrel(sponsor.DEGREE_LOGICAL))))
        cls.formal = (root / sponsor.ART_REL).read_bytes()

    def test_addition_preserves_every_existing_compressed_row(self):
        before = sponsor.p.rawmap(self.before)
        after = sponsor.p.rawmap(sponsor.build_degree(self.before))
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual({key: after[key] for key in before}, before)

    def test_duplicate_id_is_rejected_instead_of_overwritten(self):
        with self.assertRaisesRegex(ValueError, "ID already exists"):
            sponsor.build_degree(sponsor.build_degree(self.before))

    def test_plain_png_is_not_accepted_as_cdn_storage(self):
        with self.assertRaises(ValueError):
            sponsor.verify_stored_png(self.formal, self.formal)
        sponsor.verify_stored_png(sponsor.wf_assets.png_encode(self.formal), self.formal)

    def test_readback_rejects_an_archive_with_unencoded_image(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr(sponsor.p.member(("common", sponsor.p.hrel(sponsor.DEGREE_LOGICAL))),
                       sponsor.build_degree(self.before))
            z.writestr(sponsor.p.member(("common", sponsor.p.hrel(sponsor.IMAGE_LOGICAL))), self.formal)
        with self.assertRaises(ValueError):
            sponsor.verify_archive(buffer.getvalue(), self.before, self.formal)


if __name__ == "__main__":
    unittest.main()
