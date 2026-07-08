"""Historical order flow replay from LOBSTER L3 data files.

LOBSTER (Limit Order Book System - The Efficient Reconstructor) provides
nanosecond-resolution limit order book data. This module parses the L3
message format and converts events into Order objects for the simulator.

LOBSTER L3 message file format (CSV):
    Time, Type, Order ID, Size, Price, Direction
    - Time: seconds after midnight with nanosecond precision
    - Type: 1=new limit, 2=partial cancel, 3=full cancel, 4=execution visible,
            5=execution hidden, 7=trading halt
    - Order ID: unique order identifier
    - Size: number of shares
    - Price: price in dollar price * 10000 (fixed point)
    - Direction: 1=buy, -1=sell
"""

import csv
import os

import exchange_simulator as ex


LOBSTER_COLUMNS = ["time", "type", "order_id", "size", "price", "direction"]
VALID_EVENT_TYPES = {1, 2, 3, 4, 5, 7}


class ReplayGenerator:
    """Replays historical order flow from a LOBSTER L3 message file.

    Parameters
    ----------
    csv_path : str
        Path to the LOBSTER L3 message CSV file.
    price_scale : int
        Multiplier to convert LOBSTER prices to engine price format.
        LOBSTER uses price * 10000; if engine uses price * 1000, set to 0.1.
        Default 1 (pass through as-is).
    """

    def __init__(self, csv_path: str, price_scale: int = 1):
        self.csv_path = csv_path
        self.price_scale = price_scale
        self._validate_file()

    def _validate_file(self) -> None:
        """Check that the file exists and has a parseable format."""
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(
                f"LOBSTER data file not found: {self.csv_path}"
            )

        with open(self.csv_path, "r") as f:
            reader = csv.reader(f)
            first_row = next(reader, None)

            if first_row is None:
                raise ValueError(f"Empty data file: {self.csv_path}")

            if len(first_row) < 6:
                raise ValueError(
                    f"Invalid LOBSTER format: expected at least 6 columns, "
                    f"got {len(first_row)} in {self.csv_path}"
                )

    def generate(self):
        """Yield Order objects from the LOBSTER L3 file.

        Only new limit order events (type=1) are converted to Order objects.
        Cancel and execution events are skipped (they would need to be
        handled by the engine's cancel/fill logic).

        Yields
        ------
        exchange_simulator.Order
            Orders parsed from the historical data.
        """
        with open(self.csv_path, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 6:
                    continue

                event_type = int(row[1])

                # Only replay new limit orders
                if event_type != 1:
                    continue

                timestamp_sec = float(row[0])
                order_id = int(row[2])
                size = int(row[3])
                price = int(float(row[4]) * self.price_scale)
                direction = int(row[5])

                order = ex.Order()
                order.id = order_id
                order.side = ex.Side.Buy if direction == 1 else ex.Side.Sell
                order.price = price
                order.quantity = size
                order.filled_quantity = 0
                order.type = ex.OrderType.Limit
                order.tif = ex.TimeInForce.GTC
                order.timestamp = int(timestamp_sec * 1_000_000_000)
                order.stop_price = 0
                order.peg_offset = 0
                order.visible_quantity = 0
                order.hidden_quantity = 0

                yield order
