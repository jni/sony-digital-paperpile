import os
import shutil
import sys

from tinydb import TinyDB, Query


PAPERPILE = os.path.expanduser('~/Google Drive/Paperpile/All Papers')
SONY_BOX = os.path.expanduser('~/Box Sync/Paperpile')

forbidden_chars = '"<> ,;:|*?'


def to_sony_filename(fn : str) -> str:
    """Remove tricky characters from Paperpile filenames.

    The Sony Digital Paper user guide warns that filenames containing
    these characters may not sync correctly. (The space character is
    added just in case.)

    Parameters
    ----------
    fn : string
        The input filename, from the Paperpile Google Drive folder.

    Returns
    -------
    sanitised : string
        The sanitised filename.

    Examples
    --------
    >>> fn = 'A paper by Jones; and Smith: Are angle brackets <> needed?.pdf'
    >>> to_sony_filename(fn)
    'A_paper_by_Jones__and_Smith__Are_angle_brackets____needed_.pdf'
    """
    sanitised = fn
    for char in forbidden_chars:
        sanitised = sanitised.replace(char, '_')
    return sanitised


def rscandir(directory):
    """Recursively scan subdirectories and yield simple files."""
    for entry in os.scandir(directory):
        if entry.is_dir():
            yield from rscandir(entry.path)
        elif not entry.name.startswith('.'):
            yield entry


def init_paperpile_to_dpt(paperpile_path : str = None,
                          sony_path : str = None,
                          dry_run : bool = True,
                          verbose : bool = True):
    """Make the initial copy from Paperpile to the Box directory.

    This creates a tinyDB database that will store modification times
    for documents, enabling later sync.
    """
    home = os.path.expanduser('~/')
    truncate = len(home)
    if paperpile_path is None and sony_path is None:
        paperpile_path = PAPERPILE
        sony_path = SONY_BOX
    os.chdir(home)
    db = TinyDB('.sdpp-sync.json')
    for entry in rscandir(paperpile_path):
        original_name = entry.name
        original_path = entry.path
        original_path = original_path[truncate:]
        new_path = os.path.join(sony_path, to_sony_filename(original_name))
        new_path = new_path[truncate:]
        if verbose or dry_run:
            print('copying %s to %s' % (original_path, new_path))
        if not dry_run:
            shutil.copy2(original_path, new_path)
            db.insert({'paperpile': original_path, 'box': new_path,
                       'modtime': entry.stat().st_mtime})


def sync_existing(dry_run=True, verbose=True):
    """Manually sync files by comparing modification time with last known.
    """
    home = os.path.expanduser('~/')
    truncate = len(home)
    os.chdir(home)
    db = TinyDB('.sdpp-sync.json')
    for elem in db.all():
        sony, paperpile, modtime = [elem[k]
                                    for k in ['box', 'paperpile', 'modtime']]
        smod = os.stat(sony).st_mtime
        pmod = os.stat(paperpile).st_mtime
        if smod > modtime + 10:  # 10 second resolution
            if pmod > modtime + 10:
                print('both %s and %s changed; resolve manually.' %
                      (sony, paperpile))
            else:
                if dry_run or verbose:
                    print('copying updated %s to %s' % (sony, paperpile))
                if not dry_run:
                    elem['modtime'] = smod
                    shutil.copy2(sony, paperpile)
        elif pmod > modtime + 10:
            if dry_run or verbose:
                print('copying update %s to %s' % (paperpile, sony))
            if not dry_run:
                elem['modtime'] = pmod
                shutil.copy2(paperpile, sony)


def main():
    import argparse
    p = argparse.ArgumentParser(description='sync paperpile and box')
    p.add_argument('--init', action='store_true',
                   help='Run initial sync')
    p.add_argument('--do', action='store_true',
                   help='Actually sync, not just dry run.')
    p.add_argument('--syncx', action='store_true',
                   help='Manually sync existing files.')

    args = p.parse_args()

    if args.init:
        init_paperpile_to_dpt(dry_run=(not args.do))
    elif args.syncx:
        sync_existing(dry_run=(not args.do))


if __name__ == '__main__':
    main()
