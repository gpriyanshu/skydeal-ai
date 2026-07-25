import html
from decimal import Decimal
from typing import ClassVar, Literal
from pydantic import BaseModel

from src.domain.entities import DealResult
from src.adapters.providers.constants import AIRPORT_TO_COUNTRY


class NotificationMessage(BaseModel):
    subject: str
    body_text: str
    body_html: str


class NotificationFormatter:
    """
    Formatter responsible for converting DealResult objects into presentation-ready
    notification messages supporting HTML, Plain Text, Short, and Detailed layouts.
    Redesigned to resemble a premium travel app message with specific Telegram tags.
    """
    CATEGORY_EMOJIS: ClassVar[dict[str, str]] = {
        "NORMAL": "ℹ️",  # noqa: RUF001
        "GOOD": "📉",
        "GREAT": "🔥",
        "SUPER": "🚀",
    }

    COUNTRY_FLAGS: ClassVar[dict[str, str]] = {
        "Thailand": "🇹🇭",
        "Singapore": "🇸🇬",
        "Malaysia": "🇲🇾",
        "UAE": "🇦🇪",
        "United Arab Emirates": "🇦🇪",
        "Hong Kong": "🇭🇰",
        "Japan": "🇯🇵",
        "South Korea": "🇰🇷",
        "Germany": "🇩🇪",
        "France": "🇫🇷",
        "Netherlands": "🇳🇱",
        "United Kingdom": "🇬🇧",
        "Oman": "🇴🇲",
        "Vietnam": "🇻🇳",
        "Indonesia": "🇮🇩",
        "Italy": "🇮🇹",
        "India": "🇮🇳",
    }

    AIRPORT_NAMES: ClassVar[dict[str, str]] = {
        "DEL": "Delhi",
        "BOM": "Mumbai",
        "BLR": "Bengaluru",
        "HYD": "Hyderabad",
        "MAA": "Chennai",
        "CCU": "Kolkata",
        "COK": "Kochi",
        "BKK": "Bangkok",
        "SIN": "Singapore",
        "KUL": "Kuala Lumpur",
        "DXB": "Dubai",
        "LHR": "London",
        "MCT": "Muscat",
        "HAN": "Hanoi",
        "SGN": "Ho Chi Minh City",
        "DPS": "Bali",
        "CDG": "Paris",
        "FRA": "Frankfurt",
        "AMS": "Amsterdam",
        "TYO": "Tokyo",
        "ICN": "Seoul",
    }

    def _get_emoji(self, category: str) -> str:
        return self.CATEGORY_EMOJIS.get(category.upper(), "✈️")

    def _format_inr(self, val) -> str:
        return self.format_inr_static(val)

    @classmethod
    def format_inr_static(cls, val) -> str:
        try:
            rounded = int(round(float(val)))
            return f"₹{rounded:,}"
        except Exception:
            return f"₹{val}"

    @classmethod
    def get_airline_name(cls, code: str) -> str:
        from src.adapters.providers.constants import AIRLINE_CODE_TO_NAME
        clean_code = (code or "").strip().upper()
        if not clean_code:
            return "Unknown"
        if clean_code in AIRLINE_CODE_TO_NAME:
            return AIRLINE_CODE_TO_NAME[clean_code]
        if len(clean_code) <= 3:
            return clean_code
        return clean_code.title()

    @classmethod
    def format_duration(cls, duration_minutes: int | None) -> str:
        if duration_minutes and duration_minutes > 0:
            hours = duration_minutes // 60
            minutes = duration_minutes % 60
            return f"{hours}h {minutes}m"
        return "Not available"

    @classmethod
    def format_stops(cls, stops: int | None) -> str:
        if stops is None:
            return "Unknown"
        if stops == 0:
            return "Non-stop"
        if stops == 1:
            return "1 stop"
        return f"{stops} stops"

    @classmethod
    def format_conversational_deal_html(cls, deal: DealResult, rank_title: str) -> str:
        f = deal.flight
        score_val = int(round(deal.deal_score))
        price_formatted = cls.format_inr_static(f.price)
        dep_date_formatted = f.departure_date.strftime("%d %B %Y (%A)")
        airline_name = cls.get_airline_name(f.airline)
        duration_str = cls.format_duration(f.duration_minutes)
        stops_str = cls.format_stops(f.stops)
        
        rec_emoji = {
            "BOOK NOW": "✅",
            "GOOD TIME TO BOOK": "👍",
            "WAIT": "⏳",
            "NOT ENOUGH DATA": "🔍"
        }.get(deal.recommendation, "🔍")
        
        card = (
            f"<b>{rank_title}</b>\n\n"
            f"🛫 <b>{f.origin} → {f.destination}</b>\n\n"
            f"💰 <b>{price_formatted}</b>\n\n"
            f"📅 {dep_date_formatted}\n\n"
            f"✈ Airline\n<b>{airline_name}</b>\n\n"
            f"🕒 Duration\n<b>{duration_str}</b>\n\n"
            f"🔁 Stops\n<b>{stops_str}</b>\n\n"
            f"🏷 Deal Score\n<b>{score_val} / 100</b>\n\n"
        )
        
        if deal.recommendation:
            card += (
                f"🤖 Recommendation\n\n"
                f"{rec_emoji} <b>{deal.recommendation}</b>\n\n"
                f"Confidence\n<b>{deal.confidence}%</b>"
            )
            
        if deal.insights:
            insights_bullets = "\n\n".join(f"• {html.escape(ins)}" for ins in deal.insights)
            card += (
                f"\n\n━━━━━━━━━━━━━━\n\n"
                f"📈 <b>Price Insights</b>\n\n"
                f"{insights_bullets}"
            )
            
        deep_link = f.deep_link or "https://www.aviasales.com"
        escaped_link = html.escape(deep_link)
        
        card += (
            f"\n\n━━━━━━━━━━━━━━\n\n"
            f"🔗 <a href=\"{escaped_link}\">Book Flight</a>\n\n"
            f"━━━━━━━━━━━━━━"
        )
        return card

    def format(
        self, deal: DealResult, format_type: Literal["short", "detailed"] = "detailed"
    ) -> NotificationMessage:
        """
        Formats a DealResult into a NotificationMessage.
        """
        # Escape any potential user/API input to prevent HTML injection
        origin = html.escape(deal.flight.origin)
        destination = html.escape(deal.flight.destination)
        airline = html.escape(deal.flight.airline)
        category_str = deal.deal_category.upper()
        emoji = self._get_emoji(category_str)
        dep_date = deal.flight.departure_date.strftime("%Y-%m-%d")

        price_val = f"{deal.current_price:.2f}"
        pct_val = f"{deal.percentage_below_average:.1f}%"

        deep_link = deal.flight.deep_link
        escaped_link = html.escape(deep_link) if deep_link else None

        # Build Subject
        subject = f"{emoji} {category_str} DEAL: {origin} to {destination} for {price_val}"

        # Clean/normalize airport codes for country/city lookup
        origin_clean = origin[:3].upper()
        destination_clean = destination[:3].upper()

        country_name = AIRPORT_TO_COUNTRY.get(destination_clean, "Unknown")
        flag = self.COUNTRY_FLAGS.get(country_name, "🌍")

        price_formatted = self._format_inr(deal.current_price)
        avg_formatted = self._format_inr(deal.historical_stats.rolling_average)
        savings_formatted = self._format_inr(deal.savings)
        dep_date_formatted = deal.flight.departure_date.strftime("%d %b %Y")
        deal_score_formatted = str(int(round(deal.deal_score)))

        org_city = self.AIRPORT_NAMES.get(origin_clean, origin_clean)
        dest_city = self.AIRPORT_NAMES.get(destination_clean, destination_clean)

        if "(" in origin or len(origin) > 3:
            route_text = f"{origin} → {destination}"
        else:
            route_text = f"{org_city} ({origin}) → {dest_city} ({destination})"

        if format_type == "short":
            # Short plain text format
            body_text = (
                f"{emoji} {category_str} DEAL: {route_text} for {price_formatted} "
                f"(Save {savings_formatted}, {pct_val} below avg). "
            )
            if deep_link:
                body_text += f"Link: {deep_link}"
            else:
                body_text += "No booking link available."

            # Short HTML format
            body_html = (
                f"{emoji} <b>{category_str} DEAL</b>: {route_text} "
                f"for <b>{price_formatted}</b> (Save {savings_formatted}, {pct_val} below avg). "
            )
            if escaped_link:
                body_html += f'<a href="{escaped_link}">Book here</a>'
            else:
                body_html += "No booking link available."
        else:
            # Premium detailed layout
            lines = [
                f"{emoji} <b>{category_str} DEAL</b>",
                "",
                f"{flag} <b>{country_name}</b>",
                "",
                f"✈ {org_city} ({origin})",
                f"➡ {dest_city} ({destination})",
                "",
                "━━━━━━━━━━━━━━",
                "",
                "💰 <b>Price</b>",
                f"{price_formatted}",
                "",
                "📉 <b>Historical Average</b>",
                f"{avg_formatted}",
                "",
                "💸 <b>You Save</b>",
                f"{savings_formatted} ({pct_val})",
                "",
                "🛫 <b>Departure</b>",
                f"{dep_date_formatted}",
                "",
                "🛩 <b>Airline</b>",
                f"{airline}",
                "",
                "🏷 <b>Deal Score</b>",
                f"{deal_score_formatted} / 100",
                "",
                "━━━━━━━━━━━━━━",
                "",
                "🔗 <b>Book Flight</b>",
            ]

            # Detailed HTML format
            html_lines = list(lines)
            if escaped_link:
                html_lines.append(f'<a href="{escaped_link}">Book Now</a>')
            else:
                html_lines.append("No booking link available.")
            body_html = "\n".join(html_lines)

            # Detailed plain text format
            text_lines = list(lines)
            if deep_link:
                text_lines.append(f"{deep_link}")
            else:
                text_lines.append("No booking link available.")
            body_text = "\n".join(text_lines)

        return NotificationMessage(
            subject=subject,
            body_text=body_text,
            body_html=body_html
        )

    def format_summary(self, deals: list[DealResult]) -> NotificationMessage:
        """
        Formats a list of DealResult items into a single summary notification.
        """
        if not deals:
            return NotificationMessage(
                subject="🔥 Today's Best Flight Deals",
                body_text="No deals found today.",
                body_html="No deals found today."
            )

        html_blocks = ["🔥 <b>Today's Best Flight Deals</b>", ""]
        text_blocks = ["🔥 Today's Best Flight Deals", ""]

        for deal in deals:
            origin = html.escape(deal.flight.origin)
            destination = html.escape(deal.flight.destination)
            origin_clean = origin[:3].upper()
            destination_clean = destination[:3].upper()
            country_name = AIRPORT_TO_COUNTRY.get(destination_clean, "Unknown")
            flag = self.COUNTRY_FLAGS.get(country_name, "🌍")

            price_formatted = self._format_inr(deal.current_price)
            savings_formatted = self._format_inr(deal.savings)
            pct_val = f"{deal.percentage_below_average:.1f}%"
            dep_date_formatted = deal.flight.departure_date.strftime("%d %b %Y (%A)")
            deal_score_formatted = str(int(round(deal.deal_score)))

            org_city = self.AIRPORT_NAMES.get(origin_clean, origin_clean)
            dest_city = self.AIRPORT_NAMES.get(destination_clean, destination_clean)
            route_text = f"{org_city} ({origin}) → {dest_city} ({destination})"

            deep_link = deal.flight.deep_link
            escaped_link = html.escape(deep_link) if deep_link else None

            # Category emojis mapping
            category_emojis = {
                "NORMAL": "✈️",
                "GOOD": "🏷️",
                "GREAT": "🔥",
                "SUPER": "💥"
            }
            cat_emoji = category_emojis.get(deal.deal_category.upper(), "✈️")
            category_header = f"{cat_emoji} <b>{deal.deal_category.upper()} DEAL</b>"

            # Parse explanation bullets (double-spaced)
            bullets = []
            if deal.explanation:
                for b in deal.explanation.split("; "):
                    if b.strip():
                        bullets.append(f"✅ {b.strip()}")
            explanation_bullets = "\n\n".join(bullets) if bullets else "✅ Consistent with market pricing"

            # Duration & stops strings
            duration_str = ""
            hours, minutes = 0, 0
            if deal.flight.duration_minutes and deal.flight.duration_minutes > 0:
                hours = deal.flight.duration_minutes // 60
                minutes = deal.flight.duration_minutes % 60
                duration_str = f"🕒 Duration\n{hours}h {minutes}m"

            stops_str = ""
            if deal.flight.stops is not None:
                if deal.flight.stops == 0:
                    stops_str = "🔁 Stops\nNon-stop"
                elif deal.flight.stops == 1:
                    stops_str = "🔁 Stops\n1 stop"
                else:
                    stops_str = f"🔁 Stops\n{deal.flight.stops} stops"

            # Emojis for recommendation
            rec_emoji = {
                "BOOK NOW": "✅",
                "GOOD TIME TO BOOK": "👍",
                "WAIT": "⏳",
                "NOT ENOUGH DATA": "🔍"
            }.get(deal.recommendation, "🔍")

            # HTML item block
            html_item = (
                f"{category_header}\n"
                f"{flag} <b>{country_name}</b>\n"
                f"🛫 <b>{origin} → {destination}</b>\n"
                f"<b>{price_formatted}</b>\n\n"
                f"📅 <b>Departure</b>\n"
                f"{dep_date_formatted}\n\n"
                f"🛩 <b>Airline</b>\n"
                f"{html.escape(deal.flight.airline)}\n\n"
            )
            if duration_str:
                html_item += f"🕒 <b>Duration</b>\n{hours}h {minutes}m\n\n"
            if stops_str:
                stops_val = "Non-stop" if deal.flight.stops == 0 else (f"1 stop" if deal.flight.stops == 1 else f"{deal.flight.stops} stops")
                html_item += f"🔁 <b>Stops</b>\n{stops_val}\n\n"

            html_item += (
                f"🏷 <b>Deal Score</b>\n"
                f"<b>{deal_score_formatted} / 100</b>\n\n"
                f"<b>Why?</b>\n\n"
                f"{explanation_bullets}\n\n"
            )

            if deal.recommendation:
                html_item += (
                    f"🤖 <b>Recommendation</b>\n\n"
                    f"{rec_emoji} <b>{deal.recommendation}</b>\n\n"
                    f"Confidence\n"
                    f"<b>{deal.confidence}%</b>\n\n"
                )

            if deal.insights:
                insights_bullets = "\n\n".join(f"• {html.escape(ins)}" for ins in deal.insights)
                html_item += (
                    f"━━━━━━━━━━━━━━\n\n"
                    f"📈 <b>Price Insights</b>\n\n"
                    f"{insights_bullets}\n\n"
                )

            if escaped_link:
                html_item += f'━━━━━━━━━━━━━━\n\n🔗 <a href="{escaped_link}">Book Flight</a>'
            else:
                html_item += "━━━━━━━━━━━━━━\n\n🔗 No booking link"

            html_blocks.append("━━━━━━━━━━━━━━━━")
            html_blocks.append("")
            html_blocks.append(html_item)
            html_blocks.append("")

            # Text item block
            explanation_bullets_plain = explanation_bullets.replace("<b>", "").replace("</b>", "")
            text_item = (
                f"{cat_emoji} {deal.deal_category.upper()} DEAL\n"
                f"{flag} {country_name}\n"
                f"🛫 {origin} → {destination}\n"
                f"{price_formatted}\n\n"
                f"📅 Departure\n"
                f"{dep_date_formatted}\n\n"
                f"🛩 Airline\n"
                f"{deal.flight.airline}\n\n"
            )
            if duration_str:
                text_item += f"{duration_str}\n\n"
            if stops_str:
                text_item += f"{stops_str}\n\n"

            text_item += (
                f"🏷 Deal Score\n"
                f"{deal_score_formatted} / 100\n\n"
                f"Why?\n\n"
                f"{explanation_bullets_plain}\n\n"
            )

            if deal.recommendation:
                text_item += (
                    f"🤖 Recommendation\n\n"
                    f"{rec_emoji} {deal.recommendation}\n\n"
                    f"Confidence\n"
                    f"{deal.confidence}%\n\n"
                )

            if deal.insights:
                insights_bullets_plain = "\n\n".join(f"• {ins}" for ins in deal.insights)
                text_item += (
                    f"━━━━━━━━━━━━━━\n\n"
                    f"📈 Price Insights\n\n"
                    f"{insights_bullets_plain}\n\n"
                )

            if deep_link:
                text_item += f"━━━━━━━━━━━━━━\n\n🔗 Link: {deep_link}"
            else:
                text_item += "━━━━━━━━━━━━━━\n\n🔗 No booking link"

            text_blocks.append("━━━━━━━━━━━━━━━━")
            text_blocks.append("")
            text_blocks.append(text_item)
            text_blocks.append("")

        html_blocks.append("━━━━━━━━━━━━━━━━")
        html_blocks.append("")
        html_blocks.append("🔗 <b>Open App for More Details</b>")

        text_blocks.append("━━━━━━━━━━━━━━━━")
        text_blocks.append("")
        text_blocks.append("🔗 Open App for More Details")

        return NotificationMessage(
            subject="🔥 Today's Best Flight Deals",
            body_text="\n".join(text_blocks),
            body_html="\n".join(html_blocks)
        )

    def format_baseline(self, deals: list[DealResult]) -> NotificationMessage:
        """
        Formats a list of DealResult baseline items into a single startup/baseline notification.
        """
        if not deals:
            return NotificationMessage(
                subject="🚀 SkyDeal AI Started",
                body_text="Flight monitoring has started. No baseline flights available.",
                body_html="Flight monitoring has started. No baseline flights available."
            )

        html_blocks = [
            "🚀 <b>SkyDeal AI Started</b>",
            "",
            "Flight monitoring has started successfully!",
            "These are today's baseline prices for your monitored routes.",
            "Future alerts will only be sent when prices become cheaper than today's prices.",
            ""
        ]
        text_blocks = [
            "🚀 SkyDeal AI Started",
            "",
            "Flight monitoring has started successfully!",
            "These are today's baseline prices for your monitored routes.",
            "Future alerts will only be sent when prices become cheaper than today's prices.",
            ""
        ]

        for deal in deals:
            origin = html.escape(deal.flight.origin)
            destination = html.escape(deal.flight.destination)
            origin_clean = origin[:3].upper()
            destination_clean = destination[:3].upper()
            country_name = AIRPORT_TO_COUNTRY.get(destination_clean, "Unknown")
            flag = self.COUNTRY_FLAGS.get(country_name, "🌍")

            price_formatted = self._format_inr(deal.current_price)
            dep_date_formatted = deal.flight.departure_date.strftime("%d %b %Y")

            org_city = self.AIRPORT_NAMES.get(origin_clean, origin_clean)
            dest_city = self.AIRPORT_NAMES.get(destination_clean, destination_clean)
            route_text = f"{org_city} ({origin}) → {dest_city} ({destination})"

            deep_link = deal.flight.deep_link
            escaped_link = html.escape(deep_link) if deep_link else None

            # HTML item block
            html_item = (
                f"{flag} <b>{country_name}</b>\n"
                f"🛫 <b>{origin} → {destination}</b>\n\n"
                f"💰 Baseline Price: <b>{price_formatted}</b>\n"
                f"🛫 Departure: <b>{dep_date_formatted}</b>\n"
            )
            if escaped_link:
                html_item += f'🔗 <a href="{escaped_link}">Book Flight</a>'
            else:
                html_item += "🔗 No booking link"

            html_blocks.append("━━━━━━━━━━━━━━━━")
            html_blocks.append("")
            html_blocks.append(html_item)
            html_blocks.append("")

            # Text item block
            text_item = (
                f"{flag} {country_name}\n"
                f"🛫 {origin} → {destination}\n\n"
                f"💰 Baseline Price: {price_formatted}\n"
                f"🛫 Departure: {dep_date_formatted}\n"
            )
            if deep_link:
                text_item += f"🔗 Link: {deep_link}"
            else:
                text_item += "🔗 No booking link"

            text_blocks.append("━━━━━━━━━━━━━━━━")
            text_blocks.append("")
            text_blocks.append(text_item)
            text_blocks.append("")

        html_blocks.append("━━━━━━━━━━━━━━━━")
        html_blocks.append("")
        html_blocks.append("🔗 <b>Open App for More Details</b>")

        text_blocks.append("━━━━━━━━━━━━━━━━")
        text_blocks.append("")
        text_blocks.append("🔗 Open App for More Details")

        return NotificationMessage(
            subject="🚀 SkyDeal AI Started",
            body_text="\n".join(text_blocks),
            body_html="\n".join(html_blocks)
        )

    def format_goal_summary(
        self,
        goal: "TravelGoal",
        deals: list[DealResult],
        old_prices: dict[str, Decimal] | None = None
    ) -> NotificationMessage:
        """
        Formats a list of DealResult items triggered by a specific TravelGoal for Sprint 19.
        """
        if not deals:
            return NotificationMessage(
                subject="🎯 Travel Goal Matched: 🎉 Better Flight Found!",
                body_text="No deals found.",
                body_html="No deals found."
            )

        start_month_str = goal.start_date.strftime("%B %Y")
        if goal.start_date.month == goal.end_date.month and goal.start_date.year == goal.end_date.year:
            travel_window_str = start_month_str
        else:
            travel_window_str = f"{goal.start_date.strftime('%d %b %Y')} to {goal.end_date.strftime('%d %b %Y')}"

        route_str = f"{deals[0].flight.origin} → {deals[0].flight.destination}"
        html_blocks = [f"🎯 <b>Travel Goal Matched</b> (Destination: {goal.country}, Window: {travel_window_str}, Route: {route_str})", ""]
        text_blocks = [f"🎯 Travel Goal Matched (Destination: {goal.country}, Window: {travel_window_str}, Route: {route_str})", ""]
        
        for deal in deals:
            old_price_val = old_prices.get(deal.flight.id) if old_prices else None
            if not old_price_val or old_price_val <= deal.current_price:
                old_price_val = deal.historical_stats.rolling_average
            saved_val = old_price_val - deal.current_price
            if saved_val <= 0:
                saved_val = deal.savings

            dep_date_str = deal.flight.departure_date.strftime("%d %b")
            
            rec_str = "🔍 Monitor price trends"
            if deal.recommendation:
                rec_upper = deal.recommendation.upper()
                if "BOOK" in rec_upper or "GREAT" in rec_upper or "SUPER" in rec_upper:
                    rec_str = "✅ Great time to book"
                elif "GOOD" in rec_upper:
                    rec_str = "✅ Good time to book"
                elif "WAIT" in rec_upper:
                    rec_str = "⏳ Wait for better price"

            deep_link = deal.flight.deep_link or "https://www.aviasales.com"
            escaped_link = html.escape(deep_link)

            html_item = (
                f"🎉 <b>Better Flight Found!</b>\n\n"
                f"<b>Destination:</b>\n{goal.country}\n\n"
                f"<b>Old Price:</b>\n₹{old_price_val:,.0f}\n\n"
                f"<b>New Price:</b>\n<b>₹{deal.current_price:,.0f}</b>\n\n"
                f"<b>Saved:</b>\n₹{saved_val:,.0f}\n\n"
                f"<b>Airline:</b>\n{html.escape(deal.flight.airline)}\n\n"
                f"<b>Departure:</b>\n{dep_date_str}\n\n"
                f"<b>Recommendation:</b>\n{rec_str}\n\n"
                f"🔗 <a href=\"{escaped_link}\">Book Flight</a>"
            )
            html_blocks.append(html_item)

            text_item = (
                f"🎉 Better Flight Found!\n\n"
                f"Destination:\n{goal.country}\n\n"
                f"Old Price:\n₹{old_price_val:,.0f}\n\n"
                f"New Price:\n₹{deal.current_price:,.0f}\n\n"
                f"Saved:\n₹{saved_val:,.0f}\n\n"
                f"Airline:\n{deal.flight.airline}\n\n"
                f"Departure:\n{dep_date_str}\n\n"
                f"Recommendation:\n{rec_str}\n\n"
                f"Book Flight: {deep_link}"
            )
            text_blocks.append(text_item)

        return NotificationMessage(
            subject="🎯 Travel Goal Matched: 🎉 Better Flight Found!",
            body_text="\n\n====================\n\n".join(text_blocks),
            body_html="\n\n====================\n\n".join(html_blocks)
        )

    def format_personal_routes_summary(self, deals: list[dict]) -> NotificationMessage:
        """
        Formats a list of domestic route deals into a premium presentation-ready message.
        """
        subject = "🏠 Personal Route Deals: 🎉 New Domestic Fare Alerts!"
        
        html_blocks = ["🏠 <b>Home Route Deals</b>", ""]
        text_blocks = ["🏠 Home Route Deals", ""]
        
        for deal in deals:
            flight = deal["flight"]
            price_str = self._format_inr(flight.price)
            date_str = flight.departure_date.strftime("%d %b %Y")
            airline_name = self.get_airline_name(flight.airline)
            category_str = deal["category"].upper()
            
            # HTML
            html_blocks.append("━━━━━━━━━━━━")
            html_blocks.append(f"✈ <b>{flight.origin} → {flight.destination}</b>")
            html_blocks.append(f"{price_str}")
            html_blocks.append(f"📅 {date_str}")
            html_blocks.append(f"🛫 {airline_name}")
            html_blocks.append(f"🏷 <b>{category_str} DEAL</b>")
            
            # Text
            text_blocks.append("━━━━━━━━━━━━")
            text_blocks.append(f"✈ {flight.origin} → {flight.destination}")
            text_blocks.append(f"{price_str}")
            text_blocks.append(f"📅 {date_str}")
            text_blocks.append(f"🛫 {airline_name}")
            text_blocks.append(f"🏷 {category_str} DEAL")

        # Separator before footer
        html_blocks.append("━━━━━━━━━━━━")
        text_blocks.append("━━━━━━━━━━━━")
        
        # Link
        first_link = "https://www.google.com/travel/flights"
        if deals and hasattr(deals[0]["flight"], "ticket_link") and deals[0]["flight"].ticket_link:
            first_link = deals[0]["flight"].ticket_link
            
        html_blocks.append(f"🔗 <a href='{first_link}'>Book Flight</a>")
        text_blocks.append(f"🔗 Book Flight: {first_link}")
        
        return NotificationMessage(
            subject=subject,
            body_text="\n".join(text_blocks),
            body_html="\n".join(html_blocks)
        )


