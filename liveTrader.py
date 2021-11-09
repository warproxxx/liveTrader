import ccxt
from huobi.HuobiDMService import HuobiDM

import os
import time
import numpy as np
import json
import pandas as pd
import datetime
import decimal
import inspect
import sys

from dydx3 import Client
from dydx3.constants import API_HOST_MAINNET, TIME_IN_FORCE_GTT

def round_down(value, decimals):
    with decimal.localcontext() as ctx:
        d = decimal.Decimal(value)
        ctx.rounding = decimal.ROUND_DOWN
        return float(round(d, decimals))
        
class liveTrading():
    def __init__(self, exchange, symbol='BTC/USD', lev=3, params={}):
        self.symbol = symbol

        self.lev = lev
        self.symbol_here = ""
        self.exchange_name = exchange
        self.threshold_tiggered = False
        self.attempts = 5

        apiKey = os.getenv('{}_ID'.format(self.exchange_name.upper()))
        apiSecret = os.getenv('{}_SECRET'.format(self.exchange_name.upper()))

        if exchange == 'bitmex':
            self.exchange = ccxt.bitmex({
                            'apiKey': apiKey,
                            'secret': apiSecret,
                            'enableRateLimit': True,
                        })
            
            if symbol == "BTC/USD":
                self.symbol_here = "XBTUSD"
            else:
                self.symbol_here = symbol.replace("/", "")

        elif exchange == 'binance_futures':
            self.exchange = ccxt.binance({
                            'apiKey': apiKey,
                            'secret': apiSecret,
                            'enableRateLimit': True,
                        })
            
            self.symbol_here = symbol.replace("/", "")

        elif exchange == 'bybit':
            self.exchange = ccxt.bybit({
                            'apiKey': apiKey,
                            'secret': apiSecret,
                            'enableRateLimit': True,
                        })

            self.symbol_here = symbol.replace("/", "")

        elif exchange == 'ftx':
            subaccount = params['subaccount']
            
            self.exchange = ccxt.ftx({
                            'apiKey': apiKey,
                            'secret': apiSecret,
                            'enableRateLimit': True,
                            'options': {'defaultMarket': 'futures'}
                        })
            
            self.symbol_here = symbol.replace("/", "")

            if subaccount != "":
                self.exchange.headers = {
                                            'FTX-SUBACCOUNT': subaccount,
                                        }

        elif exchange == 'okex':
            password = os.getenv('{}_PASSWORD'.format(self.exchange_name.upper()))

            self.exchange = ccxt.okex({
                            'apiKey': apiKey,
                            'secret': apiSecret,
                            'password': password,
                            'enableRateLimit': True                        
                        })

            self.symbol_here = symbol.replace("/", "")

        elif exchange == 'huobi_swap':
            self.exchange = HuobiDM("https://api.hbdm.com", apiKey, apiSecret)
            self.symbol_here = symbol.replace("/", "")

        elif exchange == 'dydx':
            api_key_credentials = {"key":os.getenv('DYDX_KEY'),"passphrase":os.getenv('DYDX_PASS'), "secret": os.getenv('DYDX_SECRET')}
            self.exchange = Client(API_HOST_MAINNET, api_key_credentials=api_key_credentials, stark_private_key=os.getenv('DYDX_STARK_KEY'))
            account_response = self.exchange.private.get_account(ethereum_address=os.getenv('DYDX_PUB_KEY'))
            self.position_id = account_response.data['account']['positionId']

            self.symbol_here = self.symbol
            self.eth_address = os.getenv('DYDX_PUB_KEY')
        
        if exchange in ['dydx', 'huobi_swap']:
            self.increment = 0.1 #this needs fix
        else:
            lm = self.exchange.load_markets()
            self.increment = lm[self.symbol]['precision']['amount']

        number_str = '{0:f}'.format(self.increment)
        self.round_places = len(number_str.split(".")[1])

    def set_leverage(self):
        count = 0
        
        while count < 5:
            try:
                if self.exchange_name == 'bitmex':
                    stats = self.exchange.private_post_position_leverage({"symbol": self.symbol_here, "leverage": str(self.lev)})
                    break
                elif self.exchange_name == 'binance_futures':
                    stats = self.exchange.fapiPrivate_post_leverage({"symbol": self.symbol_here, "leverage": str(self.lev)})
                    break
                elif self.exchange_name == 'bybit':
                    try:
                        stats = self.exchange.v2_private_post_position_leverage_save({'symbol': self.symbol_here, 'leverage': str(self.lev)})
                    except:
                        pass

                    try:
                        stats = self.exchange.v2_private_post_position_switch_isolated({'symbol': self.symbol_here, 'is_isolated': False, 'sell_leverage': str(self.lev), 'buy_leverage': str(self.lev)})
                    except:
                        pass
                        
                    break
                elif self.exchange_name == 'ftx':
                    try:
                        stats = self.exchange.private_post_account_leverage({"leverage": self.lev})
                        break
                    except Exception as e:
                        break
                elif self.exchange_name == 'okex':
                    try:
                        stats = self.exchange.swapPostAccountsInstrumentIdLeverage({'instrument_id': self.symbol, 'leverage':str(self.lev), 'side':'3' })
                        break
                    except Exception as e:
                        break
                elif self.exchange_name == 'huobi_swap':
                    try:
                        stats = self.exchange.send_post_request('/swap-api/v1/swap_switch_lever_rate', {'contract_code': self.symbol, 'lever_rate': self.lev}) 
                        break
                    except Exception as e:
                        break
                elif self.exchange_name == 'dydx':
                    break

            except ccxt.BaseError as e:

                if "many requests" in str(e).lower():
                    print("Too many requests in {}".format(inspect.currentframe().f_code.co_name))
                    break
                
                if self.exchange_name == 'bitmex':
                    if ("insufficient Available Balance" in str(e)):
                        break
                elif self.exchange_name == 'binance_futures':
                    if ("insufficient" in str(e)):
                        break
                elif self.exchange_name == 'bybit':
                    if ("same to the old" in str(e)):
                        break
                    if ("balance not enough" in str(e)):
                        break
                
                count = count + 1
    
    def get_limit_orders(self):
        pass

    def get_stop_orders(self):
        pass

    def get_all_orders(self):
        if self.exchange_name == 'bitmex':
            orders = self.exchange.fetch_open_orders()
        elif self.exchange_name == 'binance_futures':
            orders = self.exchange.fapiPrivate_get_openorders()
        elif self.exchange_name == 'bybit':
            stop_orders = self.exchange.openapi_get_stop_order_list()['result']['data']
            limit_orders = self.exchange.fetch_open_orders()
            orders = limit_orders + stop_orders
        elif self.exchange_name == 'ftx':
            limit_orders = self.exchange.fetch_open_orders()
            stop_orders = self.exchange.request('conditional_orders', api='private', method='GET', params={'market': self.symbol_here})['result']
            orders = limit_orders + stop_orders
        elif self.exchange_name == 'okex':
            limit_orders = self.exchange.swap_get_orders_instrument_id({'instrument_id': self.symbol, 'state': '0'})['order_info']
            stop_orders = self.exchange.swap_get_order_algo_instrument_id({'instrument_id': self.symbol, 'order_type': "1", "status": "1"})['orderStrategyVOS']
            orders = limit_orders + stop_orders
        elif self.exchange_name == 'huobi_swap':
            stop_orders = self.exchange.send_post_request('/swap-api/v1/swap_trigger_openorders', {'contract_code': self.symbol})['data']['orders']
        elif self.exchange_name == 'dydx':
            orders = []

        return orders

    def cancel_order(self, order):
        if self.exchange_name == 'bitmex':
            self.exchange.cancel_order(order['info']['orderID'])
                    
        elif self.exchange_name == 'binance_futures':
                self.exchange.fapiPrivate_delete_order(order)

        elif self.exchange_name == 'bybit':
            is_stop = False
            if 'stop_order_status' in order:
                if order['stop_order_status'] == 'Untriggered':
                    is_stop = True

            if is_stop == True:
                self.exchange.openapi_post_stop_order_cancel(params={'stop_order_id': order['stop_order_id']})
            else:
                self.exchange.cancel_order(order[''])

        elif self.exchange_name == 'ftx':
            self.exchange.cancel_order(order['info']['id'])

        elif self.exchange_name == 'okex':
            self.exchange.swap_post_cancel_order_instrument_id_order_id({'instrument_id': self.symbol, 'order_id': order['order_id']})

        elif self.exchange_name == 'huobi_swap':
            try:
                self.exchange.send_post_request('/swap-api/v1/swap_trigger_cancelall', {'contract_code': self.symbol})
            except:
                pass

            try:
                self.exchange.send_post_request('/swap-api/v1/swap_cancelall', {'contract_code': self.symbol})
            except:
                pass
                
        elif self.exchange_name == 'dydx':
            self.exchange.private.cancel_all_orders()

    def close_all_orders(self, close_stop=False):
        if self.exchange_name == 'bybit':
            self.exchange.cancel_all_orders(symbol=self.symbol)
        elif self.exchange_name == 'ftx':
            if close_stop == True:
                self.exchange.cancel_all_orders()
        elif self.exchange_name == 'okex':
            if close_stop == True:
                for order in stop_orders:
                    self.exchange.swap_post_cancel_algos({'instrument_id': self.symbol, "order_type": "1", "algo_ids": [order['algo_id']]})


    def close_stop_order(self):
        if self.exchange_name == 'ftx':
            self.exchange.cancel_all_orders()
            orders = self.get_orders()

            if len(orders) > 0:
                for order in orders:
                    self.exchange.options['cancelOrder']['method'] = 'privateDeleteConditionalOrdersOrderId';
                    self.exchange.cancel_order(order['id'], self.symbol_here)

        self.close_open_orders(close_stop=True)
    



    def get_orderbook(self):
        orderbook = {}

        if self.exchange_name == 'dydx':
            book = self.exchange.public.get_orderbook(self.symbol).data
            orderbook['best_ask'] = float(book['asks'][0]['price'])
            orderbook['best_bid'] = float(book['bids'][0]['price'])
        else:
            book = self.exchange.fetch_order_book(self.symbol)
            orderbook['best_ask'] =  book['asks'][0][0]
            orderbook['best_bid'] = book['bids'][0][0]

        return orderbook

    def get_position(self):
        '''
        Returns position (LONG, SHORT, NONE), average entry price and current quantity
        '''

        for lp in range(self.attempts):
            try:
                if self.exchange_name == 'bitmex':

                    pos = self.exchange.private_get_position()
                    if len(pos) == 0:
                        return 'NONE', 0, 0
                    else:
                        pos = pos[0]

                        #try catch because bitmex return old position
                        try:
                            if float(pos['currentQty']) < 0:
                                current_pos = "SHORT"
                            else:
                                current_pos = "LONG"

                            return current_pos, float(pos['avgEntryPrice']), float(pos['currentQty'])
                        except:
                            return 'NONE', 0, 0

                elif self.exchange_name == 'binance_futures':
                    pos = pd.DataFrame(self.exchange.fapiPrivate_get_positionrisk())
                    pos = pos[pos['symbol'] == self.symbol_here].iloc[0]

                    if float(pos['positionAmt']) == 0:
                        return 'NONE', 0, 0
                    else:
                        if float(pos['positionAmt']) < 0:
                            current_pos = "SHORT"
                        else:
                            current_pos = "LONG"

                    return current_pos, float(pos['entryPrice']), float(pos['positionAmt'])

                elif self.exchange_name == 'bybit':
                    pos = self.exchange.private_get_position_list(params={'symbol': self.symbol_here})['result']

                    if float(pos['size']) == 0:
                        return 'NONE', 0, 0
                    else:
                        if float(pos['size']) < 0:
                            current_pos = "SHORT"
                        else:
                            current_pos = "LONG"

                    return current_pos, float(pos['entry_price']), float(pos['size'])
                elif self.exchange_name == 'ftx':
                    pos = pd.DataFrame(self.exchange.private_get_positions(params={'showAvgPrice': True})['result'])

                    if len(pos) == 0:
                        return 'NONE', 0, 0
                        
                    pos = pos[pos['future'] == self.symbol_here].iloc[0]

                    if float(pos['openSize']) == 0:
                        return 'NONE', 0, 0

                    if float(pos['openSize']) > 0:
                        current_pos = "LONG"
                    elif float(pos['openSize']) < 0:
                        current_pos = "SHORT" 
                    
                    return current_pos, float(pos['recentAverageOpenPrice']), float(pos['openSize'])
                elif self.exchange_name == 'okex':
                    pos = self.exchange.swap_get_position()

                    if len(pos) > 0:
                        pos = pd.DataFrame(pos[0]['holding'])
                        pos = pos[pos['instrument_id'] == self.symbol_here].iloc[0]

                        return "LONG", float(pos['avg_cost']), int(pos['avail_position'])
                    else:
                        return 'NONE', 0, 0
                elif self.exchange_name == 'huobi_swap':
                    pos = pd.DataFrame(self.exchange.send_post_request('/swap-api/v1/swap_position_info', {'contract_code': self.symbol})['data'])
                    if len(pos) > 0:
                        pos = pos[pos['contract_code'] == self.symbol_here].iloc[0]
                        return "LONG", float(pos['cost_open']), int(pos['available'])
                    else:
                        return 'NONE', 0, 0
                elif self.exchange_name == 'dydx':
                    position = self.exchange.private.get_positions(market=self.symbol, status='OPEN').data
                    if len(position['positions']) > 0:
                        pos = position['positions'][0]
                        return pos['side'], pos['entryPrice'], pos['size']
                    else:
                        return 'NONE', 0, 0

            except ccxt.BaseError as e:
                if "many requests" in str(e).lower():
                    print("Too many requests in {}".format(inspect.currentframe().f_code.co_name))
                    break
                
                print("Error in get position: {}".format(str(e)))
                time.sleep(1)
                pass



    def add_stop_loss(self, close_at):
        for lp in range(self.attempts):
            try:
                current_pos, avgEntryPrice, amount = self.get_position()

                if self.exchange_name == 'bitmex':
                    params = {
                        'stopPx': close_at,
                        'execInst': 'LastPrice'
                        }
                    
                    order = self.exchange.create_order(self.symbol, "Stop", "Sell", amount, None, params)
                    return order
                    break
                elif self.exchange_name == 'binance_futures':
                    params = {
                        'workingType': 'CONTRACT_PRICE'
                        }

                    order = self.exchange.fapiPrivatePostOrder({'symbol': self.symbol_here, 'type': 'STOP_MARKET', 'side': 'SELL', 'stopPrice': close_at, 'quantity': str(amount), 'params': params})
                    return order
                    break
                elif self.exchange_name == 'bybit':
                    order = self.exchange.openapi_post_stop_order_create({"order_type":"Market","side":"Sell","symbol":self.symbol_here,"qty":int(amount),"base_price":close_at,"stop_px":close_at,"time_in_force":"GoodTillCancel","reduce_only":True,"trigger_by":'LastPrice'})['result']
                    return order
                elif self.exchange_name == 'ftx':
                    params = {
                        'triggerPrice': close_at
                    }

                    order = self.exchange.create_order(self.symbol, "stop", "sell", amount, None, params)
                    return order
                    break
                elif self.exchange_name == 'okex':
                    order = self.exchange.swap_post_order_algo({'instrument_id': self.symbol, 'type': '3', 'order_type': '1', 'size': str(amount), 'algo_type': "2", "trigger_price": str(close_at)})
                    return order
                    break
                elif self.exchange_name == 'huobi_swap':
                    order = self.exchange.send_post_request('/swap-api/v1/swap_trigger_order', {'contract_code': self.symbol, 'trigger_type': 'le', 'trigger_price': close_at, 'order_price': close_at-1000, 'volume': amount, 'direction': 'sell', 'offset': 'close'})
                    return order
                    break
                elif self.exchange_name == 'dydx':
                    return []
            except Exception as e:
                if "many requests" in str(e).lower():
                    print("Too many requests in {}".format(inspect.currentframe().f_code.co_name))
                    break
                
                print("Error in add stop")
                print(str(e))
                pass

    def get_balance(self):
        for lp in range(self.attempts):
            try:
                if self.exchange_name == 'bitmex':
                    symbol_only = self.symbol.split("/")[0]
                    return float(self.exchange.fetch_balance()['free'][symbol_only])
                elif self.exchange_name == 'binance_futures':
                    balance = pd.DataFrame(self.exchange.fapiPrivate_get_balance())
                    balance = balance[balance['asset'] == 'USDT']

                    if len(balance) > 0:
                        free_balance = balance.iloc[0]['withdrawAvailable']
                        return float(free_balance)
                    else:
                        return 0
                elif self.exchange_name == 'bybit':
                    return float(self.exchange.fetch_balance()['info']['result']['BTC']['available_balance'])
                elif self.exchange_name == 'ftx':
                    return float(self.exchange.fetch_balance()['USD']['total'])
                elif self.exchange_name == 'okex':
                    return float(self.exchange.request('{}/accounts'.format(self.symbol), api='swap', method='GET')['info']['equity'])
                elif self.exchange_name == 'huobi_swap':
                    return float(self.exchange.send_post_request('/swap-api/v1/swap_account_position_info', {'contract_code': self.symbol})['data'][0]['margin_available'])
                elif self.exchange_name == 'dydx':
                    account_response = self.exchange.private.get_account(ethereum_address=os.getenv('DYDX_PUB_KEY'))
                    return float(account_response.data['account']['freeCollateral'])
            except Exception as e:
                print(str(e))


    def limit_trade(self, order_type, amount, price):
        '''
        Performs limit trade detecting exchange for the given amount
        '''
        if amount > 0:
            print("Sending limit {} order for {} of size {} @ {} on {} in {}".format(order_type, self.symbol, amount, price, self.exchange_name, datetime.datetime.utcnow()))

            if self.exchange_name == 'bitmex':
                params = {
                            'execInst': 'ParticipateDoNotInitiate'
                        }

                order = self.exchange.create_order(self.symbol, 'limit', order_type, amount, price, params)
                
                if 'info' in order:
                    if 'text' in order['info']:
                        if "execInst of ParticipateDoNotInitiate" in order['info']['text']:
                            return self.limit_trade(order_type, amount, price)

                return order
            elif self.exchange_name == 'binance_futures':
                order = self.exchange.fapiPrivatePostOrder({'symbol': self.symbol_here, 'type': 'LIMIT', 'side': order_type.upper(),'price': price, 'quantity': str(amount), 'timeInForce': 'GTX'})

                if self.exchange.fapiPrivate_get_order(order)['status'] == 'EXPIRED':
                    return self.limit_trade(order_type, amount, price)

                return order

            elif self.exchange_name == 'bybit':
                params = {
                            'time_in_force': 'PostOnly'
                }

                order = self.exchange.create_order(self.symbol, type='limit', side=order_type, amount=amount, price=price, params=params)
                
                try:
                    order_id = order['info']['order_id']
                except:
                    order_id = order['info'][0]['order_id']

                order = self.exchange.fetch_order(order_id, symbol=self.symbol)

                if order['info']['order_status'] == 'Cancelled':
                    return self.limit_trade(order_type, amount, price)

                return order
            elif self.exchange_name == 'ftx':

                params = {
                    'postOnly': True
                    }
                order = self.exchange.create_order(self.symbol, type="limit", side=order_type.lower(), amount=amount, price=price, params=params)
                order = self.exchange.fetch_order(order['info']['id'])

                if order['status'] == 'canceled':
                    return self.limit_trade(order_type, amount, price)

                return order
            elif self.exchange_name == 'okex':

                if order_type == 'buy':
                    order = self.exchange.swap_post_order({'instrument_id': self.symbol, 'size': str(amount), 'type': '1', 'price': str(price), 'order_type': 1})
                elif order_type == 'sell':
                    order = self.exchange.swap_post_order({'instrument_id': self.symbol, 'size': str(amount), 'type': '3', 'price': str(price), 'order_type': 1})

                order = self.exchange.swap_get_orders_instrument_id_order_id({'instrument_id': self.symbol, 'order_id': order['order_id']})

                if order['status'] == '-1':
                    return self.limit_trade(order_type, amount, price)
                
                return order
            elif self.exchange_name == 'huobi_swap':
                
                if order_type == 'buy':
                    order = self.exchange.send_post_request('/swap-api/v1/swap_order', {'contract_code': self.symbol, 'price': price, 'volume': int(amount), 'direction': 'buy', 'offset': 'open', 'order_price_type': 'post_only', 'lever_rate': self.lev})
                elif order_type == 'sell':
                    order = self.exchange.send_post_request('/swap-api/v1/swap_order', {'contract_code': self.symbol, 'price': price, 'volume': int(amount), 'direction': 'sell', 'offset': 'close', 'order_price_type': 'post_only', 'lever_rate': self.lev})

                try:
                    order_id = order['data']['order_id']
                except:
                    order_id = order['data'][0]['order_id']

                order = self.exchange.send_post_request('/swap-api/v1/swap_order_info', {'contract_code': self.symbol, 'order_id': order_id})

                if order['data'][0]['status'] == 7:
                    return self.limit_trade(order_type, amount, price)

                return order
        else:
            print("Doing a zero trade")
            return []

    def send_limit_order(self, order_type):
        '''
        Detects amount and sends limit order for that amount
        '''
        for lp in range(self.attempts):
            try:
                amount, price = self.get_max_amount(order_type)

                if amount == 0:
                    return [], 0

                order = self.limit_trade(order_type, amount, price)

                return order, price
            except ccxt.BaseError as e:
                print(e)
                pass

    
    def market_trade(self, order_type, amount):
        '''
        Performs market trade detecting exchange for the given amount
        '''

        if amount > 0:
            print("Sending market {} order for {} of size {} on {} in {}".format(order_type, self.symbol, amount, self.exchange_name, datetime.datetime.utcnow()))

            if self.exchange_name == 'bitmex':
                order = self.exchange.create_order(self.symbol, 'market', order_type, amount, None)
                return order
            elif self.exchange_name == 'binance_futures':
                order = self.exchange.fapiPrivatePostOrder({'symbol': self.symbol_here, 'type': 'MARKET', 'side': order_type.upper(), 'quantity': str(amount)})
                return order
            elif self.exchange_name == 'bybit':
                order = self.exchange.create_order(self.symbol, 'market', order_type, amount, None)
                return order
            elif self.exchange_name == 'ftx':
                order = self.exchange.create_order(self.symbol, 'market', order_type.lower(), amount, None)
            elif self.exchange_name == 'okex':
                if order_type == 'buy':
                    order = self.exchange.swap_post_order({'instrument_id': self.symbol, 'size': int(amount), 'type': '1', 'order_type': 4})
                elif order_type == 'sell':
                    order = self.exchange.swap_post_order({'instrument_id': self.symbol, 'size': int(amount), 'type': '3', 'order_type': 4})
            elif self.exchange_name == 'huobi_swap':
                if order_type == 'buy':
                    order = self.exchange.send_post_request('/swap-api/v1/swap_order', {'contract_code': self.symbol, 'volume': int(amount), 'direction': 'buy', 'offset': 'open', 'order_price_type': 'optimal_20', 'lever_rate': int(self.lev)})
                elif order_type == 'sell':
                    order = self.exchange.send_post_request('/swap-api/v1/swap_order', {'contract_code': self.symbol, 'volume': int(amount), 'direction': 'sell', 'offset': 'close', 'order_price_type': 'optimal_20', 'lever_rate': int(self.lev)})
                
                return order
            elif self.exchange_name == 'dydx':
                orderbook = self.get_orderbook()

                if order_type == 'buy':
                    order = self.exchange.private.create_order(position_id=self.position_id, market=self.symbol, side='BUY', order_type='MARKET', size=str(amount), post_only=False, price=str(round_down(orderbook['best_bid'] * 1.02, 1)), limit_fee='0.001', expiration_epoch_seconds=int(pd.Timestamp.utcnow().timestamp()) + 120, time_in_force='IOC')
                elif order_type == 'sell':
                    order = self.exchange.private.create_order(position_id=self.position_id, market=self.symbol, side='SELL', order_type='MARKET', size=str(amount), post_only=False, price=str(round_down(orderbook['best_ask'] * 0.98, 1)), limit_fee='0.001', expiration_epoch_seconds=int(pd.Timestamp.utcnow().timestamp()) + 120, time_in_force='IOC')

                return order.data
        else:
            print("Doing a zero trade")
            return []

    def send_market_order(self, order_type):
        '''
        Detects amount and market buys/sells the amount
        '''
        for lp in range(self.attempts):
            try:
                self.close_open_orders()
                amount, price = self.get_max_amount(order_type)
                order = self.market_trade(order_type, amount)     
                return order, price      
            except ccxt.BaseError as e:
                print(e)
                pass

    def second_average(self, intervals, sleep_time, order_type):
        self.close_open_orders()
        self.threshold_tiggered = False

        amount, price = self.get_max_amount(order_type)
        
        trading_array = []
        
        
        if amount != 0:
            amount = abs(amount)

            if self.exchange_name == 'bitmex':
                single_size = int(amount / intervals)     
                final_amount = int(amount - (single_size * (intervals - 1)))

            elif self.exchange_name == 'binance_futures':
                single_size = round_down(amount / intervals, 3)
                final_amount = round_down(amount - (single_size * (intervals - 1)), 3)

            elif self.exchange_name == 'bybit':
                single_size = int(amount / intervals)     
                final_amount = int(amount - (single_size * (intervals - 1)))

            elif self.exchange_name == 'ftx':
                single_size = round_down(amount / intervals, 3)
                final_amount = round_down(amount - (single_size * (intervals - 1)), 3)
            elif self.exchange_name == 'okex' or self.exchange_name == 'huobi_swap':
                single_size = int(amount / intervals)     
                final_amount = int(amount - (single_size * (intervals - 1)))
            elif self.exchange_name == 'dydx':
                print(amount, intervals)
                single_size = round_down(amount / intervals, 2)
                final_amount = round_down(amount - (single_size * (intervals - 1)), 2)

            trading_array = [single_size] * (intervals - 1)
            trading_array.append(final_amount)
        
        print(trading_array)
        for amount in trading_array:
            try:
                order = self.market_trade(order_type, amount) 
                time.sleep(sleep_time)
            except Exception as e:
                print("Exception: {}".format(str(e)))

        current_pos, avgEntryPrice, amount = self.get_position()

        if current_pos == 'LONG':
            if self.threshold_tiggered == False and order_type == 'sell':
                try:
                    amount, price = self.get_max_amount(order_type)
                    order = self.market_trade(order_type, amount)
                except Exception as e:
                    print("Exception: {}".format(str(e)))