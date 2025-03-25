from typing import Literal, Self

from dashboard import add_info_message, add_memory_messages, add_transaction_cost


class OutputIntegration:
    def __init__(self: Self, mode: Literal["dashboard", "console"]):
        self.mode = mode

    @property
    def output(self: Self):
        if self.mode == "console":
            return print
        elif self.mode == "dashboard":
            return add_info_message

    @property
    def handle_data(self: Self):
        # Doing nothing when data is received by this function
        if self.mode == "console":
            return lambda *args, **kwargs: None

        # Running data through external function
        elif self.mode == "dashboard":
            return add_transaction_cost

    @property
    def handle_memory_data(
            self: Self
    ):
        if self.mode == "console":
            return print

        elif self.mode == "dashboard":
            return add_memory_messages
