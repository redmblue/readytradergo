# Copyright 2021 Optiver Asia Pacific Pty. Ltd.
#
# This file is part of Ready Trader Go.
#
#     Ready Trader Go is free software: you can redistribute it and/or
#     modify it under the terms of the GNU Affero General Public License
#     as published by the Free Software Foundation, either version 3 of
#     the License, or (at your option) any later version.
#
#     Ready Trader Go is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public
#     License along with Ready Trader Go.  If not, see
#     <https://www.gnu.org/licenses/>.
import asyncio
import itertools
import math

from typing import List

from ready_trader_go import BaseAutoTrader, Instrument, Lifespan, MAXIMUM_ASK, MINIMUM_BID, Side

# if an order is open for over a certain amount of time cancel it. IMPORTANT
LOT_SIZE = 10
POSITION_LIMIT = 100
TICK_SIZE_IN_CENTS = 100
MIN_BID_NEAREST_TICK = (
    MINIMUM_BID + TICK_SIZE_IN_CENTS) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
MAX_ASK_NEAREST_TICK = MAXIMUM_ASK // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS


class AutoTrader(BaseAutoTrader):

    def __init__(self, loop: asyncio.AbstractEventLoop, team_name: str, secret: str):
        super().__init__(loop, team_name, secret)
        self.order_ids = itertools.count(1)
        self.bids = set()
        self.asks = set()
        self.curr_order_ids = []
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0
        self.last_future_highest_bid = 0  # not caching volume since assumed to be enough
        self.last_future_lowest_ask = 0
        self.etfpositions = 0
        self.futurepositions = 0
        self.SELLALL = False
        self.SELLQUANTITY = 0
        self.BUYALL = False
        self.donothedge = False
        self.donotbuy = False
        self.futurescounter = 0
        self.buyorsell = 1

        self.disablebuy = False
        self.disablesell = False

    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        print("MAX ORDER LIM REACHED ")
        print(len(self.curr_order_ids))
        for i, ele in enumerate(self.curr_order_ids):
            self.send_cancel_order(ele)
            self.curr_order_ids.pop(i)
        self.logger.warning("error with order %d: %s",
                            client_order_id, error_message.decode())
        if client_order_id != 0 and (client_order_id in self.bids or client_order_id in self.asks):
            self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_hedge_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        self.logger.info("received hedge filled for order %d with average price %d and volume %d", client_order_id,
                         price, volume)

    def highest_price(self, price_list: List[int]):
        plistlist = []
        for i, ele in enumerate(price_list):
            if (ele != 0):
                plistlist.append(ele)
        price_list = tuple(plistlist)
        currmaxprice = 0
        if (len(price_list) != 0):
            currmaxprice = price_list[0]
        for i in range(1, len(price_list)):
            if (price_list[i] > currmaxprice):
                currmaxprice = price_list[i]
        return currmaxprice

    def lowest_price(self, price_list: List[int]):
        plistlist = []
        for i, ele in enumerate(price_list):
            if (ele != 0):
                plistlist.append(ele)
        price_list = tuple(plistlist)
        currminprice = 0
        if (len(price_list) != 0):
            currminprice = price_list[0]
        # elif(len(price_list)==0):
        #    return 0
        for i in range(1, len(price_list)):
            if (price_list[i] < currminprice):
                currminprice = price_list[i]
        return currminprice

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        if (self.donotbuy):  # cancel all orders
            print("DO NOT BUY")
            self.ask_id = next(self.order_ids)
            currhighestbid = self.highest_price(bid_prices)
            currhighestbidindex = bid_prices.index(currhighestbid)
            bidvolume = bid_volumes[currhighestbidindex]
            if (bidvolume >= self.position):
                bidvolume = self.position

            print(self.futurescounter)
            return
        self.logger.info("received order book for instrument %d with sequence number %d and position is %d", instrument,
                         sequence_number, self.position)
        if (len(self.curr_order_ids) >= 5):

            for i, ele in enumerate(self.curr_order_ids):
                self.send_cancel_order(ele)
                self.curr_order_ids.pop(i)

        if (abs(self.position) > 65):
            for i, ele in enumerate(self.curr_order_ids):
                self.send_cancel_order(ele)
                self.curr_order_ids.pop(i)
            if (self.position > 0):
                self.disablebuy = True
            else:
                self.disablesell = True
        else:
            self.disablesell = False
            self.disablebuy = False
        if instrument == Instrument.ETF:
            makeorder = True
            print(f"The ask prices are {ask_prices} and\n \
                  the ask volumes are {ask_volumes}\n \
                  The bid prices are {bid_prices} and\n \
                  the bid volumes are {bid_volumes}")
            currlowestask = self.lowest_price(ask_prices)
            currhighestbid = self.highest_price(bid_prices)
            if (currhighestbid != 0 and currlowestask != 0):
                currlowestaskindex = ask_prices.index(currlowestask)
                currhighestbidindex = bid_prices.index(currhighestbid)
                currpricetotrade = ((currlowestask+currhighestbid)//2)
                askvolume = ask_volumes[currlowestaskindex]
                bidvolume = bid_volumes[currhighestbidindex]
                if (self.last_future_lowest_ask == 0 or self.last_future_highest_bid == 0):
                    makeorder = False
                currfutureprice = (
                    (self.last_future_highest_bid+self.last_future_lowest_ask)//2)
                currpricetotrade /= 100
                currpricetotrade = round(currpricetotrade)
                currpricetotrade *= 100
                currfutureprice /= 100
                currfutureprice = round(currfutureprice)
                currfutureprice *= 100
                if (currhighestbid > self.last_future_lowest_ask and currhighestbid-self.last_future_lowest_ask >= 100 and makeorder and not self.disablesell):
                    print("Sell stock time"+str(askvolume))
                    self.ask_id = next(self.order_ids)
                    if (askvolume > 20):
                        askvolume = 20
                    self.send_insert_order(
                        self.ask_id, Side.SELL, currhighestbid, askvolume, Lifespan.FILL_AND_KILL)
                    self.curr_order_ids.append(self.ask_id)  # new line
                    # hedge order done in order completetion bit
                    self.asks.add(self.ask_id)
                # elif(currfutureprice>currpricetotrade and currfutureprice-currpricetotrade>=300 and makeorder):
                elif (currlowestask < self.last_future_highest_bid and self.last_future_highest_bid-currlowestask >= 100 and makeorder and not self.disablebuy):
                    print("Buy stock time"+str(bidvolume))
                    self.bid_id = next(self.order_ids)
                    if (bidvolume > 20):
                        bidvolume = 20
                    self.send_insert_order(
                        self.bid_id, Side.BUY, currlowestask, bidvolume, Lifespan.FILL_AND_KILL)
                    self.bids.add(self.bid_id)
                    self.curr_order_ids.append(self.bid_id)
                else:
                    pass

        elif instrument == Instrument.FUTURE:

            self.last_future_highest_bid = self.highest_price(bid_prices)
            self.last_future_lowest_ask = self.lowest_price(ask_prices)

    def on_order_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        self.logger.info("received order filled for order %d with price %d and volume %d", client_order_id,
                         price, volume)
        if client_order_id in self.bids:
            self.position += volume
            self.send_hedge_order(next(self.order_ids),
                                  Side.ASK, MIN_BID_NEAREST_TICK, volume)
            self.futurescounter -= volume
            self.donotbuy = False
            print("Sold hedge")
            if (abs(self.position) >= 70):
                if (self.position > 0):
                    pass
                else:
                    pass

        elif client_order_id in self.asks:
            self.position -= volume
            self.send_hedge_order(next(self.order_ids),
                                  Side.BID, MAX_ASK_NEAREST_TICK, volume)
            self.futurescounter += volume
            self.donotbuy = False
            print("Bought hedge")
            if (abs(self.position) >= 70):
                if (self.position > 0):
                    pass
                else:
                    pass

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int,
                                fees: int) -> None:
        self.logger.info("received order status for order %d with fill volume %d remaining %d and fees %d",
                         client_order_id, fill_volume, remaining_volume, fees)
        if remaining_volume == 0:
            if client_order_id == self.bid_id:
                self.bid_id = 0
            elif client_order_id == self.ask_id:
                self.ask_id = 0
            self.bids.discard(client_order_id)
            self.asks.discard(client_order_id)

    def on_trade_ticks_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                               ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        self.logger.info("received trade ticks for instrument %d with sequence number %d", instrument,
                         sequence_number)
