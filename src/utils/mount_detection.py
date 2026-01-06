import logging
from dataclasses import dataclass
from typing import Dict, List, Optional


class MCP23017NotAvailable(RuntimeError):
    """Raised when the MCP23017 dependency stack is missing."""


@dataclass
class MountDetection:
    state_bits: str
    playlist_name: Optional[str]
    all_open: bool


class MCP23017SwitchReader:
    """Thin wrapper around adafruit-circuitpython-mcp230xx for reading inputs once."""

    def __init__(
        self,
        pins: List[int],
        address: int = 0x20,
        pull_up: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        try:
            import board
            import busio
            from adafruit_mcp230xx.mcp23017 import MCP23017
            from digitalio import Pull
        except ImportError as exc:
            raise MCP23017NotAvailable(
                "Install adafruit-circuitpython-mcp230xx and adafruit-blinka to use the MCP23017 switch reader"
            ) from exc

        if not pins:
            raise ValueError("At least one pin number is required")

        self.pins = []
        self.pull_up = pull_up
        self.logger.debug(
            "Configuring MCP23017 | address=0x%02X | pins=%s | pull_up=%s", address, pins, pull_up
        )

        i2c = busio.I2C(board.SCL, board.SDA)
        mcp = MCP23017(i2c, address=address)

        for pin_number in pins:
            pin = mcp.get_pin(pin_number)
            if pull_up:
                pin.switch_to_input(pull=Pull.UP)
            else:
                pin.switch_to_input()
            self.pins.append(pin)

    def read_state_bits(self) -> str:
        """Return switch states as a bitstring matching the configured pin order."""
        bits = ["1" if pin.value else "0" for pin in self.pins]
        state_bits = "".join(bits)
        self.logger.debug("MCP23017 pin states=%s", state_bits)
        return state_bits

    def all_closed(self) -> bool:
        """True if every pin is reading low (useful when pull-ups are enabled)."""
        return all(not pin.value for pin in self.pins)

    def all_open(self) -> bool:
        """True if every pin is reading high (all switches open, no magnets)."""
        return all(pin.value for pin in self.pins)


class MountSelector:
    """Map MCP23017 pin states to a startup playlist selection."""

    def __init__(
        self,
        reader: MCP23017SwitchReader,
        state_to_playlist: Dict[str, str],
        treat_all_open_as_none: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.reader = reader
        self.state_to_playlist = state_to_playlist or {}
        self.treat_all_open_as_none = treat_all_open_as_none
        self.logger = logger or logging.getLogger(__name__)

    @classmethod
    def from_config(cls, config: Dict, logger: Optional[logging.Logger] = None) -> "MountSelector":
        pins = config.get("pins") or []
        reader = MCP23017SwitchReader(
            pins=pins,
            address=config.get("i2c_address", 0x20),
            pull_up=config.get("pull_up", True),
            logger=logger,
        )
        return cls(
            reader=reader,
            state_to_playlist=config.get("state_to_playlist") or {},
            treat_all_open_as_none=config.get("all_open_means_no_mount", True),
            logger=logger,
        )

    def detect(self) -> MountDetection:
        state_bits = self.reader.read_state_bits()
        playlist = self.state_to_playlist.get(state_bits)
        all_open = self.reader.all_open()

        if all_open and self.treat_all_open_as_none:
            self.logger.info("Mount detection: all switches open; treating as no mount")
        elif playlist:
            self.logger.info("Mount detection: state %s -> playlist '%s'", state_bits, playlist)
        else:
            self.logger.info("Mount detection: state %s not mapped", state_bits)

        return MountDetection(state_bits=state_bits, playlist_name=playlist, all_open=all_open)
