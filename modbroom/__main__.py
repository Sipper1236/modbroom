import sys


def main():
    if '--cli-scan' in sys.argv:
        from . import cli
        return cli.main([a for a in sys.argv[1:] if a != '--cli-scan'])
    from .ui.app import main as gui_main
    return gui_main()


if __name__ == '__main__':
    main()
