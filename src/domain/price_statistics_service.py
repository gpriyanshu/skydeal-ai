from decimal import Decimal


class PriceStatisticsService:
    """
    Service responsible for calculating price statistics
    (lowest, highest, EMA, delta, percentage difference).
    """
    @staticmethod
    def calculate_ema(current_price: Decimal, previous_ema: Decimal, alpha: Decimal) -> Decimal:
        """
        Calculates the new Exponential Moving Average (EMA).
        """
        return round((current_price * alpha) + (previous_ema * (Decimal('1.0') - alpha)), 2)

    @staticmethod
    def calculate_delta(current_price: Decimal, historical_average: Decimal) -> Decimal:
        """
        Calculates the difference between the current price and the historical average.
        """
        return current_price - historical_average

    @staticmethod
    def calculate_percentage_difference(
        current_price: Decimal, historical_average: Decimal
    ) -> float:
        """
        Calculates the percentage difference (discount) between the
        historical average and the current price.
        """
        if historical_average <= Decimal('0'):
            return 0.0
        diff = (historical_average - current_price) / historical_average
        return float(diff * 100)
