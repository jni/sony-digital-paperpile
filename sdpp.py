import os
import shutil
import sys
import time

from tinydb import TinyDB, Query
from watchdog import events, observers


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
        new_paperpile_to_box(paperpile_path, db,
                             dry_run=dry_run, verbose=verbose)


def new_paperpile_to_box(path_to_file_in_paperpile, db, *,
                         dry_run=True, verbose=True):
    """Copy a new Paperpile file to Box, and add to database.
    """
    home = os.path.expanduser('~/')
    truncate = len(home)
    os.chdir(home)
    original_path = path_to_file_in_paperpile
    original_name = os.path.basename(original_path)
    if original_path.startswith(home):
        original_path = original_path[truncate:]
    new_path = os.path.join(SONY_BOX, to_sony_filename(original_name))
    if new_path.startswith(home):
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
        modified_action(elem, sony, paperpile, modtime,
                        dry_run=dry_run, verbose=verbose)


def modified_action(elem, sony, paperpile, modtime, *,
                    dry_run=True, verbose=True):
    """Perform appropriate action when a file has been modified.

    Parameters
    ----------
    elem : db element (dictionary)
    sony, paperpile : string
        The paths to the Sony Box file and corresponding Paperpile file.
    modtime : number
        The last known modification time (seconds from Epoch) of the file.
    """
    smod = os.stat(sony).st_mtime
    pmod = os.stat(paperpile).st_mtime
    print('current: %i, sony: %i, paperpile: %i' % (modtime, smod, pmod))
    if smod > modtime + 10:  # 10 second resolution
        print('sony newer')
        if pmod > modtime + 10:
            print('both %s and %s changed; favoring Sony.' %
                  (sony, paperpile))
        if dry_run or verbose:
            print('copying updated %s to %s' % (sony, paperpile))
        if not dry_run:
            elem['modtime'] = smod
            shutil.copy2(sony, paperpile)
    elif pmod > modtime + 10:
        print('paperpile newer')
        if dry_run or verbose:
            print('copying update %s to %s' % (paperpile, sony))
        if not dry_run:
            elem['modtime'] = pmod
            shutil.copy2(paperpile, sony)


class FileModifiedHandler(events.FileSystemEventHandler):
    def __init__(self, *args, **kwargs):
        self.dry_run = kwargs.pop('dry_run', True)
        self.verbose = kwargs.pop('verbose', True)
        super().__init__(*args, **kwargs)
        os.chdir(os.path.expanduser('~'))
        self.db = TinyDB('.sdpp-sync.json')

    def on_modified(self, event):
        home = os.path.expanduser('~/')
        path = event.src_path
        if path.startswith(home):
            path = path[len(home):]
        q = Query()
        result = (self.db.search(q.box == path) +
                  self.db.search(q.paperpile == path))
        print(result)
        if len(result) != 0:
            result = result[0]
            modified_action(result, result['box'], result['paperpile'],
                            result['modtime'], dry_run=self.dry_run,
                            verbose=self.verbose)


class NewFileHandler(events.FileSystemEventHandler):
    def __init__(self, *args, **kwargs):
        self.dry_run = kwargs.pop('dry_run', True)
        self.verbose = kwargs.pop('verbose', True)
        super().__init__(*args, **kwargs)
        os.chdir(os.path.expanduser('~'))
        self.db = TinyDB('.sdpp-sync.json')

    def on_created(self, event):
        home = os.path.expanduser('~/')
        path = event.src_path
        if path.startswith(home):
            path = path[len(home):]
        if path.endswith('.pdf') or path.endswith('.PDF'):
            new_paperpile_to_box(event.src_path, self.db,
                                 dry_run=self.dry_run, verbose=self.verbose)


class MovedFileHandler(events.FileSystemEventHandler):
    def __init__(self, *args, **kwargs):
        self.dry_run = kwargs.pop('dry_run', True)
        self.verbose = kwargs.pop('verbose', True)
        super().__init__(*args, **kwargs)
        os.chdir(os.path.expanduser('~'))
        self.db = TinyDB('.sdpp-sync.json')

    def on_moved(self, event):
        path = event.src_path
        if not path.endswith('.pdf') or path.endswith('.PDF'):
            return
        home = os.path.expanduser('~/')
        dest = event.dest_path
        if path.startswith(home):
            path = path[len(home):]
        if dest.startswith(home):
            dest = dest[len(home):]
        box_old = to_sony_filename(path)
        box_new = to_sony_filename(dest)
        os.rename(box_old, box_new)
        q = Query()
        elem = self.db.search(q.box == box_old)
        elem['box'] = box_new
        elem['modtime'] = os.stat(box_new).st_mtime
        elem['paperpile'] = dest


def watch(dry_run=True, verbose=True):
    """Watch both directories for changes and copy when detected.
    """
    os.chdir(os.path.expanduser('~'))
    obs = observers.Observer()
    mod = FileModifiedHandler(dry_run=dry_run, verbose=verbose)
    new = NewFileHandler(dry_run=dry_run, verbose=verbose)
    mov = MovedFileHandler(dry_run=dry_run, verbose=verbose)
    obs.schedule(mod, SONY_BOX, recursive=True)
    obs.schedule(new, PAPERPILE, recursive=True)
    obs.schedule(mov, PAPERPILE, recursive=True)
    obs.start()
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()


def main():
    import argparse
    p = argparse.ArgumentParser(description='sync paperpile and box')
    p.add_argument('--init', action='store_true',
                   help='Run initial sync')
    p.add_argument('--do', action='store_true',
                   help='Actually sync, not just dry run.')
    p.add_argument('--syncx', action='store_true',
                   help='Manually sync existing files.')
    p.add_argument('--watch', action='store_true',
                   help='Watch the relevant directories and sync when needed.')

    args = p.parse_args()

    if args.init:
        init_paperpile_to_dpt(dry_run=(not args.do))
    elif args.syncx:
        sync_existing(dry_run=(not args.do))
    elif args.watch:
        watch(dry_run=(not args.do))


if __name__ == '__main__':
    main()
