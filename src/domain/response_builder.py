class ResponseBuilder:
    @staticmethod
    def build_goal_created(
        country: str,
        travel_window: str,
        budget: float,
        cheapest_fare: float | None = None,
        airline: str | None = None,
        dep_date: str | None = None,
        booking_url: str | None = None
    ) -> str:
        """
        Builds HTML response for goal creation with price snapshot details.
        """
        from datetime import datetime
        travel_window_clean = travel_window
        try:
            if " to " in travel_window:
                start_part = travel_window.split(" to ")[0]
                dt = datetime.fromisoformat(start_part)
                travel_window_clean = dt.strftime("%B %Y")
        except Exception:
            pass

        fare_str = f"₹{cheapest_fare:,.0f}" if cheapest_fare is not None else "N/A"
        
        best_deal_block = ""
        if cheapest_fare is not None:
            airline_str = f"\n{airline}" if airline else ""
            date_str = f"\n{dep_date}" if dep_date else ""
            link_str = f"\n<a href=\"{booking_url}\">🔗 Book Flight</a>" if booking_url else ""
            best_deal_block = (
                f"<b>Current Best Deal</b>\n"
                f"₹{cheapest_fare:,.0f}"
                f"{airline_str}"
                f"{date_str}"
                f"{link_str}\n\n"
                f"Monitoring has now started.\n\n"
                f"━━━━━━━━━━━━━━━━\n\n"
            )

        return (
            f"{best_deal_block}"
            f"🎯 <b>Price Alert Created (Goal Created Successfully!)</b>\n\n"
            f"<b>Destination:</b>\n{country}\n\n"
            f"<b>Travel Window:</b>\n{travel_window_clean}\n\n"
            f"<b>Budget:</b>\n₹{budget:,.0f}\n\n"
            f"<b>Current Cheapest Fare:</b>\n{fare_str}\n\n"
            f"<b>Monitoring Frequency:</b>\nEvery scheduled scan\n\n"
            f"<b>You'll be notified when:</b>\n"
            f"✅ price falls below your budget\n"
            f"✅ a significantly better deal appears\n"
            f"✅ airline availability changes\n\n"
            f"<b>Status:</b>\nACTIVE"
        )

    @staticmethod
    def build_goal_updated(country: str, field_updates: dict) -> str:
        """
        Builds HTML response for goal update.
        """
        updates_text = "\n".join(f"• {k.replace('_', ' ').title()}: <b>{v}</b>" for k, v in field_updates.items())
        return (
            f"✅ <b>Goal Updated!</b>\n\n"
            f"I have updated your travel preferences for <b>{country}</b>:\n"
            f"{updates_text}\n\n"
            f"Monitoring continues with these new preferences."
        )

    @staticmethod
    def build_goal_deleted(country: str) -> str:
        """
        Builds HTML response for goal deletion.
        """
        return (
            f"🗑️ <b>Goal Deleted</b>\n\n"
            f"I have stopped monitoring flights to <b>{country}</b> and deleted that goal."
        )

    @staticmethod
    def build_goal_paused(country: str) -> str:
        """
        Builds HTML response for goal pause.
        """
        return (
            f"⏸️ <b>Goal Paused</b>\n\n"
            f"I have temporarily paused alerts for <b>{country}</b>. You can resume at any time."
        )

    @staticmethod
    def build_goal_resumed(country: str) -> str:
        """
        Builds HTML response for goal resume.
        """
        return (
            f"▶️ <b>Goal Resumed</b>\n\n"
            f"I have resumed active monitoring for <b>{country}</b>."
        )

    @staticmethod
    def build_no_flights_found(country: str) -> str:
        """
        Builds HTML response when no flights match the search query.
        """
        return (
            f"🔍 <b>No Deals Found</b>\n\n"
            f"I searched my database but couldn't find any outstanding deals to <b>{country}</b> right now.\n"
            f"Don't worry, your alert is active and I will notify you as soon as a great deal appears!"
        )

    @staticmethod
    def build_need_more_information(prompt: str) -> str:
        """
        Builds HTML response when more details are needed from the user.
        """
        return f"ℹ️ <b>More Information Needed</b>\n\n{prompt}"
        
    @staticmethod
    def build_help() -> str:
        """
        Builds HTML help response.
        """
        return (
            "🤖 <b>SkyDeal AI Travel Agent Help</b>\n\n"
            "You can chat with me naturally to manage your travel alerts!\n\n"
            "Try saying:\n"
            "• <i>'I want to travel to Japan next September.'</i>\n"
            "• <i>'Change budget to 40000.'</i>\n"
            "• <i>'Show my goals.'</i>\n"
            "• <i>'Pause Japan.'</i>\n"
            "• <i>'Delete Thailand.'</i>"
        )
