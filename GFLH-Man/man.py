
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "src"), os.path.join(_HERE, "tools")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)


def main():
    from man_gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
