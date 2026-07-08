"""Historical order flow replay from Databento MBO (Market By Order) data.

Databento provides high-resolution market data in a normalized format.
This module parses Databento MBO CSV exports and converts events into
Order objects for the exchange simulator.

Databento MBO CSV format (with header):
    ts_event, action, order_id, side, price, size, flags
    - ts_event: timestamp in nanoseconds since Unix epoch
    - action: A=add, M=modify, C=cancel, T=trade
    - order_id: unique order identifier
    - side: B=buy, S=sell, N=none
    - price: decimal dollar price
    - size: number of shares
    - flags: bitfield flags (currently unused)
"""

import csv
import os
from dataclasses import dataclass
from enum import Enum
from typing import Generator, Optional

import exchange_simulator as ex


class DatabentoAction(str, Enum):
    """Databento MBO action types."""
    ADD = "A"
    MODIFY = "M"
    CANCEL = "C"
    TRADE = "T"


SIDE_MAP = {
    "B": ex.Side.Buy,
    "S": ex.Side.Sell,
}


@dataclass
class DatabentoEvent:
    """A single parsed Databento MBO event."""
    timestamp_ns: int
    action: DatabentoAction
    order_id: int
    side: Optional[ex.Side]  # None for side="N"
    price: int  # Fixed-point price (price * 100 for cents)
    size: int
    flags: int

    def to_order(self) -> Optional[ex.Order]:
        """Convert this event to an Order object for the matching engine.

        Returns None for events with side=N that cannot be mapped to orders.
        """
        if self.side is None:
            return None

        order = ex.Order()
        order.id = self.order_id
        order.side = self.side
        order.price = self.price
        order.quantity = self.size
        order.filled_quantity = 0
        order.type = ex.OrderType.Limit
        order.tif = ex.TimeInForce.GTC
        order.timestamp = self.timestamp_ns
        order.stop_price = 0
        order.peg_offset = 0
        order.visible_quantity = 0
        order.hidden_quantity = 0
        return order


class DatabentoReplay:
    """Replays historical order flow from a Databento MBO CSV export.

    Parses Databento MBO CSV files (with header row) and yields events
    one at a time. Supports filtering by symbol and date range.

    Parameters
    ----------
    csv_path : str
        Path to the Databento MBO CSV file.
    price_multiplier : int
        Multiplier to convert decimal prices to fixed-point integer.
        Default 100 (converts $100.50 to 10050).
    symbol : str, optional
        If provided, only events matching this symbol are included.
        Requires a 'symbol' column in the CSV.
    start_ts : int, optional
        Start timestamp in nanoseconds. Events before this are skipped.
    end_ts : int, optional
        End timestamp in nanoseconds. Events after this are skipped.
    """

    def __init__(
        self,
        csv_path: str,
        price_multiplier: int = 100,
        symbol: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
    ):
        self.csv_path = csv_path
        self.price_multiplier = price_multiplier
        self.symbol = symbol
        self.start_ts = start_ts
        self.end_ts = end_ts
        self._validate_file()

    def _validate_file(self) -> None:
        """Check that the file exists and has the expected header."""
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(
                f"Databento data file not found: {self.csv_path}"
            )

        with open(self.csv_path, "r") as f:
            reader = csv.reader(f)
            header = next(reader, None)

            if header is None:
                raise ValueError(f"Empty data file: {self.csv_path}")

            # Normalize header names
            header_lower = [h.strip().lower() for h in header]
            required = {"ts_event", "action", "order_id", "side", "price", "size"}
            if not required.issubset(set(header_lower)):
                missing = required - set(header_lower)
                raise ValueError(
                    f"Invalid Databento format: missing columns {missing} "
                    f"in {self.csv_path}"
                )

    def events(self) -> Generator[DatabentoEvent, None, None]:
        """Yield all DatabentoEvent objects from the file.

        Applies timestamp and symbol filtering.

        Yields
        ------
        DatabentoEvent
            Parsed event data for each row.
        """
        with open(self.csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamp_ns = int(row["ts_event"])

                # Apply timestamp filtering
                if self.start_ts is not None and timestamp_ns < self.start_ts:
                    continue
                if self.end_ts is not None and timestamp_ns > self.end_ts:
                    break  # Assumes file is ordered by timestamp

                # Apply symbol filtering
                if self.symbol is not None and "symbol" in row:
                    if row["symbol"].strip() != self.symbol:
                        continue

                action_str = row["action"].strip().upper()
                if action_str not in ("A", "M", "C", "T"):
                    continue

                action = DatabentoAction(action_str)
                order_id = int(row["order_id"])
                side_str = row["side"].strip().upper()
                side = SIDE_MAP.get(side_str)  # None for "N"
                price_decimal = float(row["price"])
                price = int(round(price_decimal * self.price_multiplier))
                size = int(row["size"])
                flags = int(row.get("flags", 0))

                yield DatabentoEvent(
                    timestamp_ns=timestamp_ns,
                    action=action,
                    order_id=order_id,
                    side=side,
                    price=price,
                    size=size,
                    flags=flags,
                )

    def generate(self) -> Generator[ex.Order, None, None]:
        """Yield Order objects from the Databento MBO file.

        Only ADD events with a valid side are converted to Order objects.
        MODIFY, CANCEL, and TRADE events are available via events().

        Yields
        ------
        exchange_simulator.Order
            Orders parsed from the historical data.
        """
        for event in self.events():
            if event.action == DatabentoAction.ADD:
                order = event.to_order()
                if order is not None:
                    yield order
