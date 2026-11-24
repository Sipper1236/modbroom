"""Headless scan for scripting: python -m modbroom --cli-scan [--json|--html OUT] [path]"""
import argparse
import json
import sys

from . import scanner, game_rules, store


def main(argv=None):
    ap = argparse.ArgumentParser(prog='modbroom --cli-scan')
    ap.add_argument('path', nargs='?', help='Mods folder (defaults to the configured one)')
    ap.add_argument('--json', action='store_true', help='Emit raw JSON')
    ap.add_argument('--html', metavar='OUT', help='Write a standalone HTML report to OUT')
    ap.add_argument('--csv', metavar='OUT', help='Write a CSV file list to OUT')
    ap.add_argument('--manifest', metavar='OUT', help='Write a JSON manifest to OUT')
    args = ap.parse_args(argv)

    st = store.load_state()
    mods = args.path or st['settings'].get('mods_path')
    if not mods:
        print('No Mods folder configured; pass one as an argument.', file=sys.stderr)
        return 2
    scan = scanner.scan_tree(mods, st['settings'].get('saves_path'), st['settings'].get('tray_path'))
    findings = scanner.analyze(scan, mods_path=scan.get('mods_path'))
    rules = game_rules.analyze(scan)
    stats = findings['stats']

    if args.json:
        print(json.dumps({'stats': stats, 'findings': findings, 'game_rules': rules}, default=str, indent=2))
    else:
        print('Scanned %d files in %s' % (stats['total_files'], mods))
        print('  packages=%d scripts=%d resources=%d' % (stats['packages'], stats['scripts'], stats['total_resources']))
        print('  duplicates=%d conflicts=%d broken=%d risky scripts=%d' % (
            stats['duplicates'] + stats['resource_dupes'], stats['conflicts'], stats['integrity'], stats['high_risks']))
        print('  game-rules notes: %d' % len(rules))
        print('  load order: %d packages loaded, %d not matched by Resource.cfg' % (
            len(findings.get('load_order', [])), len(findings.get('not_loaded', []))))
        if findings.get('resource_cfg'):
            print('  Resource.cfg: %s' % findings['resource_cfg'])

    if args.html:
        store.export_html(scan, findings, args.html)
        print('HTML report written to %s' % args.html)
    if args.csv:
        store.export_csv(scan, args.csv)
        print('CSV written to %s' % args.csv)
    if args.manifest:
        store.export_manifest(scan, findings, args.manifest)
        print('Manifest written to %s' % args.manifest)

    return 1 if stats['high_risks'] or stats['integrity'] else 0
