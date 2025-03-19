"""
Main bot module

@Developer: Stan
@AppVersion: 3.2.0
@ModuleVersion: 3.2.0
@PythonVersion: 3.13

"""

import argparse
import sys
import tracemalloc
from datetime import datetime
from os import getenv, PathLike
from os.path import abspath, dirname, join
from time import sleep
from typing import Any, Callable, Literal, Mapping, Self, Collection

import ccxt
from ccxt.base.errors import InvalidOrder
from ccxt import Exchange
from dotenv import load_dotenv

import dashboard
from integrate_dashboard import OutputIntegration
from config import Color, TestData, GeneralParameters
from predict import PredictionApp


class App:
    """
    Main bot logic.

    """
    SUPPORTED_EXCHANGES: Collection[str] = ccxt.exchanges

    # Default maximum RAM capacity (in MB)
    DEFAULT_MAX_RAM: int = GeneralParameters.DEFAULT_MAX_RAM
    SQ_1024: int = 1024 * 1024

    def __init__(
            self: Self,
            prediction_api: Callable[[Any], str],
            output_integration: OutputIntegration | None = None,
            env_file_path: str | None = None
    ) -> None:
        """

        :param env_file_path: filename of .env file to use for app
        :param prediction_api: function
        """

        tracemalloc.start()

        # If .env filepath is supplied, use it. Or else '.env' is used.
        env_file_path = env_file_path or ".env"
        load_dotenv(dotenv_path=env_file_path)

        self.exchange_name: str = getenv("DEFAULT_EXCHANGE_NAME")

        if self.exchange_name in self.SUPPORTED_EXCHANGES:
            self.exchange_api_key: str = getenv("EXCHANGE_API_KEY")
            self.exchange_secret: str = getenv("EXCHANGE_SECRET")
            self.exchange_password: str = getenv("EXCHANGE_PASSPHRASE")

            # Exchange fee per transaction (0.1% = 0.001)
            self.fee: float = float(getenv("DEFAULT_EXCHANGE_FEE"))

            self.user_output = output_integration.output
            self.handle_data = output_integration.handle_data
            self.memory_output = output_integration.handle_memory_data

        else:
            sys.exit(f"No valid exchange name provided\n"
                     f"Valid options:\n\t(`kucoin`, )"
                     f"\nActual name provided: {self.exchange_name}")

        self.algorithm_trust_percentage: float = float(getenv("ALGORITHM_TRUST_PERCENTAGE"))
        self.data_vector_length: int = int(getenv("DATA_VECTOR_LENGTH"))
        self.premium: float = float(getenv("PREMIUM_OVER_EXCHANGE_FEES")) + self.fee
        self.min_transaction_value_in_base: float = float(getenv("MIN_TRANSACTION_VALUE_IN_BASE"))

        # Timeframe of data
        self.timeframe: str = getenv("TIMEFRAME")

        # Times it takes to cancel open orders
        self.cancel_order_limit: int = int(getenv("CANCEL_ORDER_LIMIT")) or 3
        self.cancel_order_counter: int = 0

        # Times to retry after failure
        self.retries_before_sleep_limit: int = int(getenv("RETRIES_BEFORE_SLEEP_LIMIT")) or 4
        self.retries_before_sleep_counter: int = 0

        # Optimal sleep time also works
        self.base_sleep_time: int = int(getenv("BASE_SLEEP_TIME")) or \
                                    min(max(self.data_vector_length // 2,
                                            self.cancel_order_limit),
                                        5) * 60

        # Instantiate the Exchange class
        self.exchange: Exchange = getattr(ccxt, self.exchange_name)()

        # Set sandbox mode to True or False (currently, True is not supported on kucoin)
        self.exchange.set_sandbox_mode(enabled=False)

        # Set your API keys
        self.exchange.apiKey = self.exchange_api_key
        self.exchange.secret = self.exchange_secret
        self.exchange.password = self.exchange_password  # it's called `passphrase` on KuCoin

        # Set the symbol you want to trade on KuCoin
        self.symbol: str = getenv("TRADING_PAIR")
        pair_lst: list = self.symbol.split("/") if "/" in self.symbol else [
            getenv("TRADING_BASE"), getenv("TRADING_QUOTE")]
        self.base_asset: str = pair_lst[0]
        self.quote_asset: str = pair_lst[1]

        self.predict_up_or_down: Callable[[Any], str] = prediction_api

    def order(self: Self,
              order_type: Literal["market", "limit"],
              buy_or_sell: Literal["buy", "sell"],
              amount: float,
              price: float = None) -> Mapping[str, Any]:
        """
        Create order of either buy or sell

        :param order_type:
        :param buy_or_sell:
        :param amount:
        :param price:
        :return:
        """
        try:
            transaction_cost: float = round(amount * float(price), 2)
            self.user_output(f"\t[INFO]\t⭐️ {Color.ITALIC}Trying to {buy_or_sell} {self.base_asset} with "
                  f"total transaction value ≈ {transaction_cost} {self.quote_asset}.{Color.END}")
            if amount > self.min_transaction_value_in_base:
                order_id: Mapping[str, Any] = self.exchange.create_order(
                    symbol=self.symbol,
                    type=order_type,
                    side=buy_or_sell,
                    amount=amount,
                    price=price
                )
            else:
                raise ValueError("\t[INFO]\t⛔️ Won't process order (transaction too small).\n")

        except InvalidOrder as error:
            self.user_output(f"\t[ERROR]\tInvalid order:\n\t\t{error}.\n")
            return {}

        except ValueError as error:
            print(error)
            return {}

        else:

            self.user_output(f"[ACTION DONE]\t🤝 Place a limit {Color.BOLD}{buy_or_sell} order{Color.END}"
                  f" of {Color.BOLD}{self.base_asset.lower()}{amount}{Color.END} x"
                  f" {self.quote_asset.lower()}{price} ≈ {self.quote_asset.lower()}{transaction_cost}")
            self.handle_data(transaction_cost)
            return order_id

    def prepare_order(self: Self) -> tuple[float | None, float | None, float | None, float | None]:
        """

        :return: (price_buy, price_sell, amount_buy, amount_sell) or tuple of Nones
        """

        # Fetch the current ticker information for the symbol
        self.user_output("\n\t[INFO]\tFetch the current info for the symbol.")

        # Get current balance
        balance = self.exchange.fetch_balance()
        base_asset_balance = balance[self.base_asset]["free"]
        quote_asset_balance = balance[self.quote_asset]["free"]
        self.user_output(f"\t[INFO]\t💰 {self.base_asset} balance: {base_asset_balance}")
        self.user_output(f"\t[INFO]\t💵 {self.quote_asset} balance: {quote_asset_balance}")

        try:
            orderbook: Mapping[str, Any] = self.exchange.fetch_order_book(symbol=self.symbol)
            bid: Any = orderbook["bids"][0][0] if len(orderbook["bids"]) > 0 else None
            ask: Any = orderbook["asks"][0][0] if len(orderbook["asks"]) > 0 else None
            if not ask:
                raise Exception("Ask price is None")
            if not bid:
                raise Exception("Bid price is None")

        except BaseException as error:
            self.user_output(f"\t[WARNING]\t...Retrying because of some error:\n\t\t{error}.\n")
            self.retries_before_sleep_counter += 1
            if self.retries_before_sleep_counter == self.retries_before_sleep_limit:
                self.retries_before_sleep_counter = 0
                self.self_sleep()
            return None, None, None, None

        # Check the current bid and ask prices
        bid: float = float(bid)
        ask: float = float(ask)
        self.user_output(f"\t[INFO]\tBid {Color.ITALIC}≈ {round(bid, 4)} {self.quote_asset}{Color.END}"
              f", Ask {Color.ITALIC}≈ {round(ask, 4)} {self.quote_asset}{Color.END}\n")

        # Price is ALWAYS in quote asset (2nd item in trading pair `1st/2nd`)
        mean_price: float = (ask + bid) / 2
        price_buy: float = mean_price * (1 - self.premium)
        price_sell: float = mean_price * (1 + self.premium)
        # price_buy = price_sell = mean_price
        # price_buy: float = ask
        # price_sell: float = bid

        # Calculate how much of quote asset is about to be spent on a buy order
        amount_to_buy_in_quote_asset: float = self.algorithm_trust_percentage * quote_asset_balance

        # By CCXT rules, 'amount' variable for all '...order' methods
        # is ALWAYS in base asset (1st item in trading pair `1st/2nd`)
        amount_buy: float = amount_to_buy_in_quote_asset / price_buy
        amount_sell: float = self.algorithm_trust_percentage * base_asset_balance

        return price_buy, price_sell, amount_buy, amount_sell

    def run_if_open_orders(self: Self, open_orders: Collection[Any]) -> bool:
        """
        Cancel all open orders on achieving Limit value.

        :param open_orders:
        :return: bool, if the while cycle of orders should be skipped to the next iteration
        """
        self.user_output("\t[INFO]\t🛑 There are open orders.")

        self.cancel_order_counter += 1
        self.user_output(f"\t[INFO]\t💪🏻 {Color.ITALIC}Current open orders counter:{Color.END}"
              f" {Color.BOLD}{Color.DARK_CYAN}{self.cancel_order_counter}{Color.END}.")

        if self.cancel_order_counter == self.cancel_order_limit:
            self.cancel_order_counter = 0
            for order in open_orders:
                order_id_to_cancel: str = order.get("id")

                # Kucoin has no problem recognizing an order by ID only
                if self.exchange_name != "kucoin":
                    self.exchange.cancel_order(id=order_id_to_cancel, symbol=self.symbol)

                # Other exchanges might not be the same
                else:
                    self.exchange.cancel_order(id=order_id_to_cancel)
                self.user_output(f"[ACTION DONE]\t☑️ {Color.BOLD}Order"
                      f" cancelled{Color.END} with id: {order_id_to_cancel}")
            return True

        return False

    def run_if_not_open_orders(self: Self) -> bool:
        """
        Try to make new orders, if there aren't any.

        :return: if the while cycle of orders should be skipped to the next iteration
        """
        self.user_output("\t[INFO]\t🟢 No open orders.")
        self.cancel_order_counter = 0

        data: Any = self.exchange.fetch_ohlcv(
            self.symbol, self.timeframe, limit=self.data_vector_length)
        self.user_output("\t[INFO]\t📊 Got data: "
              f"({self.data_vector_length} x {self.timeframe}).")

        try:
            # Check if it is bullish up or bearish down before buying
            prediction_main: Any = self.predict_up_or_down(data)
            # prediction_support: Any = self.predict_up_or_down(data)
            if prediction_main:
                self.user_output("\t[AI]\t🤖 Got prediction.")

            else:
                self.user_output("\t[AI]\t🤖 Could not get prediction.")
                self.retries_before_sleep_counter += 1
                if self.retries_before_sleep_counter == self.retries_before_sleep_limit:
                    self.retries_before_sleep_counter = 0
                    self.self_sleep()
                return True

            # If bullish
            if prediction_main == "up":
                self.user_output(f"\t[AI]\t🤖 Is {Color.GREEN}bullish{Color.END} on {self.base_asset}.")

                price_buy, _, amount_buy, _ = self.prepare_order()
                if amount_buy is None:
                    return True

                # Place a limit buy order
                new_order: Mapping[str, Any] = self.order(
                    order_type="limit",
                    buy_or_sell="buy",
                    amount=amount_buy,
                    price=price_buy
                )
                if new_order:
                    self.user_output(f"\t[ORDER]\tBuy order id: {new_order.get("id")}")

            # If bearish
            elif prediction_main == "down":
                self.user_output(f"\t[AI]\t🤖 Is {Color.RED}bearish{Color.END} on {self.base_asset}.")

                _, price_sell, _, amount_sell = self.prepare_order()
                if amount_sell is None:
                    return True

                # Place a limit sell order
                new_order: Mapping[str, Any] = self.order(
                    order_type="limit",
                    buy_or_sell="sell",
                    amount=amount_sell,
                    price=price_sell
                )

                if new_order:
                    self.user_output(f"\t[ORDER]\tSell order id: {new_order.get("id")}")

            # If indecisive
            elif prediction_main == "hold":
                self.user_output(f"\t[AI]\t🤖 Is {Color.PURPLE}hold{Color.END} on {self.base_asset}.")
                self.user_output("\t[INFO]\t😎 Doing nothing.")

            else:
                self.self_sleep()
                return True

        except BaseException as error:
            self.retries_before_sleep_counter += 1
            if self.retries_before_sleep_counter == self.retries_before_sleep_limit:
                self.retries_before_sleep_counter = 0
                self.default_sleep_message(error, "ProbablyAIButCouldBeAnything")
                self.self_sleep()
            return True

        return False

    def output_memory_monitor(
            self: Self,
            max_memory: int | float = DEFAULT_MAX_RAM
    ) -> None:
        current, peak = tracemalloc.get_traced_memory()
        current, peak = current // self.SQ_1024, peak // self.SQ_1024
        is_maxed: str = " (peaked over MAX, restart recommended)" if peak > max_memory else ""
        msg = f"\t[TRCM]\t🚦 Current memory usage: {current} MB, peak usage: {peak} MB{is_maxed}"
        self.memory_output(msg)

    def main(self: Self, infinite_loop_condition: bool) -> None:
        """
        Main bot cycle logic.

        :param infinite_loop_condition: bool value
        :return: None
        """

        self.user_output(f"\t[INFO]\t🏦 Exchange: `{self.exchange_name}`.\n"
              "\t[INFO]\t💼 Algorithm trust percentage (reinvestment rate): "
              f"{Color.DARK_CYAN}{self.algorithm_trust_percentage * 100}%{Color.END}.\n"
              "\t[INFO]\t📈 Algorithm premium: "
              f"{Color.DARK_CYAN}{round(self.premium * 100, 4)}%{Color.END}.\n"
              "\t[INFO]\t📉 Lower limit: "
              f"{Color.DARK_CYAN}{self.min_transaction_value_in_base} "
              f"{self.base_asset}{Color.END}.\n\n"
              f"\t[INFO]\t🚀 Started algorithm with pair `{self.symbol}`.")

        while infinite_loop_condition:
            self.output_memory_monitor()

            try:
                # Market Data Print
                current_time = datetime.now()
                self.user_output(f"\n\t[INFO]\t⌚️ {Color.BOLD}Current time:"
                      f" {current_time.strftime('%B %d, %Y %I:%M:%S %p')}{Color.END}")

                # Check if there are any open orders
                self.user_output("\t[INFO]\t👀 Checking for open orders for trading pair")
                open_orders: Collection[Any] = self.exchange.fetch_open_orders(self.symbol)
                if not open_orders:
                    do_cycle_continue: bool = self.run_if_not_open_orders()
                    if do_cycle_continue:
                        continue

                else:
                    do_cycle_continue: bool = self.run_if_open_orders(open_orders=open_orders)

                    if do_cycle_continue:
                        continue

                self.self_sleep()

            except KeyboardInterrupt:
                self.user_output("[END]\tEND `main` module on KeyboardInterrupt.")
                break

            except ccxt.NetworkError as error:
                self.default_sleep_message(error, "NetworkError")
                self.self_sleep()
                continue

            except ccxt.ExchangeError as error:
                self.default_sleep_message(error, "ExchangeError")
                self.self_sleep()
                continue

            except Exception as error:
                self.default_sleep_message(error, "Some other")
                self.self_sleep()
                continue

        self.user_output("[END]\t👋🏻 END `main` module.")

    def self_sleep(self: Self) -> None:
        """
        Invoke time.sleep with needed extra logic.

        :return: None
        """
        self.user_output(f"\t[INFO]\t🙈 Pause for {self.base_sleep_time} seconds.")
        sleep(self.base_sleep_time)

    def default_sleep_message(self: Self, error: Any, tag: str) -> None:
        """
        Print sleep message with error mention. Tag is the error name.

        :param error: Exception
        :param tag: str
        :return: None
        """
        self.user_output(f"\t[ERROR]\t🙈 Retrying after sleep ({self.base_sleep_time} seconds). "
              f"{tag} exception:\n\t\t{error}.\n")


def global_main() -> None:
    console_arguments_parser = argparse.ArgumentParser(
        prog="run.py",
        description="run.py will place trades in accordance with specified parameters. "
                    "Use with `test` command to only run default data through prediction API; "
                    "use with `run` command to run main functionality.",
        epilog="Extremely caution is advised, don't run the program unless knowing EXACTLY what will happen."
    )
    default_main_environment_filename = "main.env"
    default_prediction_environment_filename = "probability_llm.env"
    subparsers = console_arguments_parser.add_subparsers(
        dest="running_mode",
        required=True
    )
    parser_test_predict_api = subparsers.add_parser("test")
    parser_test_predict_api.add_argument(
        "-p", "--predictions",
        default=default_prediction_environment_filename,
        type=str,
        required=False,
    )
    parser_run = subparsers.add_parser("run")
    parser_run.add_argument(
        "-e", "--env",
        default=default_main_environment_filename,
        type=str,
        required=False,
    )
    parser_run.add_argument(
        "-p", "--predictions",
        default=default_prediction_environment_filename,
        type=str,
        required=False,
    )
    # New argument for dashboard mode:
    parser_run.add_argument(
        "-d", "--dashboard",
        action="store_true",
        help="Launch the app in dashboard mode (powered by Streamlit)"
    )

    console = console_arguments_parser.parse_args()
    mode = console.running_mode

    # Paths
    current_path: str | PathLike = dirname(abspath(__file__))
    predictions_env_path: str | PathLike = join(current_path, console.predictions)

    # Predictions
    prediction_app: PredictionApp = PredictionApp(env_file_path=predictions_env_path)
    prediction_function: Callable[[Any], str] = prediction_app.predict_up_or_down

    match mode:
        case "run":
            main_trading_env_path = join(current_path, console.env)

            # If -d or --dashboard flags have been used to run the script
            if console.dashboard:
                print("[START]\tRunning in `run` mode with dashboard & trading logic concurrently.")
                trading_bot: App = App(
                    prediction_api=prediction_function,
                    output_integration=OutputIntegration("dashboard"),
                    env_file_path = main_trading_env_path
                )
                dashboard.run_dashboard()

            # No -d or --dashboard flag has been given
            else:
                print("[START]\tStarted module in `run` mode without dashboard.")
                trading_bot: App = App(
                    prediction_api=prediction_function,
                    output_integration=OutputIntegration("console"),
                    env_file_path=main_trading_env_path
                )

            # Regardless of usage of -d or --dashboard flags
            sys.exit(trading_bot.main(infinite_loop_condition=True))

        case "test":
            print("[START]\tSTARTED module in `test` mode.")
            print("\t[INFO]\tUptrend recognized ?",
                  prediction_function(TestData.DEFAULT_DATA_TO_TEST_API_UP))
            print("\t[INFO]\tDowntrend recognized ?",
                  prediction_function(TestData.DEFAULT_DATA_TO_TEST_API_DOWN))
            sys.exit(print("END] Test mode exited."))



if __name__ == "__main__":
    global_main()
