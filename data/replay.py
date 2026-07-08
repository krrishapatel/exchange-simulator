"""Historical order flow replay from LOBSTER L3 data files.

LOBSTER (Limit Order Book System - The Efficient Reconstructor) provides
nanosecond-resolution limit order book data. This module parses the L3
message format and converts events into Order objects for the simulator.

LOBSTER L3 message file format (CSV, no header):
    Time, Type, Order ID, Size, Price, Direction
    - Time: seconds after midnight with nanosecond precision
    - Type: 1=new limit, 2=partial cancel, 3=full cancel, 4=execution visible,
            5=execution hidden, 7=trading halt
    - Order ID: unique order identifier
    - Size: number of shares
    - Price: price in 1/100 cents (multiply by 100 to get fixed-point)
    - Direction: 1=buy, -1=sell
"""

import csv
import os
from dataclasses import dataclass
from enum import IntEnum
from typing import Generator, Optional

import exchange_simulator as ex


LOBSTER_COLUMNS = ["time", "type", "order_id", "size", "price", "direction"]
VALID_EVENT_TYPES = {1, 2, 3, 4, 5, 7}


class LobsterEventType(IntEnum):
    """LOBSTER L3 event types."""
    NEW_LIMIT = 1
    PARTIAL_CANCEL = 2
    FULL_CANCEL = 3
    EXECUTION_VISIBLE = 4
    EXECUTION_HIDDEN = 5
    TRADING_HALT = 7


@dataclass
class LobsterEvent:
    """A single parsed LOBSTER event."""
    timestamp_ns: int
    event_type: LobsterEventType
    order_id: int
    size: int
    price: int
    direction: int  # 1=buy, -1=sell

    @property
    def side(self) -> ex.Side:
        """Convert direction to Side enum."""
        return ex.Side.Buy if self.direction == 1 else ex.Side.Sell

    def to_order(self) -> ex.Order:
        """Convert this event to an Order object for the matching engine."""
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


class LobsterReplay:
    """Replays historical order flow from a LOBSTER L3 message file.

    Parses LOBSTER L3 message files and yields events one at a time.
    Supports timestamp filtering and maps all event types to structured
    LobsterEvent objects.

    Parameters
    ----------
    csv_path : str
        Path to the LOBSTER L3 message CSV file.
    price_scale : float
        Multiplier to convert LOBSTER prices to engine price format.
        Default 1 (pass through as-is).
    start_time : float, optional
        Start timestamp in seconds after midnight. Events before this are skipped.
    end_time : float, optional
        End timestamp in seconds after midnight. Events after this are skipped.
    """

    def __init__(
        self,
        csv_path: str,
        price_scale: float = 1.0,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ):
        self.csv_path = csv_path
        self.price_scale = price_scale
        self.start_time = start_time
        self.end_time = end_time
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

    def events(self) -> Generator[LobsterEvent, None, None]:
        """Yield all LobsterEvent objects from the file.

        Applies timestamp filtering if start_time or end_time are set.

        Yields
        ------
        LobsterEvent
            Parsed event data for each row.
        """
        start_ns = int(self.start_time * 1_000_000_000) if self.start_time is not None else None
        end_ns = int(self.end_time * 1_000_000_000) if self.end_time is not None else None

        with open(self.csv_path, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 6:
                    continue

                timestamp_sec = float(row[0])
                timestamp_ns = int(timestamp_sec * 1_000_000_000)

                # Apply timestamp filtering
                if start_ns is not None and timestamp_ns < start_ns:
                    continue
                if end_ns is not None and timestamp_ns > end_ns:
                    break  # Assumes file is ordered by timestamp

                event_type_raw = int(row[1])
                if event_type_raw not in VALID_EVENT_TYPES:
                    continue

                event_type = LobsterEventType(event_type_raw)
                order_id = int(row[2])
                size = int(row[3])
                price = int(float(row[4]) * self.price_scale)
                direction = int(row[5])

                yield LobsterEvent(
                    timestamp_ns=timestamp_ns,
                    event_type=event_type,
                    order_id=order_id,
                    size=size,
                    price=price,
                    direction=direction,
                )

    def generate(self) -> Generator[ex.Order, None, None]:
        """Yield Order objects from the LOBSTER L3 file.

        Only new limit order events (type=1) are converted to Order objects.
        Cancel and execution events are available via the events() generator.

        Yields
        ------
        exchange_simulator.Order
            Orders parsed from the historical data.
        """
        for event in self.events():
            if event.event_type == LobsterEventType.NEW_LIMIT:
                yield event.to_order()


# Keep backward compatibility
class ReplayGenerator(LobsterReplay):
    """Legacy alias for LobsterReplay.

    Maintains backward compatibility with code using the original
    ReplayGenerator class.
    """

    def __init__(self, csv_path: str, price_scale: float = 1.0):
        super().__init__(csv_path, price_scale=price_scale)
