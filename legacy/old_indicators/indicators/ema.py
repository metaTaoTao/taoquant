from indicators.base_indicator import BaseIndicator
import mplfinance as mpf
class EMAIndicator(BaseIndicator):
    def __init__(self, spans):
        self.spans = spans
        self.color_map = {20: 'green', 50: 'blue', 100: 'orange', 200: 'red'}

    def calculate(self, df):
        for span in self.spans:
            df[f'EMA{span}'] = df['close'].ewm(span=span).mean()
        return df

    def plot(self, df):
        plots = []
        for span in self.spans:
            label = f'EMA{span}'
            plots.append(mpf.make_addplot(df[label], color=self.color_map.get(span, 'gray'), width=1))
        return plots