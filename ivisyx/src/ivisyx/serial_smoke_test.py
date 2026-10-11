from __future__ import annotations

import argparse
import time

from ivisyx.config import load_settings
from ivisyx.stackchan import Expression, connect_stackchan


def main() -> None:
    settings = load_settings()

    parser = argparse.ArgumentParser(description="Send sample expression commands to Stack-chan.")
    parser.add_argument("--port", default=settings.stackchan_port, help="Serial port, for example /dev/cu.usbmodemXXXX")
    parser.add_argument("--baud", type=int, default=settings.stackchan_baud)
    args = parser.parse_args()

    stackchan = connect_stackchan(args.port, args.baud)
    try:
        for expression in (
            Expression.NEUTRAL,
            Expression.LISTENING,
            Expression.THINKING,
            Expression.SPEAKING,
            Expression.HAPPY,
            Expression.ALERT,
            Expression.ERROR,
        ):
            print(f"Sending {expression.value}")
            stackchan.check_expression(expression)
            time.sleep(1.0)
        stackchan.check_expression(Expression.NEUTRAL)
    finally:
        stackchan.close()


if __name__ == "__main__":
    main()
