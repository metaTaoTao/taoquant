"""Analyze BULLISH strategy buy/sell imbalance."""
import pandas as pd

orders = pd.read_csv('run/results_bullish_20240703_20240810/orders.csv')
orders['timestamp'] = pd.to_datetime(orders['timestamp'])

print('=== BUY vs SELL ORDERS ===')
print()

buy_orders = orders[orders['direction'] == 'buy']
sell_orders = orders[orders['direction'] == 'sell']

print(f'BUY orders:  {len(buy_orders):>4}  |  Total: {buy_orders["size"].sum():>8.4f} BTC  |  Avg price: ${buy_orders["price"].mean():>10,.2f}')
print(f'SELL orders: {len(sell_orders):>4}  |  Total: {sell_orders["size"].sum():>8.4f} BTC  |  Avg price: ${sell_orders["price"].mean():>10,.2f}')
print()
print(f'Net position (BUY - SELL): {buy_orders["size"].sum() - sell_orders["size"].sum():.4f} BTC')
print()

# Total cost analysis
total_buy_cost = buy_orders['cost'].sum()
total_sell_proceeds = sell_orders['proceeds'].sum()

print('=== CASH FLOW ANALYSIS ===')
print(f'Cash spent on buys:    ${total_buy_cost:>15,.2f}')
print(f'Cash from sells:       ${total_sell_proceeds:>15,.2f}')
print(f'Net cash outflow:      ${total_buy_cost - total_sell_proceeds:>15,.2f}')
print()

# Commission analysis
total_buy_comm = buy_orders['commission'].sum()
total_sell_comm = sell_orders['commission'].sum()
print(f'Buy commissions:       ${total_buy_comm:>15,.2f}')
print(f'Sell commissions:      ${total_sell_comm:>15,.2f}')
print(f'Total commissions:     ${total_buy_comm + total_sell_comm:>15,.2f}')
print()

# Check final price
final_price = orders.iloc[-1]['market_price']
final_holdings = buy_orders["size"].sum() - sell_orders["size"].sum()
final_holdings_value = final_holdings * final_price
print(f'Final market price:    ${final_price:>15,.2f}')
print(f'Final holdings value:  ${final_holdings_value:>15,.2f}')
print(f'Avg buy cost:          ${total_buy_cost / buy_orders["size"].sum():>15,.2f}')
print(f'Unrealized loss:       ${final_holdings_value - (total_buy_cost - total_sell_proceeds):>15,.2f}')
