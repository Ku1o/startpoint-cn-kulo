"""Read retained artwork from immutable active archives, without extracting it.

The index pins the original PNG bytes, including Deathbringer's pre-revision art.
An explicit --images directory supplies filenames directly and never falls back
to an archive when an input is missing. No loose artwork is written or cached.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import zipfile

REPO = Path(__file__).resolve().parents[2]
PNG_REAL = b'\x89PNG\r\n\x1a\n'
PNG_STORED = b'\x89png\r\n\x1a\n'

# These enabled, Git-tracked archives retain exact original artwork. Do not
# replace them with the newest effective resource: later artwork can differ.
ARCHIVES = {
    'pinball-1.4.102-1.4.103-1-lens0909-consolidated-cn.zip':
        '5167a391e4d2f659c1a523153f43fbe5e49a85a91081ddbcfc7f39c40e255d04',
    'pinball-1.4.103-1.4.104-1-abyss-lens0910-entry-message-consolidated.zip':
        'bfdc008bbd59056354466603bba49f63bf4c1663bd2ee84d2c5ddc7d3f139c43',
    'pinball-1.4.104-1.4.105-1-five-boss-ui-art.zip':
        '04f775c38a16c7e6646ea8c5df6bea93f5cd3f64ccc3653fd7f4b0fd32607959',
}


@dataclass(frozen=True)
class ArtworkSource:
    archive: str
    member: str
    png_sha256: str


_TICKET, _ITEMS, _UI = ARCHIVES
SOURCES = {
    'five-boss/20260910/新·深界连战凭证.png': ArtworkSource(
        _TICKET, 'production/upload/70/0e22050ee329943b09f0bbc92c636ec8b51849',
        '1a4fdb3bc7541a7e687f4add754cac66efd379166745d61758e5f4e513ad1db0'),
    'five-boss/20260910/新·深界结晶.png': ArtworkSource(
        _ITEMS, 'production/upload/5a/8557140d67bf8b9d06fe1ddff2343d05607e11',
        'd08e5a35e07b76c3d790379d729094f4783df6ef55b9cba47bf9d2890232c63b'),
    'five-boss/20260910/五王心核.png': ArtworkSource(
        _ITEMS, 'production/upload/e8/e94d472f8d41f8d2954a8d106bb0d18b47d0ac',
        '3fdb546388fc18b0cfdbb9f1157959a85ad0349127eba06ec6d17a381f778430'),
    'five-boss/20260910/死亡使者.png': ArtworkSource(
        _ITEMS, 'production/upload/f0/de168aad4299c068f3427535f469a49ff9cbbb',
        '23911ca588ceafd61330392dd8f352e575121607d356215596409cb3301bfec3'),
    'five-boss/ui-20260911/五重决战交换所横幅.png': ArtworkSource(
        _UI, 'production/upload/59/9a322b2b502b17e3ac626be2243e9631d8b630',
        '0f054029078114edcc574d409a4f6dc9ede9d39beff3052f7bdf679f83a352c7'),
    'five-boss/ui-20260911/五重关卡-讨伐页.png': ArtworkSource(
        _UI, 'production/upload/d9/014faaf3b6323850a22cc892a376427f6c42f5',
        'd93b308b548633fd931000716b71de81a7cf3f278a30e5609cd641fabf5adedb'),
    'five-boss/ui-20260911/五重关卡预览图.png': ArtworkSource(
        _UI, 'production/upload/e5/2bdb970ed33dad0a25f81768cb9b68971263d6',
        'e21e994f2b7c3a7be7b79e3d02add9229f152703f0916338c3270e1bf6e773f8'),
    'sponsor-special-thanks/degree_mod_special_thanks_wide.png': ArtworkSource(
        _ITEMS, 'production/upload/03/076857d74f07bb194f6185d4f1c1d6061850ce',
        '54c217185bb463354c8aed169746023ffa6a2b42a6fd022fc678435da66ed82a'),
}


def read_artwork(relative_key: str, *, images_dir: Path | None = None,
                 repo_root: Path = REPO) -> bytes:
    """Return a pinned original, or a filename from an explicit input directory.

    Keys are relative to assets/asset-patch/artwork. images_dir is the directory
    containing the selected PNG filenames, matching the makers' --images option.
    The retired narrow sponsor title intentionally has no supported key.
    """
    try:
        source = SOURCES[relative_key]
    except KeyError:
        raise ValueError(f'unsupported artwork key: {relative_key}') from None
    if images_dir is not None:
        path = Path(images_dir) / Path(relative_key).name
        if not path.is_file():
            raise FileNotFoundError(f'explicit artwork input is missing: {path}')
        raw = path.read_bytes()
        if raw[:8] != PNG_REAL:
            raise ValueError(f'explicit artwork input needs a standard PNG signature: {path}')
        return raw

    path = Path(repo_root) / 'assets/asset-patch/active' / source.archive
    archive = path.read_bytes()
    if hashlib.sha256(archive).hexdigest() != ARCHIVES[source.archive]:
        raise ValueError(f'artwork archive SHA-256 mismatch: {path}')
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        if bundle.namelist().count(source.member) != 1:
            raise ValueError(f'artwork member must occur exactly once: {source.member}')
        stored = bundle.read(source.member)
    if stored[:8] != PNG_STORED:
        raise ValueError(f'artwork member needs the stored lowercase png signature: {source.member}')
    raw = PNG_REAL + stored[8:]
    if hashlib.sha256(raw).hexdigest() != source.png_sha256:
        raise ValueError(f'original artwork PNG SHA-256 mismatch: {relative_key}')
    return raw
