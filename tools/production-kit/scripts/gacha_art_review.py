"""Hash-bound, page-specific maker review; never claims visual/device acceptance."""
from pathlib import Path
import copy

POLICY = 'official-art-v1'
COVER = ['title', 'nameplates', 'palette', 'footer', 'buttons', 'banner']
POSTER = ['name', 'epithet', 'limited-badge', 'palette', 'footer', 'buttons']


def core():
    import gacha_pipeline
    return gacha_pipeline


def requirements(spec):
    posters = {c['posterPage'] for c in spec['characters']}
    return {p['key']: (POSTER if p['key'] in posters else COVER)
            for p in spec['nativePages']}


def template(build_file, destination):
    p = core()
    path, build = p.verify_build(build_file)
    target = Path(destination).resolve()
    if target.exists():
        raise ValueError('Refusing to replace an art review draft')
    spec = p.read(build['resolvedInput']['file'])
    if any(p.inside(target, Path(root).resolve()) for root in spec.get('protectedRoots', [])) or p.inside(target, p.HERE) or p.inside(target, Path(spec['toolchain']['supportRoot'])):
        raise ValueError('Art review destination is protected')
    result = {'schemaVersion': 1, 'policy': POLICY, 'build': p.binding(path),
              'finalPreview': build['review'], 'resourceManifest': build['resourceManifest'],
              'officialReferences': [], 'pages': [
                  {'page': key, 'checks': {name: {'decision': 'pending', 'observations': ''} for name in checks},
                   'evidence': []} for key, checks in requirements(spec).items()],
              'scope': 'Maker visual review only; not user adoption, business configuration or device acceptance.'}
    p.write(target, result)
    return {'status': 'art_review_draft', 'review': str(target), 'pages': len(result['pages'])}


def validate_review(path, build, review):
    p = core()
    if review.get('schemaVersion') != 1 or review.get('policy') != POLICY:
        raise ValueError('Unsupported art review policy')
    for key, expected in [('build', p.binding(path)), ('finalPreview', build['review']), ('resourceManifest', build['resourceManifest'])]:
        if review.get(key) != expected:
            raise ValueError('Art review no longer matches final ' + key)
        p.input_bindings(review[key])
    references = review.get('officialReferences')
    if not isinstance(references, list) or not references:
        raise ValueError('Bind actual official references for visual comparison')
    p.input_bindings(references)
    if any(not isinstance(r, dict) or not {'file', 'sha256', 'bytes'} <= r.keys() for r in references):
        raise ValueError('Official references need exact file/hash/size bindings')
    spec = p.read(build['resolvedInput']['file'])
    wanted = requirements(spec)
    pages = review.get('pages', [])
    if len(pages) != len(wanted) or {page.get('page') for page in pages} != set(wanted):
        raise ValueError('Art review must cover every cover and character page once')
    from PIL import Image
    for page in pages:
        checks = page.get('checks', {})
        if set(checks) != set(wanted[page['page']]):
            raise ValueError('Missing or unexpected art checks for ' + page['page'])
        for name, row in checks.items():
            if row.get('decision') != 'pass' or not str(row.get('observations', '')).strip():
                raise ValueError('Unresolved visual check: ' + page['page'] + '/' + name)
        evidence = page.get('evidence', [])
        if {e.get('phase') for e in evidence} != {'transition', 'settled'}:
            raise ValueError('Review actual transition and settled full-UI frames')
        for e in evidence:
            if e.get('view') != 'full-ui' or type(e.get('frame')) is not int or e['frame'] < 0 or type(e.get('displayWidth')) is not int or e['displayWidth'] <= 0:
                raise ValueError('Evidence needs actual frame, display size and full-UI view')
            image = e.get('image', {})
            if not {'file', 'sha256', 'bytes'} <= image.keys():
                raise ValueError('Evidence image must bind exact bytes')
            p.input_bindings(image)
            with Image.open(image['file']) as im:
                if not 0 < im.width <= 4096 or not 0 < im.height <= 8192:
                    raise ValueError('Review image exceeds bounded inspection dimensions')
    return True


def record(build_file, review_file):
    p = core()
    path, build = p.verify_build(build_file)
    source = Path(review_file).resolve()
    review = p.read(source)
    validate_review(path, build, review)
    record = copy.deepcopy(review)
    record.update(status='maker_art_reviewed', userAccepted=False, deviceVerified=False,
                  automaticAestheticJudgment=False, sourceReview=p.binding(source))
    archive = path.parent / 'art-reviews' / (p.digest(source) + '.json')
    if archive.exists():
        if p.read(archive) != record:
            raise ValueError('Art review archive differs; do not overwrite it')
    else:
        p.write(archive, record)
    p.write(path.parent / 'ART-REVIEW.json', record)
    return {'status': 'maker_art_reviewed', 'review': str(archive), 'userAccepted': False, 'deviceVerified': False}


def require_for_accept(path, build):
    p = core()
    spec = p.read(build['resolvedInput']['file'])
    if spec.get('artReviewPolicy') != POLICY:
        return  # Archived projects retain their original verification contract.
    receipt = path.parent / 'ART-REVIEW.json'
    if not receipt.is_file():
        raise ValueError('Run review-art on the final preview before recording adoption')
    review = p.read(receipt)
    p.input_bindings(review.get('sourceReview', {}))
    validate_review(path, build, review)
