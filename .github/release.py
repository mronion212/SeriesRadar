"""Check the release version and extract its changelog entry for GitHub Actions."""
import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def parse_version(value):
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',value):
        raise ValueError('Gebruik een versie als 0.1.0, zonder v of voorloopnullen.')
    return tuple(map(int,value.split('.')))


def check_sequence(current, previous=None):
    current=parse_version(current)
    if previous is None:
        if current!=(0,1,0):raise ValueError('De eerste release begint bij 0.1.0.')
        return
    major,minor,patch=parse_version(previous)
    if current not in ((major,minor,patch+1),(major,minor+1,0),(major+1,0,0)):
        raise ValueError('Verhoog patch met één, of begin de eerstvolgende minor/major op nul.')


def release_notes(changelog, version):
    pattern=r'^## \['+re.escape(version)+r'\] - \d{4}-\d{2}-\d{2}\s*\n(.*?)(?=^## |\Z)'
    entry=re.search(pattern,changelog,re.M|re.S)
    if not entry or not entry[1].strip():raise ValueError('Voeg wijzigingsnotities voor '+version+' toe aan CHANGELOG.md.')
    return entry[1].strip()+'\n'


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--notes-file',type=Path)
    args=parser.parse_args()
    version=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
    parse_version(version)
    tags=[tag for tag in git('tag','--list').splitlines() if re.fullmatch(r'v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)',tag)]
    own='v'+version
    if own in tags:
        if git('rev-list','-n','1',own)!=git('rev-parse','HEAD'):
            raise ValueError('Deze versie is al gebruikt. Verhoog VERSION en voeg wijzigingsnotities toe.')
        tags.remove(own)  # A retry of the same successful commit is safe.
    latest=max(tags,key=lambda tag:parse_version(tag[1:]))[1:] if tags else None
    check_sequence(version,latest)
    notes=release_notes((ROOT/'CHANGELOG.md').read_text(encoding='utf-8'),version)
    if args.notes_file:args.notes_file.write_text(notes,encoding='utf-8')
    print('Release v'+version+' gecontroleerd.')


if __name__=='__main__':main()
