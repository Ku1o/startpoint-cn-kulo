import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gacha_pipeline as p
import gacha_art_review as art


class ArtReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'BUILD.json'
        spec = {'artReviewPolicy': art.POLICY, 'nativePages': [{'key': 'cover'}, {'key': 'poster'}],
                'characters': [{'id': 12, 'posterPage': 'poster'}]}
        p.write(self.root / 'project.json', spec)
        p.write(self.root / 'resources.json', [])
        (self.root / 'review.html').write_text('<html>final</html>', encoding='utf8')
        self.build = {'review': p.binding(self.root / 'review.html'),
                      'resourceManifest': p.binding(self.root / 'resources.json'),
                      'resolvedInput': p.binding(self.root / 'project.json')}
        p.write(self.path, self.build)
        image = self.root / 'ui.png'
        Image.new('RGB', (180, 320), 'white').save(image)
        self.review = {'schemaVersion': 1, 'policy': art.POLICY, 'build': p.binding(self.path),
                       'finalPreview': self.build['review'], 'resourceManifest': self.build['resourceManifest'],
                       'officialReferences': [p.binding(image)], 'pages': []}
        for key, checks in art.requirements(spec).items():
            self.review['pages'].append({'page': key,
                'checks': {k: {'decision': 'pass', 'observations': 'Fixture contract only'} for k in checks},
                'evidence': [{'phase': phase, 'view': 'full-ui', 'frame': n, 'displayWidth': 360,
                             'image': p.binding(image)} for n, phase in enumerate(['transition', 'settled'])]})

    def check(self, review=None):
        return art.validate_review(self.path, self.build, review or self.review)

    def test_complete_contract(self):
        self.assertTrue(self.check())

    def test_independent_limited_plaque_required(self):
        del self.review['pages'][1]['checks']['limited-badge']
        with self.assertRaisesRegex(ValueError, 'Missing'): self.check()

    def test_cover_nameplates_are_separate(self):
        del self.review['pages'][0]['checks']['nameplates']
        with self.assertRaisesRegex(ValueError, 'Missing'): self.check()

    def test_not_all_pages_reviewed(self):
        self.review['pages'].pop()
        with self.assertRaisesRegex(ValueError, 'every'): self.check()

    def test_pending_art_does_not_pass(self):
        self.review['pages'][1]['checks']['name']['decision'] = 'pending'
        with self.assertRaisesRegex(ValueError, 'Unresolved'): self.check()

    def test_transition_evidence_required(self):
        self.review['pages'][0]['evidence'].pop(0)
        with self.assertRaisesRegex(ValueError, 'transition'): self.check()

    def test_modified_image_rejected(self):
        (self.root / 'ui.png').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.check()

    def test_stale_final_preview_rejected(self):
        self.review['finalPreview']['sha256'] = 'a' * 64
        with self.assertRaises(ValueError): self.check()

    def test_adoption_needs_review_and_archives_are_retained(self):
        with self.assertRaisesRegex(ValueError, 'review-art'): art.require_for_accept(self.path, self.build)
        source = self.root / 'decision.json'
        p.write(source, self.review)
        with patch.object(p, 'verify_build', return_value=(self.path, self.build)):
            one = art.record(self.path, source)
            self.review['pages'][0]['checks']['title']['observations'] = 'Rechecked fixture'
            p.write(source, self.review)
            two = art.record(self.path, source)
        self.assertNotEqual(one['review'], two['review'])
        self.assertTrue(Path(one['review']).is_file())
        art.require_for_accept(self.path, self.build)

    def test_legacy_contract_not_retroactively_promoted(self):
        p.write(self.root / 'project.json', {})
        art.require_for_accept(self.path, self.build)


if __name__ == '__main__':
    unittest.main()
